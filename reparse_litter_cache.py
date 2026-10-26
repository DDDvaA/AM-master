import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import app

CATEGORY = "Pet Supplies > Cats > Litter Boxes"
COUNTRY_CURRENCY = {code: details[2] for code, details in app.COUNTRIES.items()}
RAW_ROOT = Path(r"D:\AM-master-data\raw")


def latest_pages(country):
    candidates = []
    pattern = re.compile(rf"amazon_{country}_page_(\d+)\.html$", re.I)
    for path in RAW_ROOT.glob("*/amazon_*_page_*.html"):
        match = pattern.search(path.name)
        if match:
            candidates.append((path.parent.name, int(match.group(1)), path))
    if not candidates:
        return []
    latest_folder = max(folder for folder, _page, _path in candidates)
    return [path for folder, _page, path in sorted(candidates, key=lambda x: x[1]) if folder == latest_folder]


country_rows = {}
for country, (_label, host, _currency, _language) in app.COUNTRIES.items():
    rows = []
    for html_path in latest_pages(country):
        parser = app.AmazonSearchParser(f"https://{host}")
        parser.feed(html_path.read_text(encoding="utf-8", errors="ignore"))
        for item in parser.items:
            page_currency = item.get("currency") or COUNTRY_CURRENCY[country]
            price = item.get("price")
            if page_currency != COUNTRY_CURRENCY[country]:
                price = None
            rows.append({
                "country": country,
                "category_path": CATEGORY,
                "source": "Amazon cached public search (reparsed)",
                "source_date": datetime.fromtimestamp(
                    html_path.stat().st_mtime, timezone.utc
                ).isoformat(),
                "asin": item["asin"],
                "title": item["title"],
                "brand": item.get("brand", ""),
                "price": price,
                "currency": page_currency,
                "units": None,
                "revenue": None,
                "growth": None,
                "rating": item.get("rating") if item.get("rating") is None or item.get("rating") <= 5 else None,
                "reviews": item.get("reviews"),
                "bsr_rank": None,
                "image_url": item.get("image_url", ""),
                "product_url": item.get("product_url", "") or f"https://{host}/dp/{item['asin']}",
            })
    rows = app.deduplicate_products(rows, app.MAX_PRODUCTS_PER_MARKET)
    if len(rows) != app.MAX_PRODUCTS_PER_MARKET:
        raise RuntimeError(
            f"{country} cache produced {len(rows)}/{app.MAX_PRODUCTS_PER_MARKET} products; "
            "the existing category data was not changed"
        )
    country_rows[country] = rows
    print(json.dumps({"country": country, "pages": len(latest_pages(country)), "rows": len(rows)}, ensure_ascii=False))

con = sqlite3.connect(app.DB_PATH)
try:
    con.execute("DELETE FROM products WHERE category_path=?", (CATEGORY,))
    con.commit()
finally:
    con.close()

total = 0
for rows in country_rows.values():
    total += app.save_products(rows)
print(json.dumps({"total": total}, ensure_ascii=False))
