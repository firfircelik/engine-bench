#!/bin/bash
# Polars built from main (see host.txt for the commit) vs the Oct 23 Polars 2.0.0 runs. Same harness and cap.
set -u
cd /workspace/engine-bench-latest
export BENCH_PYTHON=/workspace/polars-main-venv/bin/python
PY=$BENCH_PYTHON
R=polars_main_window_fix_2026-10-24
D=results/$R
B="--sizes 150m --reps 3 --budget-gib 4.5"
ALLQ=q1_filter_agg,q2_join_agg,q3_window_latest,q3_sort_unique_latest,q3_max_sort_latest,q4_highcard_agg
SUBQ=q3_window_latest,q3_sort_unique_latest,q4_highcard_agg
{ date; uname -a; nproc; free -m; lscpu | grep -E "Model name|^CPU\(s\)"; $PY -c "import sys,duckdb,polars,pyarrow,psutil,numpy;print(sys.version);print('duckdb',duckdb.__version__,'polars',polars.__version__,'pyarrow',pyarrow.__version__,'psutil',psutil.__version__,'numpy',numpy.__version__)"; $PY -c "import polars; polars.show_versions()"; $PY -m pip list 2>/dev/null | grep -i polars; echo "polars source: github.com/pola-rs/polars main @ $(git -C /workspace/polars-main rev-parse HEAD)"; git -C /workspace/polars-main log -1 --format='  %s (%cI)'; echo "engine-bench @ $(git rev-parse HEAD)"; md5sum -c data_checksums.md5 2>&1 | grep -E "150m|products" | grep -vc ": OK$" | sed 's/^/150m+products checksum mismatches: /'; } > $D/host.txt 2>&1
echo "== plans"; $PY $D/plans.py > $D/plans.txt 2>&1; mv plan_*.dot $D/ 2>/dev/null
echo "== repro 60M"; $PY $D/repro_window_ooc.py --rows 60000000 --budgets unset,1024,256 > $D/repro_60m_output.txt 2>&1; grep -E "budget=|nodes" $D/repro_60m_output.txt
echo "== duckdb ref"; $PY bench.py $B --engines duckdb --queries q1_filter_agg,q2_join_agg,q3_window_latest,q4_highcard_agg --tag $R/duckdb_ref
for cfg in default 3072 1024 512; do
  rm -f out/polars/150m_*.parquet
  if [ $cfg = default ]; then echo "== polars default"; $PY bench.py $B --engines polars --queries $ALLQ --tag $R/polars_default
  else Q=$SUBQ; [ $cfg = 3072 ] && Q=$ALLQ; echo "== polars ooc$cfg"; $PY bench.py $B --engines polars --queries $Q --env POLARS_OOC_MEMORY_BUDGET_MB=$cfg --tag $R/polars_ooc$cfg; fi
  $PY $D/check_outputs.py . polars_$cfg
done
echo ALLDONE
