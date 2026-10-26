import json
import sqlite3

DB = r"D:\AM-master-data\am_master.sqlite3"
CATEGORY = "Pet Supplies > Cats > Litter Boxes"

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
products = [
    dict(row)
    for row in con.execute(
        """
        SELECT country, COUNT(*) AS products,
               SUM(CASE WHEN price IS NOT NULL THEN 1 ELSE 0 END) AS priced,
               GROUP_CONCAT(DISTINCT currency) AS currencies,
               MAX(source_date) AS latest
        FROM products WHERE category_path=? GROUP BY country ORDER BY country
        """,
        (CATEGORY,),
    )
]
runs = [
    dict(row)
    for row in con.execute(
        "SELECT * FROM analysis_runs WHERE category_path=? ORDER BY started_at DESC LIMIT 5",
        (CATEGORY,),
    )
]
review_count = con.execute(
    """
    SELECT COUNT(*) FROM reviews r
    WHERE EXISTS (
      SELECT 1 FROM products p
      WHERE p.country=r.country AND p.asin=r.asin AND p.category_path=?
    )
    """,
    (CATEGORY,),
).fetchone()[0]
print(json.dumps({"products": products, "runs": runs, "review_count": review_count}, ensure_ascii=False, indent=2))
