# Polars max timestamp + sort, 150M rows

[Linux run](https://github.com/Vleyked/engine-bench/actions/runs/39765017037), October 22, 2026. Ubuntu 24.04, 4 vCPUs (AMD EPYC 7763), 15983 MiB RAM, no swap, 8 engine threads. Python 3.13.5 and pinned versions are in [host.txt](host.txt).

`q3_max_sort_latest` filters to each customer's maximum timestamp with a semi join, then sorts only the candidates to break timestamp ties by order ID. The original `bench.py` and `run_engine.py` are unchanged: fresh processes, Parquet in/out, 4.5 GiB process-tree RSS cap sampled every 50 ms, 1 GiB system-memory floor, and the usual memory/CPU gate. Each query ran three times on the same runner, reversing order in the second pair.

| Query | Spill budget | Finished | Wall seconds, median | Peak RSS GiB, range |
|---|---|---|---|---|
| Sort + unique | 1024 MB | 3/3 | 80.56 | 2.47–2.80 |
| Max timestamp + sort | default | 3/3 | 14.23 | 3.99–4.04 |
| DuckDB window reference | 3 GB engine limit | 1/1 | 18.50 | 3.04 |

The new query was 5.7x faster than sort + unique in these paired runs, using more memory but staying under the cap. The earlier 90.58 s result came from a different runner. DuckDB was run once to produce the reference output; this is not a repeated cross-engine comparison.

All 33 generated input files matched the repository's MD5s. Every screening and repeated output was compared to DuckDB with bidirectional `EXCEPT ALL`: 14,999,347 rows, zero missing or extra rows. Tests also cover empty inputs, nulls, negative values, timestamp ties and duplicate winners across files.

- [comparison.jsonl](comparison.jsonl), [summary.md](summary.md), [validation.json](validation.json)
- [duckdb.jsonl](duckdb.jsonl), [checksums.txt](checksums.txt)
- [Screening records and checks](screening): max timestamp + sort and a two-stage max + semi-join alternative, one run each at default/3072/2048/1024 MB. All passed; default max + sort was selected for repeated comparison. The tiny difference between the two formulations in screening is not evidence of a meaningful speed difference.
- [Workflow and validation script](https://github.com/Vleyked/engine-bench/tree/611012d50873c4d3207c413010766ec7607b4677) preserve both candidates and the exact experiment.

Reproduce the retained query with default Polars memory settings:

```bash
python bench.py --sizes 150m --reps 3 --engines polars \
  --queries q3_max_sort_latest --budget-gib 4.5 --tag dedup_max_sort_run
python -m unittest discover -s tests -v
python summarize.py results/dedup_max_sort
```

Results are specific to this Linux host and data distribution. The existing harness initializes `min_sys_avail` to 1e9 bytes, capping that recorded field at 0.93 GiB; RSS measurements and watchdog checks are unaffected.
