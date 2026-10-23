#!/bin/bash
set -u
cd /workspace/engine-bench-latest
PY=.venv/bin/python
R=polars_ooc_budget_2026-10-23
B="--sizes 150m --reps 3 --budget-gib 4.5"
ALLQ=q1_filter_agg,q2_join_agg,q3_window_latest,q3_sort_unique_latest,q3_max_sort_latest,q4_highcard_agg
{ date; uname -a; nproc; free -m; lscpu | grep -E "Model name|^CPU\(s\)"; $PY -c "import sys,duckdb,polars,pyarrow,psutil,numpy;print(sys.version);print('duckdb',duckdb.__version__,'polars',polars.__version__,'pyarrow',pyarrow.__version__,'psutil',psutil.__version__,'numpy',numpy.__version__)"; $PY -m pip list 2>/dev/null | grep -i polars; git rev-parse HEAD; } > results/$R/host.txt 2>&1
echo "== duckdb ref"; $PY bench.py $B --engines duckdb --queries q1_filter_agg,q2_join_agg,q3_window_latest,q4_highcard_agg --tag $R/duckdb_ref
echo "== polars ooc3072"; $PY bench.py $B --engines polars --queries $ALLQ --env POLARS_OOC_MEMORY_BUDGET_MB=3072 --tag $R/polars_ooc3072
$PY /workspace/eb_check.py . polars_ooc3072
echo "== polars default same session"; $PY bench.py $B --engines polars --queries $ALLQ --tag $R/polars_default
$PY /workspace/eb_check.py . polars_default
echo "== polars ooc1024"; $PY bench.py $B --engines polars --queries q3_window_latest,q4_highcard_agg,q3_sort_unique_latest --env POLARS_OOC_MEMORY_BUDGET_MB=1024 --tag $R/polars_ooc1024
$PY /workspace/eb_check.py . polars_ooc1024
echo ALLDONE
