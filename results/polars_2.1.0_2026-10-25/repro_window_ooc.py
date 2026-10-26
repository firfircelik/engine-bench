"""Minimal repro: a latest-row-per-key window inside filter() is not bounded by POLARS_OOC_MEMORY_BUDGET_MB.

Pure Python (numpy, polars, psutil). Generates synthetic Parquet in a temp dir, then runs each
variant in a fresh subprocess with the budget set before `import polars`, sinks to Parquet with
the streaming engine, and samples the child's peak RSS every 20 ms.

    python repro_window_ooc.py [--rows 30000000] [--budgets unset,1024,256] [--threads 8]

Variants (same input, same budget):
  window_in_filter   lf.filter(int_range(len()).over(k, order_by=[ts, o], descending=True) == 0)
  window_in_columns  same window via with_columns(rn=...), then filter(rn == 0)
  group_by           group_by(k).agg(len, sum(amount), min(ts), max(ts)), one row per key, about rows/10 groups
"""
import argparse, os, re, shutil, subprocess, sys, tempfile, time

VARIANTS = ["window_in_filter", "window_in_columns", "group_by"]


def build(variant, src):
    import polars as pl
    lf = pl.scan_parquet(os.path.join(src, "*.parquet"))
    rn = pl.int_range(pl.len()).over("customer_id", order_by=["ts", "order_id"], descending=True)
    if variant == "window_in_filter":
        return lf.filter(rn == 0)
    if variant == "window_in_columns":
        return lf.with_columns(rn.alias("rn")).filter(pl.col("rn") == 0).drop("rn")
    if variant == "group_by":
        return lf.group_by("customer_id").agg(pl.len().alias("n"), pl.col("amount").sum(),
                                              pl.col("ts").min().alias("first_ts"), pl.col("ts").max().alias("last_ts"))
    raise KeyError(variant)


def child(variant, src, out):
    import polars as pl
    t = time.perf_counter()
    build(variant, src).sink_parquet(out)
    rows = pl.scan_parquet(out).select(pl.len()).collect().item()
    print(f"RESULT rows={rows} secs={time.perf_counter() - t:.2f}", flush=True)


def physical_nodes(variant, src):
    dot = build(variant, src).show_graph(engine="streaming", plan_stage="physical", raw_output=True, show=False)
    return [l.split("\\n")[0] for l in re.findall(r'label="((?:[^"\\]|\\.)*)"', dot)]


def gen(src, rows, seed=0):
    import numpy as np, polars as pl
    os.makedirs(src, exist_ok=True)
    chunk = 5_000_000
    for i, lo in enumerate(range(0, rows, chunk)):
        n = min(chunk, rows - lo)
        rng = np.random.default_rng([seed, i])
        pl.DataFrame({
            "order_id": np.arange(lo, lo + n, dtype=np.int64),
            "customer_id": rng.integers(0, rows // 10, n, dtype=np.int32),
            "ts": rng.integers(0, 270 * 24 * 3600, n, dtype=np.int64),
            "amount": rng.uniform(1, 500, n),
        }).write_parquet(os.path.join(src, f"part-{i:04d}.parquet"))


def run(variant, src, out, budget_mb, threads, kill_gib):
    import psutil
    env = dict(os.environ, POLARS_MAX_THREADS=str(threads))
    if budget_mb:
        env["POLARS_OOC_MEMORY_BUDGET_MB"] = str(budget_mb)
    proc = subprocess.Popen([sys.executable, __file__, "--child", variant, src, out],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    p, peak, killed = psutil.Process(proc.pid), 0, False
    while proc.poll() is None:
        try:
            peak = max(peak, p.memory_info().rss)
        except psutil.NoSuchProcess:
            break
        if peak > kill_gib * 1024 ** 3:  # safety valve so the repro cannot take the machine down
            proc.kill(); killed = True
            break
        time.sleep(0.02)
    so, se = proc.communicate()
    res = next((l[7:] for l in so.splitlines() if l.startswith("RESULT ")), None)
    status = f"KILLED above {kill_gib} GiB" if killed else (res or "error: " + se.strip()[-300:])
    return peak / 1024 ** 3, status


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        return child(*sys.argv[2:5])
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=30_000_000)
    ap.add_argument("--budgets", default="unset,1024,256", help="comma list of POLARS_OOC_MEMORY_BUDGET_MB values; 'unset' = not set")
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--kill-gib", type=float, default=6.0)
    ap.add_argument("--reps", type=int, default=1)
    a = ap.parse_args()
    import polars as pl
    pl.show_versions()
    tmp = tempfile.mkdtemp(prefix="polars_ooc_repro_")
    try:
        src = os.path.join(tmp, "src")
        gen(src, a.rows)
        size = sum(os.path.getsize(os.path.join(src, f)) for f in os.listdir(src)) / 1024 ** 2
        print(f"\nrows={a.rows:,} keys~{a.rows // 10:,} parquet={size:.0f} MiB "
              f"POLARS_OOC_MEMORY_BUDGET_MB in {a.budgets} POLARS_MAX_THREADS={a.threads}\n")
        for v in VARIANTS:
            print(f"{v:18s} physical plan nodes (top to bottom): {physical_nodes(v, src)}")
        print()
        for rep in range(a.reps):
            for v in VARIANTS:
                for budget in [None if b == "unset" else int(b) for b in a.budgets.split(",")]:
                    peak, status = run(v, src, os.path.join(tmp, f"{v}.parquet"), budget, a.threads, a.kill_gib)
                    print(f"{v:18s} budget={str(budget or 'unset'):>5s} peak_rss={peak:5.2f} GiB  {status}", flush=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
