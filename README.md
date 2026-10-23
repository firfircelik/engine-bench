# engine-bench: DuckDB 2.0 vs Polars vs Spark on one machine

Scripts, raw results and query plans behind the article
[DuckDB 2.0 vs Polars vs Spark on One Machine: 150M Rows Under a 4.5 GiB Cap](https://dev.to/firfircelik/duckdb-20-vs-polars-vs-spark-on-one-machine-150m-rows-under-a-45-gib-cap-h38).

**Thesis:** on one 8 vCPU machine with a 4.5 GiB process memory cap, DuckDB finished every query at every size, local Spark finished almost everything 5x to 12x slower, and Polars was fast until its window dedup at 150M rows did not fit.

The top-level files in `results/` and `results_duckdb156/` are the raw output of the runs the article reports. Follow-up experiments are kept in separate subdirectories; the original records are unchanged.

## Setup

- **Machine:** 8 vCPU Intel Xeon, 15 GiB RAM (16002 MiB), no swap, Linux 6.12. A shared VM, so other processes were running. Every run waited until at least 5 GiB was free and CPU busy was under 30% over a 3 second window (`bench.py`, `wait_for_room`).
- **Versions:** Python 3.13.5, OpenJDK 21.0.12.1, DuckDB 2.0.0, Polars 2.0.0, PySpark 4.2.0, pyarrow 26.0.0. The "before" run used DuckDB 1.5.6. Details and sources in [VERSIONS.md](VERSIONS.md).
- **Data:** seeded synthetic star schema (`gen_data.py`, `SEED = 20261019`): a `sales` fact table and a 50,000-row `products` dimension. 10M rows (213 MB), 50M (1.1 GB), 150M (3.2 GB of snappy Parquet, 30 files of 5M rows). About 10 orders per customer.
- **Queries** (`queries.py`, same SQL for DuckDB and Spark, same logic as Polars expressions):
  1. `q1_filter_agg`: filter on timestamp and status, group by store and status.
  2. `q2_join_agg`: fact to dimension join, group by category and brand.
  3. `q3_window_latest`: latest order per customer with `ROW_NUMBER()` (dedup / SCD pattern).
  4. `q4_highcard_agg`: one row per customer (about 15M groups at 150M).
- **How each engine runs** (`run_engine.py`), always Parquet in and Parquet out:
  - DuckDB: `COPY (SQL) TO 'out.parquet'`, `SET memory_limit = '3GB'`, `threads = 8`.
  - Polars: `LazyFrame.sink_parquet()` on the streaming engine, `POLARS_MAX_THREADS=8`, default memory settings.
  - Spark: `spark.sql(...).write.parquet()`, `local[8]`, `spark.driver.memory = 3g`, UI off, UTC session time zone.
- **Method** (`bench.py`):
  - One fresh process per run: interpreter start, import, session, read, compute, write.
  - Engines run strictly one at a time; engine order rotates per repetition.
  - 5 repetitions at 10M, 3 at 50M and 150M. Reported numbers are **medians**.
  - A watchdog samples the RSS of the whole process tree every 50 ms and kills the run above **4.5 GiB** (`--budget-gib`), or if system available memory drops under 1 GiB (`--floor-gib`).
  - **Wall** is the whole process. **Query** is read, compute and write only (`query_s`). The difference is setup (`setup_s`).

## Reproduce

Native install, no containers. You need Python 3.13 and a Java 21 runtime on `PATH` (for Spark).

```bash
git clone https://github.com/firfircelik/engine-bench.git
cd engine-bench
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
java -version   # OpenJDK 21 in the original runs

# 1. Generate data (deterministic). 10M is enough to start; 150M needs about 3.2 GB of disk.
.venv/bin/python gen_data.py 10
.venv/bin/python gen_data.py 50
.venv/bin/python gen_data.py 150
md5sum -c data_checksums.md5   # optional: compare with the files the benchmark used

# 2. Keep the published results apart; the scripts append to results/*.jsonl
mv results results_published && mkdir results

# 3a. One engine, one size, with the same 4.5 GiB process-tree cap
.venv/bin/python bench.py --sizes 10m --reps 5 --engines polars --budget-gib 4.5 --tag mine

# 3b. Or the full plan the article used (takes a while at 150M)
./run_duckdb2.sh > results/run_duckdb2.log 2>&1

# 4. Medians as markdown tables
.venv/bin/python summarize.py results

# 5. Check every engine produced the same answer (needs the out/ files from step 3)
.venv/bin/python validate.py 150m
```

Useful `bench.py` flags: `--engines duckdb,polars,spark`, `--queries q3_window_latest`, `--mem 1g` (DuckDB `memory_limit` and Spark driver memory), `--budget-gib`, `--min-avail-gib`, `--max-busy-pct`, `--env KEY=VAL` (for example `DUCKDB_NO_ORDER=1` or `POLARS_OOC_MEMORY_BUDGET_MB=3072`). `bench.py` uses `$BENCH_PYTHON` if set, else `./.venv/bin/python`, else the interpreter running it. The shell scripts take `PY=...` the same way.

Spark spill and DuckDB temp files go to `out/tmp/<engine>`, outputs to `out/<engine>/`. Both are ignored by git.

## Results at 150M rows (DuckDB 2.0.0, October 22, 2026)

From [summary_duckdb200.md](summary_duckdb200.md), `main` tag. Median wall seconds, finished runs under the 4.5 GiB cap in brackets.

| Query | DuckDB 2.0.0 | Polars 2.0.0 | PySpark 4.2.0 |
|---|---|---|---|
| Filter + aggregate | **0.87 s** (3/3) | 0.96 s (3/3) | 10.77 s (3/3) |
| Join + aggregate | 1.47 s (3/3) | **1.46 s** (3/3) | 16.10 s (3/3) |
| Window dedup | **7.92 s** (3/3) | killed (0/3) | 46.29 s (2/3) |
| High-cardinality group by | 7.91 s (3/3) | **4.21 s** (1/3) | 39.70 s (3/3) |

Peak process-tree RSS, median of finished runs:

| Query | DuckDB 2.0.0 | Polars 2.0.0 | PySpark 4.2.0 |
|---|---|---|---|
| Filter + aggregate | 0.77 GiB | 0.94 GiB | 1.85 GiB |
| Join + aggregate | 0.42 GiB | 1.96 GiB | 1.61 GiB |
| Window dedup | 3.01 GiB | above 4.5 (killed at 4.52 to 4.66) | 3.74 GiB, one run hit 7.51 |
| High-cardinality group by | 3.01 GiB | 4.49 GiB | 4.40 GiB |

DuckDB with `memory_limit = 1GB`, 150M rows (`duckdb1g`, `duckdb1g_noorder` tags):

| Query | Wall (median) | Peak RSS | Finished |
|---|---|---|---|
| Window dedup | 14.97 s | 1.12 GiB | 3/3 |
| High-cardinality group by | 13.94 s | 1.08 GiB | 3/3 |
| Window dedup, `preserve_insertion_order = false` | 14.94 s | 1.12 GiB | 3/3 |
| Group by, `preserve_insertion_order = false` | 13.88 s | 1.08 GiB | 3/3 |

Polars 150M window dedup, every attempt:

| Setting | Result | File |
|---|---|---|
| Default, 4.5 GiB cap (Oct 22) | 0/3, killed at 4.52 to 4.66 GiB | `results/main.jsonl` |
| `POLARS_OOC_MEMORY_BUDGET_MB=3072`, 4.5 GiB cap (Oct 22) | 0/3, killed at 4.57 to 4.66 GiB | `results/polars_ooc3g.jsonl` |
| Default, 9 GiB cap (Oct 19, same Polars 2.0.0) | 0/3, killed at 9.04 to 9.54 GiB | `results_duckdb156/needs150.jsonl` |

`POLARS_OOC_MEMORY_BUDGET_MB` is a variable I found in the Polars 2.0.0 source, not a documented setting. Treat that row as "I tried", not as guidance.

All sizes (10M, 50M, 150M), query-only and setup times, and pre-run system state are in [summary_duckdb200.md](summary_duckdb200.md). The DuckDB 1.5.6 run is in [summary_duckdb156.md](summary_duckdb156.md).

## Raw results

One JSON object per run, appended as the run finished.

| File | What |
|---|---|
| `results/main.jsonl` | Oct 22, 132 runs: 3 engines x 4 queries x 10M (5 reps), 50M and 150M (3 reps), 4.5 GiB cap |
| `results/duckdb1g.jsonl` | Oct 22, DuckDB 2.0.0 at 150M with `memory_limit = 1GB` |
| `results/duckdb1g_noorder.jsonl` | same, plus `preserve_insertion_order = false` |
| `results/polars_ooc3g.jsonl` | Oct 22, Polars at 150M with `POLARS_OOC_MEMORY_BUDGET_MB=3072` |
| `results/host.txt`, `results/run_duckdb2.log` | host info and console log of the Oct 22 run |
| `results_duckdb156/` | Oct 19 run with DuckDB 1.5.6: same files, plus `needs150.jsonl` (Polars and Spark at 150M with a 9 GiB cap), `smoke.jsonl` and `probe150.*` (early checks, excluded from the summaries), `versions.txt` |

Fields: `engine`, `size`, `query`, `mem`, `wall_s`, `query_s`, `setup_s`, `peak_rss_gib` (process tree), `min_sys_avail_gib`, `rows_out`, `version`, `status` (`ok` or the watchdog reason), `stderr_tail` on failure, `rep`, `pre_avail_gib`, `pre_load1`, `pre_cpu_busy_pct`, `started` (local time, UTC+3), plus any `--env` keys.

## Query plans for the window dedup

[`plans/`](plans) holds the plans for `q3_window_latest` on the 10M data, produced by `plans/make_plans.py`. No timing was done for these.

- [`plans/polars_dedup_explain.txt`](plans/polars_dedup_explain.txt): `explain()`, `explain(optimized=False)`, `explain(engine="streaming")` and the streaming **physical** plan from `show_graph(engine="streaming", plan_stage="physical", raw_output=True)`. (`explain(streaming=True)` was removed in Polars 2.0.)
- [`plans/polars_dedup_physical_streaming.dot`](plans/polars_dedup_physical_streaming.dot): the same physical plan as Graphviz DOT.
- [`plans/duckdb_dedup_explain.txt`](plans/duckdb_dedup_explain.txt): DuckDB 2.0.0 `EXPLAIN` for the same SQL.

What the Polars physical plan shows: the scan and the projections run as streaming nodes, but the `int_range(pl.len()).over("customer_id", order_by=[...])` window runs in an `in-memory-map` node, which Polars' own legend marks as **in-memory engine fallback**, behind a `multiplexer` node marked **potentially memory-intensive**. That fits what the runs measured (memory not bounded by streaming), but I have not profiled where the memory goes inside that node.

```bash
.venv/bin/python gen_data.py 10
.venv/bin/python plans/make_plans.py
dot -Tsvg plans/polars_dedup_physical_streaming.dot -o plans/polars_dedup.svg   # if Graphviz is installed
```

## Alternative Polars dedup

`q3_max_sort_latest` first finds each customer's maximum timestamp and uses a semi join to keep matching rows. It then sorts those candidates by customer and descending order ID and keeps one row per customer. This avoids sorting all 150M rows. Its [physical plan on the 10M data](plans/polars_max_sort_physical_streaming.dot) has no in-memory fallback.

At 150M rows it finished 3/3 Linux runs with default Polars memory settings: **14.23 s median**, 3.99–4.04 GiB peak RSS, under the same 4.5 GiB cap. Sort + unique took 80.56 s median on that runner with its 1024 MB spill budget. Every output matched DuckDB row for row. [Raw results, host and validation](results/dedup_max_sort/README.md).

The original window query and `q3_sort_unique_latest` remain available for comparison. The latter sorts all rows and needed `POLARS_OOC_MEMORY_BUDGET_MB=1024` to fit on the [first Linux run](results/dedup_linux/README.md), taking 90.58 s median. Its [Windows trials](results/dedup_windows/README.md) exceeded the cap.

```bash
python bench.py --sizes 150m --reps 3 --engines polars \
  --queries q3_max_sort_latest --budget-gib 4.5 --tag dedup_max_sort_run
python -m unittest discover -s tests -v
```

The follow-up results are specific to the recorded Linux hosts. The spill budget used for sort + unique is undocumented and does not cap total process RSS.

## Update (Oct 23): Polars with an out-of-core budget

Ritchie Vink (Polars) pointed out that only DuckDB was told about the memory limit (`memory_limit = 3GB`), so Polars did not know it should stay under 4 GiB, and suggested `POLARS_OOC_MEMORY_BUDGET_MB` for a fairer comparison. On October 23, 2026 I reran every Polars query at 150M rows with that budget, on the same VM, with the same harness and 4.5 GiB cap, plus a same-session Polars default and DuckDB reference. Median wall seconds, finished runs out of 3, median peak RSS of finished runs (range at kill for failed runs):

| Query | Polars default | Polars 3072 MB | Polars 1024 MB | DuckDB 3GB |
|---|---|---|---|---|
| Filter + aggregate | 1.02 s, 3/3, 1.14 GiB | 1.04 s, 3/3, 1.15 GiB | not run | 0.99 s, 3/3, 0.73 GiB |
| Join + aggregate | 1.53 s, 3/3, 1.92 GiB | 1.51 s, 3/3, 2.00 GiB | not run | 1.69 s, 3/3, 0.37 GiB |
| Window dedup `over(order_by)` | 0/3, killed 4.63-4.70 | 0/3, killed 4.61-4.75 | 0/3, killed 4.63-4.83 | 10.80 s, 3/3, 3.02 GiB |
| Sort + unique dedup | 0/3, killed 4.51-4.55 | 0/3, killed 4.51-4.64 | 31.28 s, 3/3, 2.29 GiB | |
| Max timestamp + sort dedup | 5.61 s, 3/3, 4.02 GiB | 6.31 s, 3/3, 3.68 GiB | not run | |
| High-cardinality group by | 4.50 s, 3/3, 4.25 GiB | 6.17 s, 3/3, 3.46 GiB | 6.69 s, 3/3, 2.75 GiB | 9.56 s, 3/3, 3.01 GiB |

The window dedup was also 0/3 with a 512 MB budget (killed at 4.52-4.81 GiB). Every finished dedup output matched DuckDB row for row (14,999,347 rows).

Caveats: other work on the VM was paused, but an idle PostgreSQL server stayed up and the load average rose during part of the run (the CPU gate passed before every run). DuckDB was 21 to 36% slower on the dedup and group by than on October 22, so compare engines within this session, not with the October 22 tables. Only Polars 2.0.0 was tested: it is still the newest release on PyPI and no wheel from Polars main was available. The Polars changes that look relevant, [#29911](https://github.com/pola-rs/polars/pull/29911) (streaming out-of-core group by with shuffles) and [#30237](https://github.com/pola-rs/polars/pull/30237) (default spill compression level 1), are merged on main but not released yet. I will rerun when the next Polars release ships.

Details, raw results and output checks: [results/polars_ooc_budget_2026-10-23/README.md](results/polars_ooc_budget_2026-10-23/README.md).

## Known limitations

- **The original runs tested one Polars formulation of the dedup:** `filter(int_range(len()).over(..., order_by=..., descending=True) == 0)`, the direct translation of the SQL. Other formulations may stream better and were not measured in those runs, for example:
  - `sort(["customer_id", "ts", "order_id"], descending=[False, True, True]).unique("customer_id", keep="first", maintain_order=False)`
  - `group_by("customer_id").agg(pl.all().sort_by(["ts", "order_id"]).last())`
  - `group_by("customer_id").agg(pl.all().top_k_by(["ts", "order_id"], k=1))` or a `max_by` style aggregation
  - a `ts`/`order_id` max per customer followed by a semi join back to the fact table

  PRs that add these to `queries.py` (as new query names, so the original stays comparable) and run them under the same `--budget-gib 4.5` cap are welcome. Please include your `results/*.jsonl`, `host.txt` and versions.
- **One shared VM.** Other processes were running. Runs were gated on free memory and CPU, and the gate values are recorded per run, but treat differences under about 10 to 15% as noise. The DuckDB 1.5.6 and 2.0.0 runs were three days apart.
- **Single node only, and small on purpose.** The largest input is 3.2 GB of Parquet. This says nothing about multi-node Spark, Databricks or Fabric, or governed Delta writes.
- **Spark pays its JVM start every run** (about 5 s). That is the point of the fresh-process method, but it is not how a warm cluster behaves. `query_s` in the raw data isolates the query part.
- **Engine memory settings are left mostly at defaults.** Spark has `driver.memory = 3g` and nothing else tuned; Polars has no memory setting apart from the out-of-core budget runs (October 22, and the October 23 update above).
- **Validation needs the outputs.** `validate.py` compares row counts and rounded checksums of the Parquet outputs in `out/`, which are not in this repo. In the original runs all engines matched wherever they produced output.
- **numpy was not logged** at run time. With numpy 2.5.4 and pyarrow 26.0.0 the 10M data regenerates byte-identical; see [VERSIONS.md](VERSIONS.md) and `data_checksums.md5`.

## Changes from the scripts as they ran

Only paths, nothing in the benchmark logic:

- `bench.py`: the engine interpreter is `$BENCH_PYTHON`, else `./.venv/bin/python`, else the current interpreter (originally hardcoded to `./.venv/bin/python`).
- `run_*.sh`: `PY` can be overridden from the environment.
- `gen_data.py`: creates `data/` if it does not exist.
- `summarize.py`: takes the results directory as an optional argument (default `results`).
- Logs: the absolute path of the original working directory was removed from `wrote ...` lines.

## License

MIT, see [LICENSE](LICENSE). Copyright (c) 2026 Firat Celik.
