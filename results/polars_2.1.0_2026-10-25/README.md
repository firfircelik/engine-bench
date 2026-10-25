# Official Polars 2.1.0 wheel, 150M rows, 4.5 GiB cap

Run on October 25, 2026, 23:47 to October 26, 00:26 (UTC+3), on the same 8 vCPU Intel Xeon VM (16002 MiB, no swap, Linux 6.12.94) as the runs in `../polars_ooc_budget_2026-10-23/` (Polars 2.0.0) and `../polars_main_window_fix_2026-10-24/` (Polars main `d02c621`). The 150M input and products file matched `data_checksums.md5` (0 mismatches, see `host.txt`).

## Versions

- Polars 2.1.0 and polars-runtime-32 2.1.0, the official PyPI wheels installed with `pip install polars==2.1.0` into a fresh venv. `pl.show_versions()`: `Polars: 2.1.0`, `Build: 7f902bd3ffd27ff82d14278a09a295ff2f7aed92`, `Runtime: rt32`. According to the GitHub compare API, `7f902bd` is 14 commits ahead of `d02c621` and 0 behind, so it contains everything tested on October 24 (#30268, #30272, #30277, #30282, #30280). It adds #30281, #30283, #30286, #30290 to #30298 (including #30294 and #30296, wait for spills while over the budget, #30292, prefetch fraction 0.5, #30295 and #30297) and #29245.
- Python 3.13.5, DuckDB 2.0.0, pyarrow 26.0.0, psutil 7.2.2, numpy 2.5.4.

## Method

Unchanged: `bench.py`, fresh process per run, 4.5 GiB process-tree RSS watchdog (50 ms sampling), 1 GiB system floor, 5 GiB free / 30% CPU gate, 3 reps, budget passed with `--env`. DuckDB reference (`memory_limit = 3GB`) rerun in the same session. See `run.sh`. The other long-running benchmark on the VM and its PostgreSQL server were stopped. Compared with October 24, the max timestamp + sort rewrite was also run at 1024 and 512 MB.

The 4.5 GiB cap is enforced by the harness's RSS watchdog. It is not a cgroup limit. The benchmark process runs in cgroup `/agent` with `memory.max = max` (recorded in `host.txt`), and the VM does not allow creating child cgroups. Polars' cgroup-aware default budget therefore has no limit to detect here, and this run does not test it.

## 1. Issue repro (`repro_window_ooc.py --rows 60000000`, 1 rep, full output in `repro_60m_output.txt`)

Peak RSS of the child process, sampled every 20 ms. All variants returned 5,999,734 rows.

| Variant | Budget | 2.0.0 (Oct 23) | main d02c621 (Oct 24) | 2.1.0 (today) |
|---|---|---|---|---|
| window inside `filter()` | unset | 5.24 GiB, 13.76 s | 3.76 GiB, 5.04 s | 3.81 GiB, 3.60 s |
| window inside `filter()` | 1024 MB | 5.20 GiB, 15.08 s | 1.27 GiB, 10.33 s | 1.15 GiB, 7.66 s |
| window inside `filter()` | 256 MB | 4.80 GiB, 13.54 s | 1.06 GiB, 16.48 s | 0.97 GiB, 17.53 s |
| window via `with_columns` | unset | 4.86 GiB, 6.21 s | 3.75 GiB, 3.72 s | 3.74 GiB, 3.84 s |
| window via `with_columns` | 1024 MB | 4.91 GiB, 9.64 s | 1.27 GiB, 10.98 s | 1.16 GiB, 7.71 s |
| window via `with_columns` | 256 MB | 4.91 GiB, 10.82 s | 1.04 GiB, 17.78 s | 0.99 GiB, 17.51 s |
| group by | unset / 1024 / 256 | 1.83 / 2.03 / 1.37 GiB | 1.76 / 1.51 / 0.89 GiB | 1.83 / 1.10 / 0.46 GiB |

Streaming physical plan for the window inside `filter()` on 2.1.0: `filter, select, with-columns, window[maintain_order: true, ordered_eval: true], multi-scan[parquet]`, the same as on main `d02c621`. On 2.0.0 the window ran in an `in-memory-map` fallback node. None of the 150M plans (`plans.txt`, `plan_*.dot`) contains an in-memory fallback node.

## 2. 150M benchmark on 2.1.0 (median wall s of finished runs, finished/total, median peak RSS GiB of finished runs; range over all runs when killed)

| Query | Polars default (unset) | Budget 3072 | Budget 1024 | Budget 512 | DuckDB 3GB (today) |
|---|---|---|---|---|---|
| Filter + aggregate | 0.86 s, 3/3, 0.96 | 0.85 s, 3/3, 0.94 | not run | not run | 0.91 s, 3/3, 0.89 |
| Join + aggregate | 1.51 s, 3/3, 1.91 | 1.47 s, 3/3, 1.94 | not run | not run | 1.47 s, 3/3, 0.40 |
| Window dedup `over(order_by)` | 0/3, killed 4.50-4.71 | 18.78 s, 3/3, 3.34 | 20.11 s, 3/3, 1.29 | 43.01 s, 3/3, 2.15 | 8.07 s, 3/3, 3.03 |
| Sort + unique dedup | 0/3, killed 4.66-4.77 | 33.21 s, 3/3, 3.04 | 63.31 s, 3/3, 1.13 | 73.85 s, 3/3, 0.69 | (window SQL above) |
| Max timestamp + sort dedup | 5.12 s, 3/3, 3.72 | 6.06 s, 3/3, 3.16 | 8.87 s, 3/3, 1.34 | 12.14 s, 3/3, 1.29 | (window SQL above) |
| High-cardinality group by | 3.74 s, 3/3, 4.17 | 5.77 s, 3/3, 3.03 | 8.01 s, 3/3, 1.12 | 9.43 s, 3/3, 0.74 | 8.63 s, 3/3, 3.01 |

## 3. Window dedup and friends across versions (same harness, each with its own same-session DuckDB reference)

| Query, budget | 2.0.0 (Oct 23) | main d02c621 (Oct 24) | 2.1.0 (Oct 25) |
|---|---|---|---|
| Window dedup, unset | 0/3 | 0/3 | 0/3 |
| Window dedup, 3072 | 0/3 | 22.85 s, 3.52 GiB | 18.78 s, 3.34 GiB |
| Window dedup, 1024 | 0/3 | 28.68 s, 1.52 GiB | 20.11 s, 1.29 GiB |
| Window dedup, 512 | 0/3 | 42.49 s, 2.20 GiB | 43.01 s, 2.15 GiB |
| Sort + unique, unset | 0/3 | 0/3 | 0/3 |
| Sort + unique, 3072 | 0/3 | 33.62 s, 3.66 GiB | 33.21 s, 3.04 GiB |
| Sort + unique, 1024 | 31.28 s, 2.29 GiB | 42.08 s, 2.48 GiB | 63.31 s, 1.13 GiB |
| Sort + unique, 512 | not run | 77.73 s, 2.05 GiB | 73.85 s, 0.69 GiB |
| Max timestamp + sort, unset | 5.61 s, 4.02 GiB | 5.34 s, 3.76 GiB | 5.12 s, 3.72 GiB |
| Group by, unset | 4.50 s, 4.25 GiB | 3.84 s, 4.19 GiB | 3.74 s, 4.17 GiB |
| Group by, 3072 | 6.17 s, 3.46 GiB | 6.01 s, 2.99 GiB | 5.77 s, 3.03 GiB |
| Group by, 1024 | 6.69 s, 2.75 GiB | 11.59 s, 1.48 GiB | 8.01 s, 1.12 GiB |
| Group by, 512 | not run | 20.52 s, 0.95 GiB | 9.43 s, 0.74 GiB |
| DuckDB window dedup (reference) | 10.80 s, 3.02 GiB | 11.12 s, 3.03 GiB | 8.07 s, 3.03 GiB |

All Polars cells are 3/3 unless shown as 0/3. DuckDB was 27% faster today than on October 24 on the same query (8.07 s against 11.12 s), so the VM was less loaded or behaved differently. Compare ratios within a session rather than raw seconds across sessions.

## Findings

- 2.1.0 behaves like main `d02c621` and slightly better. The window inside `filter()` runs in the streaming window node, and with any budget set it finishes 3/3 at 150M rows under the 4.5 GiB cap.
- With the budget unset, the window dedup and sort + unique still exceed the 4.5 GiB cap (killed at 4.50 to 4.77 GiB). With no cgroup memory limit visible to Polars on this VM, the unset case still needs an explicit `POLARS_OOC_MEMORY_BUDGET_MB`.
- Peak memory follows the budget more closely than on main. Sort + unique peaked at 1.13 GiB at 1024 MB (2.48 on main) and 0.69 GiB at 512 MB (2.05). Group by peaked at 1.12 and 0.74 GiB (1.48 and 0.95). At 1024 MB the window dedup peaked at 1.29 GiB (1.52) and was faster (20.11 s against 28.68 s). Sort + unique at 1024 MB was slower than on main (63.31 s against 42.08 s).
- The window dedup at 512 MB still peaks higher (2.15 GiB) than at 1024 MB (1.29 GiB), as on main.
- DuckDB's window query is still faster in the same session: 8.07 s against 18.78 s for Polars at 3072 MB, about 2.3x. The fastest Polars dedup is still the max timestamp + sort rewrite (5.12 s at default, 3.72 GiB).

## Output checks

`check_outputs.py` compares Polars outputs with DuckDB outputs from the same session (`validation.jsonl`). Every finished Polars output matched: the aggregate checksums for filter, join and group by, and every dedup output (window, sort + unique, max + sort, at every budget where it finished), which matched DuckDB's window output exactly, 14,999,347 rows, 0 missing and 0 extra under bidirectional `EXCEPT ALL`. `match: null` entries are queries that were not run, or were killed, at that budget.

## Caveats

- Sort + unique at 3072 MB took 285.64 s in rep 2, against 33.21 s and 31.53 s in reps 1 and 3 (same output, same peak 3.05 GiB). It is not explained. The VM pauses when idle, which could cause a gap like this, but that is not confirmed. The median is reported.
- `min_sys_avail_gib` in the raw records is not meaningful. `bench.py` seeds it with `1e9` bytes (0.93 GiB), and the VM never went below that, so every record shows 0.93 in all three sessions. The 1 GiB floor check uses the live value and is not affected.
- The window dedup at 512 MB rep 1 started with load average 0.0, so the VM may have just resumed from a pause. Its wall time (38.63 s) is in line with reps 2 and 3.
- The repro is 1 rep.

## Files

`run.sh`, `host.txt`, `console.log`, `duckdb_ref.jsonl`, `polars_default.jsonl`, `polars_ooc3072.jsonl`, `polars_ooc1024.jsonl`, `polars_ooc512.jsonl`, `validation.jsonl`, `check_outputs.py`, `repro_window_ooc.py`, `repro_60m_output.txt`, `plans.py`, `plans.txt`, `plan_*.dot`.
