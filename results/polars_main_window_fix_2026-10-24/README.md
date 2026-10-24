# Polars main (window fixes for pola-rs/polars#30270), 150M rows, 4.5 GiB cap

Run on October 24, 2026, 17:45 to 18:09 (UTC+3), on the same 8 vCPU Intel Xeon VM (16002 MiB, no swap, Linux 6.12.94) as the October 23 run in `../polars_ooc_budget_2026-10-23/`. engine-bench at `94e21d2` (main after PR #3). The 150M input and products file matched `data_checksums.md5` (0 mismatches, see `host.txt`).

Purpose: verify the fixes Ritchie Vink merged after issue [pola-rs/polars#30270](https://github.com/pola-rs/polars/issues/30270) (a `int_range(len()).over(..., order_by=...)` window inside `filter()` ignored `POLARS_OOC_MEMORY_BUDGET_MB`).

## Build

- Polars from `github.com/pola-rs/polars` main at `d02c62175ad906f3c54cda7a0d917e6a72f73865` ("perf: Return freed memory to the OS right away while out-of-core data is spilled (#30280)", committed 2026-10-24 16:11 UTC+3). This commit includes #30268, #30272, #30277, #30282 and #30280. `pl.show_versions()` reports `Polars: 2.0.0`, `Build: d02c621...` because the version string was not bumped on main.
- Built natively (no containers) with rustup toolchain `nightly-2026-09-01` (from `rust-toolchain.toml`), `maturin 1.15.0 build --profile nodebug-release -m py-polars/runtime/polars-runtime-32/Cargo.toml`, `CARGO_BUILD_JOBS=6`, and the same x86-64 `RUSTFLAGS`/`CFLAGS` target features and `tune-cpu=skylake` as Polars' PyPI release workflow. Python frontend installed from `py-polars/` at the same commit. Build time 9 min 19 s.
- Difference from PyPI wheels: PyPI uses the `dist-release` profile (fat LTO, 1 codegen unit); this build uses `nodebug-release` (thin LTO). Small timing differences can come from that, memory behaviour should not.
- Other versions in the venv: Python 3.13.5, DuckDB 2.0.0, pyarrow 26.0.0, psutil 7.2.2, numpy 2.5.4.

## Method

Unchanged from October 23: `bench.py`, fresh process per run, 4.5 GiB process-tree RSS watchdog (50 ms sampling), 1 GiB system floor, 5 GiB free / 30% CPU gate, 3 reps, budget passed with `--env`. DuckDB reference (`memory_limit = 3GB`) rerun in the same session. See `run.sh`. The other long-running benchmark on the VM and its PostgreSQL server were stopped for this run (on October 23 PostgreSQL stayed up idle). Load average rose to 20 to 30 during the spill-heavy runs while CPU busy before each run stayed low (gate passed every time).

## 1. Issue repro (`repro_window_ooc.py --rows 60000000`, 1 rep, full output in `repro_60m_output.txt`)

Peak RSS of the child process, sampled every 20 ms.

| Variant | Budget | Polars 2.0.0 (Oct 23) | Polars main d02c621 (today) |
|---|---|---|---|
| window inside `filter()` | unset | 5.24 GiB, 13.76 s | 3.76 GiB, 5.04 s |
| window inside `filter()` | 1024 MB | 5.20 GiB, 15.08 s | 1.27 GiB, 10.33 s |
| window inside `filter()` | 256 MB | 4.80 GiB, 13.54 s | 1.06 GiB, 16.48 s |
| window via `with_columns` | unset | 4.86 GiB, 6.21 s | 3.75 GiB, 3.72 s |
| window via `with_columns` | 1024 MB | 4.91 GiB, 9.64 s | 1.27 GiB, 10.98 s |
| window via `with_columns` | 256 MB | 4.91 GiB, 10.82 s | 1.04 GiB, 17.78 s |
| group by | unset / 1024 / 256 | 1.83 / 2.03 / 1.37 GiB | 1.76 / 1.51 / 0.89 GiB |

All variants returned 5,999,734 rows.

Streaming physical plan for the window inside `filter()`:

- 2.0.0: `filter, select, zip-broadcast, multiplexer, multi-scan[parquet], in-memory-map, select` (the window ran in the `in-memory-map` in-memory engine fallback).
- main: `filter, select, with-columns, window[maintain_order: true, ordered_eval: true], multi-scan[parquet]`, the same streaming window node as the `with_columns` form. No in-memory fallback.

The same holds for the 150M benchmark query (`plans.txt`, `plan_*.dot`): no in-memory fallback node in the window, sort + unique, max + sort or group by plans.

## 2. 150M benchmark (median wall s of finished runs, finished/total, median peak RSS GiB of finished runs; range over all runs when killed)

| Query | Polars default | Polars budget 3072 | Polars budget 1024 | Polars budget 512 | DuckDB 3GB (today) |
|---|---|---|---|---|---|
| Filter + aggregate | 0.92 s, 3/3, 0.99 | 0.86 s, 3/3, 0.99 | not run | not run | 0.97 s, 3/3, 0.84 |
| Join + aggregate | 1.45 s, 3/3, 1.90 | 1.44 s, 3/3, 1.91 | not run | not run | 1.45 s, 3/3, 0.39 |
| Window dedup `over(order_by)` | 0/3, killed 4.53-4.76 | **22.85 s, 3/3, 3.52** | **28.68 s, 3/3, 1.52** | **42.49 s, 3/3, 2.20** | 11.12 s, 3/3, 3.03 |
| Sort + unique dedup | 0/3, killed 4.54-4.74 | 33.62 s, 3/3, 3.66 | 42.08 s, 3/3, 2.48 | 77.73 s, 3/3, 2.05 | (window SQL above) |
| Max timestamp + sort dedup | 5.34 s, 3/3, 3.76 | 7.03 s, 3/3, 2.85 | not run | not run | (window SQL above) |
| High-cardinality group by | 3.84 s, 3/3, 4.19 | 6.01 s, 3/3, 2.99 | 11.59 s, 3/3, 1.48 | 20.52 s, 3/3, 0.95 | 10.38 s, 3/3, 3.03 |

For comparison, Polars 2.0.0 on October 23: window dedup 0/3 at every budget (default, 3072, 1024, 512), sort + unique 0/3 at default and 3072 and 31.28 s / 2.29 GiB at 1024, group by 4.50 / 6.17 / 6.69 s at default / 3072 / 1024. DuckDB's window query took 10.80 s then and 11.12 s today, so the two sessions are roughly comparable.

Run-to-run notes: sort + unique at 512 MB took 212.08 s in rep 1 and 75.22 / 77.73 s in reps 2 and 3 (median reported). At 512 MB the window dedup peaked higher (2.20 GiB) than at 1024 MB (1.52 GiB). Raw records in the `.jsonl` files.

## Findings

- The window dedup inside `filter()` now runs in the streaming window node and is bounded by the budget. At 150M rows it finished 3/3 under the 4.5 GiB cap with any budget set (3072, 1024, 512), where 2.0.0 was killed at every budget. Without a budget it still exceeds 4.5 GiB, as before.
- It is still about 2x slower than DuckDB's window query in this session (22.85 s at 3072 MB against 11.12 s), and slower again with smaller budgets. The max timestamp + sort rewrite stays the fastest Polars dedup (5.34 s at default).
- Sort + unique now also finishes at 3072 MB (it failed there on 2.0.0), and at 512 MB.
- High-cardinality group by: memory falls with the budget (4.19, 2.99, 1.48, 0.95 GiB) and wall time rises (3.84, 6.01, 11.59, 20.52 s). Default and 3072 are faster than DuckDB here.

## Output checks

`check_outputs.py` compares Polars outputs with DuckDB outputs from the same session (`validation.jsonl`). Every finished Polars output matched: aggregate checksums for filter, join and group by, and every dedup output (window, sort + unique, max + sort) matched DuckDB's window output exactly, 14,999,347 rows, 0 missing and 0 extra under bidirectional `EXCEPT ALL`. `match: null` entries are queries that were not run (or were killed) for that budget.

## Files

`run.sh`, `host.txt`, `console.log`, `duckdb_ref.jsonl`, `polars_default.jsonl`, `polars_ooc3072.jsonl`, `polars_ooc1024.jsonl`, `polars_ooc512.jsonl`, `validation.jsonl`, `check_outputs.py`, `repro_window_ooc.py`, `repro_60m_output.txt`, `plans.py`, `plans.txt`, `plan_*.dot`.
