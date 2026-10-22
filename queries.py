"""One query set, three engines. SQL is shared by DuckDB and Spark; Polars gets the same logic as expressions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

SQL = {
    # Q1: filter + aggregate (the AWS-style scheduled rollup)
    "q1_filter_agg": """
        SELECT store_id, status, COUNT(*) AS orders, SUM(qty * price) AS revenue
        FROM sales
        WHERE ts >= TIMESTAMP '2026-06-01 00:00:00' AND status IN ('completed', 'shipped')
        GROUP BY store_id, status
    """,
    # Q2: fact-to-dimension join + group by
    "q2_join_agg": """
        SELECT p.category, p.brand, COUNT(*) AS orders,
               SUM(s.qty * s.price) AS revenue, AVG(s.price - p.list_price) AS avg_delta
        FROM sales s JOIN products p ON s.product_id = p.product_id
        WHERE s.status <> 'cancelled'
        GROUP BY p.category, p.brand
    """,
    # Q3: window function: latest order per customer (classic dedup / SCD pattern)
    "q3_window_latest": """
        SELECT customer_id, order_id, ts, qty * price AS amount
        FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY customer_id
                                         ORDER BY ts DESC, order_id DESC) AS rn
            FROM sales
        ) t
        WHERE rn = 1
    """,
    # Q4: high-cardinality aggregate: one row per customer
    "q4_highcard_agg": """
        SELECT customer_id, COUNT(*) AS orders, SUM(qty * price) AS revenue,
               MIN(ts) AS first_ts, MAX(ts) AS last_ts
        FROM sales
        GROUP BY customer_id
    """,
}


def polars_query(name: str, sales: pl.LazyFrame, products: pl.LazyFrame) -> pl.LazyFrame:
    import polars as pl
    amount = pl.col("qty").cast(pl.Float64) * pl.col("price")
    if name == "q1_filter_agg":
        return (sales.filter((pl.col("ts") >= pl.datetime(2026, 6, 1))
                             & pl.col("status").is_in(["completed", "shipped"]))
                .group_by("store_id", "status")
                .agg(pl.len().alias("orders"), amount.sum().alias("revenue")))
    if name == "q2_join_agg":
        return (sales.filter(pl.col("status") != "cancelled")
                .join(products, on="product_id", how="inner")
                .group_by("category", "brand")
                .agg(pl.len().alias("orders"), amount.sum().alias("revenue"),
                     (pl.col("price") - pl.col("list_price")).mean().alias("avg_delta")))
    if name == "q3_window_latest":
        rn = pl.int_range(pl.len()).over("customer_id", order_by=["ts", "order_id"], descending=True)
        return (sales.filter(rn == 0)
                .select("customer_id", "order_id", "ts", amount.alias("amount")))
    if name == "q3_sort_unique_latest":
        return (sales.select("customer_id", "order_id", "ts", amount.alias("amount"))
                .sort(["customer_id", "ts", "order_id"],
                      descending=[False, True, True], nulls_last=True)
                .unique("customer_id", keep="first", maintain_order=False))
    if name == "q3_max_sort_latest":
        rows = sales.select("customer_id", "order_id", "ts", amount.alias("amount"))
        timestamps = sales.group_by("customer_id").agg(pl.col("ts").max())
        latest = rows.join(timestamps, on=["customer_id", "ts"], how="semi", nulls_equal=True)
        return (latest.sort(["customer_id", "order_id"],
                            descending=[False, True], nulls_last=True)
                .unique("customer_id", keep="first", maintain_order=False))
    if name == "q4_highcard_agg":
        return (sales.group_by("customer_id")
                .agg(pl.len().alias("orders"), amount.sum().alias("revenue"),
                     pl.col("ts").min().alias("first_ts"), pl.col("ts").max().alias("last_ts")))
    raise KeyError(name)
