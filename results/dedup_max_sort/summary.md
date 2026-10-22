
### comparison (6 runs)

| size | query | engine | ok/runs | wall s (median) | query s (median) | setup s (median) | peak RSS GiB (median, max) | failures |
|---|---|---|---|---|---|---|---|---|
| 150m | q3_sort_unique_latest | polars | 3/3 | 80.56 | 80.30 | 0.12 | 2.68, 2.80 |  |
| 150m | q3_max_sort_latest | polars | 3/3 | 14.23 | 14.00 | 0.13 | 3.99, 4.04 |  |

Pre-run system state: available memory 13.1 to 13.5 GiB, CPU busy 0 to 1% (3 s window), load1 8.2 to 15.1. First run 2026-10-22T13:47:54, last run 2026-10-22T13:52:05.

### duckdb (1 runs)

| size | query | engine | ok/runs | wall s (median) | query s (median) | setup s (median) | peak RSS GiB (median, max) | failures |
|---|---|---|---|---|---|---|---|---|
| 150m | q3_window_latest | duckdb | 1/1 | 18.50 | 18.24 | 0.10 | 3.04, 3.04 |  |

Pre-run system state: available memory 14.4 to 14.4 GiB, CPU busy 2 to 2% (3 s window), load1 1.1 to 1.1. First run 2026-10-22T13:43:20, last run 2026-10-22T13:43:20.
