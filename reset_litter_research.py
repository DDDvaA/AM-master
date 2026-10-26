import sqlite3
from datetime import datetime, timezone

DB = r"D:\AM-master-data\am_master.sqlite3"
CATEGORY = "Pet Supplies > Cats > Litter Boxes"

con = sqlite3.connect(DB)
product_count = con.execute("SELECT COUNT(*) FROM products WHERE category_path=?", (CATEGORY,)).fetchone()[0]
cache_count = con.execute("SELECT COUNT(*) FROM amazon_search_cache WHERE category_path=?", (CATEGORY,)).fetchone()[0]
search_count = con.execute("SELECT COUNT(*) FROM searches WHERE category_path=?", (CATEGORY,)).fetchone()[0]
con.execute("DELETE FROM products WHERE category_path=?", (CATEGORY,))
con.execute("DELETE FROM amazon_search_cache WHERE category_path=?", (CATEGORY,))
con.execute("DELETE FROM searches WHERE category_path=?", (CATEGORY,))
con.execute(
    "UPDATE analysis_runs SET finished_at=?, status='FAILED', message=? WHERE category_path=? AND status='RUNNING'",
    (datetime.now(timezone.utc).isoformat(), "解析器修复后重启并重新采集", CATEGORY),
)
con.commit()
con.close()
print({"products": product_count, "cache": cache_count, "searches": search_count})
