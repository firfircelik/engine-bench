"""Streaming physical plan node labels (and explain()) for the three 150M dedup queries, as in queries.py. No execution."""
import os, re, sys
os.environ.setdefault("POLARS_MAX_THREADS", "8")
import polars as pl
sys.path.insert(0, os.getcwd())
from queries import polars_query
s, p = pl.scan_parquet("data/sales_150m/*.parquet"), pl.scan_parquet("data/products.parquet")
from polars._utils.polars_version import get_polars_build_commit
print(f"polars {pl.__version__} build commit {get_polars_build_commit()}")
for q in ["q3_window_latest", "q3_sort_unique_latest", "q3_max_sort_latest", "q4_highcard_agg"]:
    lf = polars_query(q, s, p)
    dot = lf.show_graph(engine="streaming", plan_stage="physical", raw_output=True, show=False)
    labels = [l.split("\\n")[0] for l in re.findall(r'label="((?:[^"\\]|\\.)*)"', dot)]
    print(f"\n== {q}\nphysical streaming nodes (top to bottom): {labels}")
    print("in-memory fallback node present:", any("in-memory" in l for l in labels))
    print("explain():\n" + lf.explain())
    open(f"plan_{q}.dot", "w").write(dot)
