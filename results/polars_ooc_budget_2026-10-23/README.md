# Polars with POLARS_OOC_MEMORY_BUDGET_MB, 150M rows, 4.5 GiB cap

Run on October 23, 2026, 21:47 to 22:03 (UTC+3), on the same 8 vCPU Intel Xeon VM (16002 MiB, no swap, Linux 6.12.94) as the October 22 article run. Repo at commit `7246555` (main after PRs #1 and #2). Versions: Python 3.13.5, Polars 2.0.0 (polars-runtime-32 2.0.0), DuckDB 2.0.0, pyarrow 26.0.0, psutil 7.2.2, numpy 2.5.4. 150M input matched `data_checksums.md5`.

Prompted by Ritchie Vink's comment that only DuckDB was told about the memory limit (`memory_limit = 3GB`), and that `POLARS_OOC_MEMORY_BUDGET_MB` makes the comparison fairer.

Method unchanged: `bench.py`, fresh process per run, 4.5 GiB process-tree RSS watchdog (50 ms sampling), 1 GiB system floor, 5 GiB free / 30% CPU gate, 3 reps. Budget passed with `--env`. DuckDB reference rerun in the same session. Spark not rerun. See `run.sh`.

Other long-running work on the VM was paused for this run, but a PostgreSQL server stayed up idle, and the load average went up to 39 during the 1024 MB pass (the CPU gate passed before every run). DuckDB was 21 to 36% slower than on October 22 for the dedup and group by, so compare engines within this session, not with the article's numbers.

## Results (median wall s, finished runs, median peak RSS GiB of finished runs; range over all runs)

| Query | Article Polars default (Oct 22) | Polars default (today) | Polars budget 3072 | Polars budget 1024 | DuckDB 3GB (today) |
|---|---|---|---|---|---|
| Filter + aggregate | 0.96 s, 3/3, 0.94 | 1.02 s, 3/3, 1.14 | 1.04 s, 3/3, 1.15 | not run | 0.99 s, 3/3, 0.73 |
| Join + aggregate | 1.46 s, 3/3, 1.96 | 1.53 s, 3/3, 1.92 | 1.51 s, 3/3, 2.00 | not run | 1.69 s, 3/3, 0.37 |
| Window dedup `over(order_by)` | 0/3, killed 4.52-4.66 | 0/3, killed 4.63-4.70 | 0/3, killed 4.61-4.75 | 0/3, killed 4.63-4.83 | 10.80 s, 3/3, 3.02 |
| Sort + unique dedup (PR #1) | not in article | 0/3, killed 4.51-4.55 | 0/3, killed 4.51-4.64 | 31.28 s, 3/3, 2.29 | (window SQL above) |
| Max timestamp + sort dedup (PR #2) | not in article | 5.61 s, 3/3, 4.02 | 6.31 s, 3/3, 3.68 | not run | (window SQL above) |
| High-cardinality group by | 4.21 s, 1/3, 4.49 | 4.50 s, 3/3, 4.25 | 6.17 s, 3/3, 3.46 | 6.69 s, 3/3, 2.75 | 9.56 s, 3/3, 3.01 |

Extra: window dedup with budget 512 MB: 0/3, killed at 4.52-4.81 GiB after 9.3 to 10.6 s.

## Findings

- With a budget, Polars' high-cardinality group by finished 3/3 and used less memory (3.46 GiB at 3072, 2.75 GiB at 1024) at a cost of about 1.4x to 1.5x wall time compared with default. Even then it was faster than DuckDB in this session (6.17 s against 9.56 s).
- The window dedup `int_range(len()).over(..., order_by=...)` still exceeded 4.5 GiB at every budget tried (default, 3072, 1024, 512). With smaller budgets it ran longer before being killed (about 2 s at default, 5 to 7 s at 3072, 8 s at 1024, 9 to 11 s at 512), but process RSS still climbed past the cap. The budget does not cap total process RSS for this plan (it runs in an in-memory fallback node, see `plans/`).
- Sort + unique needed 1024 MB to fit: 3/3 at 31.28 s and 2.29 GiB. It failed at default and at 3072.
- Max timestamp + sort finished 3/3 at default (5.61 s, 4.02 GiB) and at 3072 (6.31 s, 3.68 GiB), faster than DuckDB's window query in this session (10.80 s).
- Filter and join: no meaningful change from the budget.
- Ritchie Vink said Polars main now spills the group by correctly and that this ships in the next release. PyPI's newest Polars is still 2.0.0 (also for polars-runtime-32/64/compat), `polars-nightly` was last published in September 2024, and the latest successful main CI runs had no wheel artifacts. So no build from main was tested. Recent merged Polars PRs that look relevant: #29911 "perf: Streaming OOC group-by with shuffles" (merged 2026-10-21) and #30237 "perf: Set default spill compression level to 1" (2026-10-22).

## Output checks

`check_outputs.py` compares Polars outputs with DuckDB outputs from the same session (`validation.jsonl`). The aggregate checksums for filter, join and group by matched. Every finished dedup output (sort + unique at 1024, max + sort at default and 3072) matched DuckDB's window output exactly: 14,999,347 rows, 0 missing and 0 extra under bidirectional `EXCEPT ALL`. The window dedup produced no output to check.

## Files

`duckdb_ref.jsonl`, `polars_default.jsonl`, `polars_ooc3072.jsonl`, `polars_ooc1024.jsonl`, `polars_ooc512_window.jsonl` (raw, one record per run, budget recorded as the `POLARS_OOC_MEMORY_BUDGET_MB` field), `validation.jsonl`, `host.txt`, `console.log`, `run.sh`, `check_outputs.py`. The 512 MB window run was a separate command after `run.sh`: `bench.py --sizes 150m --reps 3 --budget-gib 4.5 --engines polars --queries q3_window_latest --env POLARS_OOC_MEMORY_BUDGET_MB=512 --tag polars_ooc_budget_2026-10-23/polars_ooc512_window`.
