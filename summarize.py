"""Medians per (tag, size, query, engine) from <dir>/*.jsonl -> markdown tables on stdout.

python summarize.py [results_dir]   (default: results)
"""
import glob
import json
import os
import statistics as st
import sys
from collections import defaultdict

ORDER_E = ["duckdb", "polars", "spark"]
ORDER_Q = ["q1_filter_agg", "q2_join_agg", "q3_window_latest", "q3_sort_unique_latest", "q3_max_sort_latest", "q4_highcard_agg"]
ORDER_S = ["10m", "50m", "150m"]


def med(xs):
    return st.median(xs) if xs else None


def fmt(x, nd=2):
    return "-" if x is None else f"{x:.{nd}f}"


for path in sorted(glob.glob(os.path.join(sys.argv[1] if len(sys.argv) > 1 else "results", "*.jsonl"))):
    tag = os.path.basename(path)[:-6]
    if tag in ("smoke", "probe150"):
        continue
    recs = [json.loads(l) for l in open(path)]
    groups = defaultdict(list)
    for r in recs:
        groups[(r["size"], r["query"], r["engine"])].append(r)
    print(f"\n### {tag} ({len(recs)} runs)\n")
    print("| size | query | engine | ok/runs | wall s (median) | query s (median) | setup s (median) | peak RSS GiB (median, max) | failures |")
    print("|---|---|---|---|---|---|---|---|---|")
    keys = sorted(groups, key=lambda k: (ORDER_S.index(k[0]), ORDER_Q.index(k[1]), ORDER_E.index(k[2])))
    for k in keys:
        rs = groups[k]
        ok = [r for r in rs if r["status"] == "ok"]
        fails = sorted({r["status"].split(":")[0] + ": " + r["status"].split(":", 1)[1].strip()
                        if ":" in r["status"] else r["status"] for r in rs if r["status"] != "ok"})
        rss_all = [r["peak_rss_gib"] for r in rs]
        print(f"| {k[0]} | {k[1]} | {k[2]} | {len(ok)}/{len(rs)} | {fmt(med([r['wall_s'] for r in ok]))} | "
              f"{fmt(med([r['query_s'] for r in ok]))} | {fmt(med([r['setup_s'] for r in ok]))} | "
              f"{fmt(med([r['peak_rss_gib'] for r in ok]) if ok else None)}, {fmt(max(rss_all))} | "
              f"{'; '.join(fails) if fails else ''} |")
    pre = [r["pre_avail_gib"] for r in recs]
    busy = [r.get("pre_cpu_busy_pct", 0) for r in recs]
    loads = [r["pre_load1"] for r in recs]
    print(f"\nPre-run system state: available memory {min(pre):.1f} to {max(pre):.1f} GiB, "
          f"CPU busy {min(busy):.0f} to {max(busy):.0f}% (3 s window), load1 {min(loads):.1f} to {max(loads):.1f}. "
          f"First run {recs[0]['started']}, last run {recs[-1]['started']}.")
