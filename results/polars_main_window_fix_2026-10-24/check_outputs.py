"""Compare Polars 150m outputs with DuckDB outputs (exact for dedup, checksums for aggregates)."""
import json, sys, os, duckdb
os.chdir(sys.argv[1]); phase = sys.argv[2]
con = duckdb.connect()
CHECK = {
 "q1_filter_agg": "COUNT(*), SUM(orders), ROUND(SUM(revenue), 0)",
 "q2_join_agg": "COUNT(*), SUM(orders), ROUND(SUM(revenue), 0), ROUND(SUM(avg_delta), 3)",
 "q4_highcard_agg": "COUNT(*), SUM(orders), ROUND(SUM(revenue), 0), MIN(first_ts), MAX(last_ts)",
}
res = {"phase": phase}
d = lambda q: f"read_parquet('out/duckdb/150m_{q}.parquet')"
p = lambda q: f"read_parquet('out/polars/150m_{q}.parquet')"
for q, e in CHECK.items():
    try:
        a = con.execute(f"SELECT {e} FROM {d(q)}").fetchone(); b = con.execute(f"SELECT {e} FROM {p(q)}").fetchone()
        res[q] = {"match": str(a) == str(b), "duckdb": str(a), "polars": str(b)}
    except Exception as ex: res[q] = {"match": None, "error": str(ex)[:200]}
for q in ["q3_window_latest", "q3_sort_unique_latest", "q3_max_sort_latest"]:
    try:
        cols = "customer_id, order_id, ts, amount"
        miss = con.execute(f"SELECT COUNT(*) FROM (SELECT {cols} FROM {d('q3_window_latest')} EXCEPT ALL SELECT {cols} FROM {p(q)})").fetchone()[0]
        extra = con.execute(f"SELECT COUNT(*) FROM (SELECT {cols} FROM {p(q)} EXCEPT ALL SELECT {cols} FROM {d('q3_window_latest')})").fetchone()[0]
        n = con.execute(f"SELECT COUNT(*) FROM {p(q)}").fetchone()[0]
        res[q] = {"match": miss == 0 and extra == 0, "rows": n, "missing": miss, "extra": extra}
    except Exception as ex: res[q] = {"match": None, "error": str(ex)[:200]}
print(json.dumps(res))
with open("results/polars_main_window_fix_2026-10-24/validation.jsonl", "a") as f: f.write(json.dumps(res) + "\n")
