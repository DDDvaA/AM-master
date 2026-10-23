from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill


ROOT = Path(__file__).resolve().parent
STATIC = (ROOT / "static").resolve()
DEFAULT_DATA = Path(r"D:\AM-master-data") if os.name == "nt" else ROOT / "data"
DATA_DIR = Path(os.environ.get("AM_MASTER_DATA_DIR", str(DEFAULT_DATA))).expanduser()
DB_PATH = DATA_DIR / "am_master.sqlite3"
RAW_DIR = DATA_DIR / "raw"
PORT = int(os.environ.get("AM_MASTER_PORT", "8777"))
MAX_PRODUCTS_PER_MARKET = 100
MAX_SEARCH_PAGES = 10
_DB_INIT_LOCK = threading.Lock()
_INITIALIZED_DATABASES = set()
COUNTRIES = {
    "US": ("美国", "www.amazon.com", "USD", "en-US,en;q=0.9"),
    "CA": ("加拿大", "www.amazon.ca", "CAD", "en-CA,en;q=0.9"),
    "UK": ("英国", "www.amazon.co.uk", "GBP", "en-GB,en;q=0.9"),
    "DE": ("德国", "www.amazon.de", "EUR", "de-DE,de;q=0.9"),
    "FR": ("法国", "www.amazon.fr", "EUR", "fr-FR,fr;q=0.9"),
    "IT": ("意大利", "www.amazon.it", "EUR", "it-IT,it;q=0.9"),
    "ES": ("西班牙", "www.amazon.es", "EUR", "es-ES,es;q=0.9"),
}
FEATURES = {
    "双仓/多仓": ["双粮仓", "双仓", "dual hopper", "two hopper", "dual chamber", "2 hopper"],
    "摄像头": ["摄像头", "摄像", "camera", "video"],
    "Wi-Fi/APP": ["wifi", "wi-fi", "app", "手机控制", "远程控制"],
    "定时定量": ["定时", "定量", "计划喂养", "schedule", "portion", "timed", "programmable"],
    "克重校准": ["克重", "克数", "重量校准", "weigh", "gram", "scale"],
    "备用电源": ["备用电池", "断电", "dual power", "battery backup", "battery operated"],
    "防堵/堵粮提醒": ["防堵", "堵粮", "anti-jam", "anti clog", "blockage sensor"],
    "密封保鲜": ["密封", "保鲜", "干燥剂", "airtight", "freshness", "desiccant", "sealed"],
    "不锈钢餐盘": ["不锈钢", "304", "316", "stainless steel"],
    "双向语音": ["对讲", "双向语音", "two-way audio", "2-way audio"],
    "夜视": ["夜视", "红外", "night vision", "infrared", "940nm"],
    "可拆洗": ["可拆洗", "可拆卸", "易清洁", "detachable", "dishwasher", "easy clean"],
    "指示灯控制": ["指示灯", "灯光关闭", "indicator light", "light control"],
    "多宠识别": ["宠物识别", "rfid", "microchip", "pet recognition", "multi-pet"],
}


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    database_id = str(DB_PATH.resolve())
    if database_id not in _INITIALIZED_DATABASES:
        with _DB_INIT_LOCK:
            if database_id not in _INITIALIZED_DATABASES:
                con.executescript("""
                  CREATE TABLE IF NOT EXISTS products(
                    id INTEGER PRIMARY KEY, country TEXT NOT NULL, category_path TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL, source_date TEXT NOT NULL, asin TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL, brand TEXT NOT NULL DEFAULT '', price REAL, currency TEXT,
                    units REAL, revenue REAL, growth REAL, rating REAL, reviews REAL,
                    image_url TEXT, product_url TEXT, product_key TEXT NOT NULL DEFAULT '',
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(country, source, source_date, asin, title)
                  );
                  CREATE INDEX IF NOT EXISTS ix_products_scope ON products(country,category_path,source_date);
                  CREATE TABLE IF NOT EXISTS searches(
                    id TEXT PRIMARY KEY, keyword TEXT NOT NULL, category_path TEXT NOT NULL,
                    countries TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL,
                    finished_at TEXT, message TEXT NOT NULL DEFAULT ''
                  );
                  CREATE TABLE IF NOT EXISTS analyses(
                    id TEXT PRIMARY KEY, product_name TEXT NOT NULL, category_path TEXT NOT NULL,
                    product_text TEXT NOT NULL, created_at TEXT NOT NULL, result_json TEXT NOT NULL
                  );
                """)
                columns = {row[1] for row in con.execute("PRAGMA table_info(products)")}
                if "product_key" not in columns:
                    con.execute("ALTER TABLE products ADD COLUMN product_key TEXT NOT NULL DEFAULT ''")
                migrate_product_keys(con)
                con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_products_country_key ON products(country,product_key) WHERE product_key<>''")
                con.commit()
                _INITIALIZED_DATABASES.add(database_id)
    return con


def clean_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"[^0-9,.\-]", "", text)
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(",", "") if text.rfind(".") > text.rfind(",") else text.replace(".", "").replace(",", ".")
    elif "," in text:
        tail = text.split(",")[-1]
        text = text.replace(",", "." if len(tail) in (1, 2) else "")
    try:
        return float(text)
    except ValueError:
        return None


def normalized_product_url(value):
    try:
        parsed = urllib.parse.urlparse(str(value or "").strip())
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    path = re.sub(r"/(ref|gp/aw/d)/.*$", "", parsed.path.rstrip("/"), flags=re.I)
    return f"{parsed.netloc.lower()}{path.lower()}"


def product_identity(row):
    asin = re.sub(r"[^A-Z0-9]", "", str(row.get("asin") or "").upper())
    if asin:
        return f"asin:{asin}"
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", str(row.get("product_url") or ""), re.I)
    if match:
        return f"asin:{match.group(1).upper()}"
    url = normalized_product_url(row.get("product_url"))
    if url:
        return f"url:{url}"
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(row.get("title") or "").lower())
    return f"title:{title}" if title else ""


def deduplicate_products(rows, limit=None):
    unique = []
    seen = set()
    for row in rows:
        key = product_identity(row)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(row)
        if limit and len(unique) >= limit:
            break
    return unique


def migrate_product_keys(con):
    rows = [dict(row) for row in con.execute("SELECT * FROM products ORDER BY source_date DESC, id DESC")]
    keepers = {}
    for row in rows:
        key = product_identity(row)
        if not key:
            continue
        keeper = keepers.get((row["country"], key))
        if keeper is None:
            keepers[(row["country"], key)] = row
            con.execute("UPDATE products SET product_key=? WHERE id=?", (key, row["id"]))
            continue
        updates = {}
        keeper_has_metrics = any(keeper.get(field) is not None for field in ("units", "revenue", "growth"))
        row_has_metrics = any(row.get(field) is not None for field in ("units", "revenue", "growth"))
        if row_has_metrics and not keeper_has_metrics:
            updates["source"] = row["source"]
            keeper["source"] = row["source"]
        for field in ("units", "revenue", "growth", "price", "rating", "reviews", "image_url", "product_url"):
            if keeper.get(field) in (None, "") and row.get(field) not in (None, ""):
                updates[field] = row[field]
                keeper[field] = row[field]
        if updates:
            assignment = ",".join(f"{field}=?" for field in updates)
            con.execute(f"UPDATE products SET {assignment} WHERE id=?", (*updates.values(), keeper["id"]))
        con.execute("DELETE FROM products WHERE id=?", (row["id"],))


def normalize_header(value):
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", text)


HEADER_ALIASES = {
    "country": ["country", "国家", "站点", "marketplace", "market"],
    "category_path": ["category", "categorypath", "品类", "三级类目", "类目路径"],
    "asin": ["asin", "productid", "商品编码", "产品id"],
    "title": ["title", "商品标题", "产品标题", "商品名称", "产品名称"],
    "brand": ["brand", "品牌"], "price": ["price", "价格", "售价"],
    "currency": ["currency", "币种"], "units": ["units", "销量", "月销量", "月销售量"],
    "revenue": ["revenue", "销售额", "月销售额", "月销额"],
    "growth": ["growth", "增长率", "销量增长", "销售额增长", "环比增长"],
    "rating": ["rating", "评分", "星级"], "reviews": ["reviews", "评论数", "评分数"],
    "image_url": ["image", "imageurl", "图片", "图片链接"],
    "product_url": ["url", "producturl", "商品链接", "产品链接"],
}


def canonical_country(value):
    text = str(value or "").strip().upper()
    reverse = {label.upper(): code for code, (label, *_rest) in COUNTRIES.items()}
    for code in COUNTRIES:
        if text == code or text == COUNTRIES[code][0].upper() or text == COUNTRIES[code][1].upper():
            return code
    return reverse.get(text, "")


class AmazonSearchParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items = []
        self.item = None
        self.root_depth = 0
        self.depth = 0
        self.capture = None
        self.capture_depth = 0
        self.title_depth = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.item is None and tag == "div" and attrs.get("data-asin") and attrs.get("data-component-type") == "s-search-result":
            self.item = {"asin": attrs["data-asin"], "title": "", "brand": "", "price": None, "rating": None, "reviews": None, "image_url": "", "product_url": ""}
            self.root_depth = self.depth
        if self.item is not None:
            cls = attrs.get("class", "")
            if tag == "h2":
                self.title_depth = self.depth
                if attrs.get("aria-label"):
                    self.item["title"] = attrs["aria-label"].strip()
            if tag == "img" and not self.item["image_url"]:
                self.item["image_url"] = attrs.get("src", "") or attrs.get("data-src", "")
            if tag == "a" and ("s-link-style" in cls or re.search(r"/dp/[A-Z0-9]{10}", attrs.get("href", ""))) and not self.item["product_url"]:
                self.item["product_url"] = urllib.parse.urljoin(self.base_url, attrs.get("href", ""))
            if tag == "span":
                if "a-price-whole" in cls: self.capture = "price"
                elif "a-icon-alt" in cls: self.capture = "rating"
                elif "s-underline-text" in cls: self.capture = "reviews"
                elif (self.title_depth is not None or "a-size-base-plus" in cls or "a-size-medium" in cls) and not self.item["title"]: self.capture = "title"
                elif "a-size-base" in cls and not self.item["brand"]: self.capture = "brand"
                if self.capture: self.capture_depth = self.depth
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.depth += 1

    def handle_endtag(self, tag):
        self.depth = max(0, self.depth - 1)
        if self.item is not None and self.depth <= self.root_depth:
            if self.item.get("title"):
                self.items.append(self.item)
            self.item = None
            self.capture = None
            self.title_depth = None
        elif self.capture and self.depth <= self.capture_depth:
            self.capture = None
        if self.title_depth is not None and self.depth <= self.title_depth:
            self.title_depth = None

    def handle_data(self, data):
        if self.item is None or not self.capture:
            return
        value = data.strip()
        if not value:
            return
        key = self.capture
        if key in ("price", "rating", "reviews"):
            self.item[key] = clean_number((self.item.get(key + "_raw", "") + value))
            self.item[key + "_raw"] = self.item.get(key + "_raw", "") + value
        else:
            self.item[key] = (self.item.get(key, "") + " " + value).strip()


def amazon_search(country, keyword, category_path, progress=None):
    label, host, currency, language = COUNTRIES[country]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = RAW_DIR / stamp
    folder.mkdir(parents=True, exist_ok=True)
    collected = []
    seen = set()
    final_url = ""
    empty_pages = 0
    for page in range(1, MAX_SEARCH_PAGES + 1):
        query = urllib.parse.urlencode({"k": keyword, "page": page})
        request = urllib.request.Request(f"https://{host}/s?{query}", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36", "Accept-Language": language})
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read()
            final_url = response.geturl()
        (folder / f"amazon_{country}_page_{page}.html").write_bytes(raw)
        parser = AmazonSearchParser(f"https://{host}")
        parser.feed(raw.decode("utf-8", "replace"))
        added = 0
        for item in parser.items:
            row = {"country": country, "category_path": category_path, "source": "Amazon public search", "source_date": datetime.now(timezone.utc).isoformat(), "asin": item["asin"], "title": item["title"], "brand": item.get("brand", ""), "price": item.get("price"), "currency": currency, "units": None, "revenue": None, "growth": None, "rating": item.get("rating"), "reviews": item.get("reviews"), "image_url": item.get("image_url", ""), "product_url": item.get("product_url", "") or f"https://{host}/dp/{item['asin']}"}
            key = product_identity(row)
            if not key or key in seen:
                continue
            seen.add(key)
            row["rank"] = len(collected) + 1
            collected.append(row)
            added += 1
            if len(collected) >= MAX_PRODUCTS_PER_MARKET:
                break
        if progress:
            progress(page, len(collected), added)
        if len(collected) >= MAX_PRODUCTS_PER_MARKET:
            break
        empty_pages = empty_pages + 1 if added == 0 else 0
        if not parser.items or empty_pages >= 2:
            break
        time.sleep(0.6)
    items = collected[:MAX_PRODUCTS_PER_MARKET]
    if not items:
        raise RuntimeError(f"页面可访问但未解析到商品。可能遇到站点拦截或页面结构变化。响应页已缓存；未尝试绕过拦截。{final_url}")
    return items


def save_products(items):
    items = deduplicate_products(items)
    if not items:
        return 0
    con = connect()
    for row in items:
        row = {**row, "product_key": product_identity(row), "raw_json": json.dumps(row, ensure_ascii=False)}
        con.execute("""INSERT INTO products(country,category_path,source,source_date,asin,title,brand,price,currency,units,revenue,growth,rating,reviews,image_url,product_url,product_key,raw_json)
          VALUES(:country,:category_path,:source,:source_date,:asin,:title,:brand,:price,:currency,:units,:revenue,:growth,:rating,:reviews,:image_url,:product_url,:product_key,:raw_json)
          ON CONFLICT(country,product_key) WHERE product_key<>'' DO UPDATE SET
            category_path=excluded.category_path,
            source=CASE
              WHEN excluded.units IS NOT NULL OR excluded.revenue IS NOT NULL OR excluded.growth IS NOT NULL THEN excluded.source
              WHEN products.units IS NOT NULL OR products.revenue IS NOT NULL OR products.growth IS NOT NULL THEN products.source
              ELSE excluded.source END,
            source_date=excluded.source_date,
            asin=CASE WHEN excluded.asin<>'' THEN excluded.asin ELSE products.asin END,
            title=excluded.title, brand=CASE WHEN excluded.brand<>'' THEN excluded.brand ELSE products.brand END,
            price=COALESCE(excluded.price,products.price), currency=COALESCE(excluded.currency,products.currency),
            units=COALESCE(excluded.units,products.units), revenue=COALESCE(excluded.revenue,products.revenue), growth=COALESCE(excluded.growth,products.growth),
            rating=COALESCE(excluded.rating,products.rating), reviews=COALESCE(excluded.reviews,products.reviews),
            image_url=CASE WHEN excluded.image_url<>'' THEN excluded.image_url ELSE products.image_url END,
            product_url=CASE WHEN excluded.product_url<>'' THEN excluded.product_url ELSE products.product_url END,
            raw_json=excluded.raw_json""", row)
    con.commit(); con.close()
    return len(items)


def parse_csv_payload(content):
    text = content.decode("utf-8-sig", "replace")
    dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t") if text.strip() else csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return list(reader)


def import_rows(filename, content):
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        rows = parse_csv_payload(content)
    elif suffix in (".xlsx", ".xlsm"):
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.active
        values = sheet.iter_rows(values_only=True)
        headers = [str(x or "") for x in next(values, [])]
        rows = [dict(zip(headers, row)) for row in values]
    else:
        raise ValueError("支持 CSV、XLSX、XLSM 格式。旧版 XLS 请另存为 XLSX。")
    if not rows:
        raise ValueError("文件没有数据行。")
    normalized_aliases = {key: {normalize_header(x) for x in aliases} for key, aliases in HEADER_ALIASES.items()}
    mapped = []
    for raw in rows:
        cols = {normalize_header(k): v for k, v in raw.items()}
        row = {}
        for field, aliases in normalized_aliases.items():
            found = next((cols[a] for a in aliases if a in cols), None)
            row[field] = found
        country = canonical_country(row.get("country"))
        if not country or not row.get("title"):
            continue
        row["country"] = country
        row["source"] = f"导入:{Path(filename).name}"
        row["source_date"] = datetime.now(timezone.utc).isoformat()
        row["category_path"] = str(row.get("category_path") or "").strip()
        row["asin"] = str(row.get("asin") or "").strip()
        row["title"] = str(row["title"]).strip()
        row["brand"] = str(row.get("brand") or "").strip()
        row["currency"] = str(row.get("currency") or COUNTRIES[country][2]).strip()
        for number in ("price", "units", "revenue", "growth", "rating", "reviews"):
            row[number] = clean_number(row.get(number))
        row["image_url"] = str(row.get("image_url") or "").strip()
        row["product_url"] = str(row.get("product_url") or (f"https://{COUNTRIES[country][1]}/dp/{row['asin']}" if row["asin"] else "")).strip()
        mapped.append(row)
    return save_products(mapped)


def extract_features(text):
    lower = str(text or "").lower()
    found = {}
    for name, terms in FEATURES.items():
        hits = [term for term in terms if term.lower() in lower]
        found[name] = {"present": bool(hits), "evidence": hits[:3]}
    return found


def compare_product(name, specs, category_path, countries):
    our_features = extract_features(specs)
    con = connect()
    params = list(countries)
    where = "country IN (" + ",".join("?" for _ in params) + ")" if params else "1=1"
    if category_path:
        where += " AND (category_path=? OR category_path='' OR category_path IS NULL)"
        params.append(category_path)
    data = [dict(row) for row in con.execute(f"SELECT * FROM products WHERE {where} ORDER BY COALESCE(revenue,0) DESC, COALESCE(units,0) DESC, COALESCE(reviews,0) DESC LIMIT 300", params)]
    con.close()
    competitor_rows = []
    for item in data:
        features = extract_features(item["title"])
        deltas = []
        for feature, evidence in our_features.items():
            if evidence["present"] and not features[feature]["present"]:
                verdict = "我方描述有、竞品标题未见证据，需打开详情页核实"
            elif evidence["present"] and features[feature]["present"]:
                verdict = "双方标题/资料均有，非独占优势"
            elif not evidence["present"] and features[feature]["present"]:
                verdict = "竞品标题有、我方资料未提及，待确认是否缺失"
            else:
                verdict = "双方资料均未提及"
            deltas.append({"feature": feature, "verdict": verdict, "our_evidence": evidence["evidence"], "competitor_evidence": features[feature]["evidence"]})
        competitor_rows.append({**item, "feature_comparison": deltas})
    supported_advantages = [name for name, evidence in our_features.items() if evidence["present"] and any(not extract_features(row["title"])[name]["present"] for row in data)]
    return {"product_name": name, "category_path": category_path, "features": our_features, "competitors": competitor_rows, "supported_differentiators": supported_advantages, "limitations": ["竞品标题没写不代表商品没有此功能，差异结论需逐条打开链接核实。", "销量、销售额和增长率仅在数据源提供时参与机会判断；不会用公开页面数据或模型补造。", "页面截图/图片对比受图片角度、光线和尺寸影响，需人工确认产品结构。"], "created_at": datetime.now(timezone.utc).isoformat()}


def opportunity_tags(rows):
    scoped = [r for r in rows if r.get("country") and r.get("category_path")]
    by_scope = {}
    for row in scoped:
        by_scope.setdefault((row["country"], row["category_path"]), []).append(row)
    tagged = []
    for row in rows:
        group = by_scope.get((row.get("country"), row.get("category_path")), [])
        units = sorted([x["units"] for x in group if x["units"] is not None])
        revenues = sorted([x["revenue"] for x in group if x["revenue"] is not None])
        prices = sorted([x["price"] for x in group if x["price"] is not None])
        q_units = units[int((len(units)-1)*0.75)] if units else None
        q_revenue = revenues[int((len(revenues)-1)*0.75)] if revenues else None
        q_price = prices[int((len(prices)-1)*0.75)] if prices else None
        tags = []
        if row.get("growth") is not None and row["growth"] >= 20:
            tags.append("高增长")
        if (row.get("units") is not None and q_units is not None and row["units"] >= q_units) or (row.get("revenue") is not None and q_revenue is not None and row["revenue"] >= q_revenue):
            tags.append("流量款")
        if row.get("price") is not None and q_price is not None and row["price"] >= q_price:
            tags.append("利润款候选")
        tagged.append({**row, "opportunity_tags": tags, "thresholds": {"units_p75": q_units, "revenue_p75": q_revenue, "price_p75": q_price}, "opportunity_note": "样本内相对筛选，不等同于净利润；价格需结合成本、广告、佣金、退货和税费。"})
    return tagged


def export_xlsx(category_path=""):
    con = connect()
    sql = "SELECT * FROM products" + (" WHERE category_path=? OR category_path=''" if category_path else "") + " ORDER BY country,category_path,COALESCE(revenue,0) DESC,COALESCE(units,0) DESC"
    data = [dict(x) for x in con.execute(sql, (category_path,) if category_path else ())]
    analyses = [dict(x) for x in con.execute("SELECT product_name,category_path,created_at,result_json FROM analyses ORDER BY created_at DESC LIMIT 50")]
    con.close()
    data = opportunity_tags(data)
    book = Workbook(); products = book.active; products.title = "七国商品数据"
    headers = ["国家", "三级类目", "数据源", "采集时间", "ASIN", "品牌", "标题", "价格", "币种", "月销量", "月销售额", "增长率(%)", "评分", "评论数", "机会标签", "商品图", "商品链接"]
    products.append(headers)
    for row in data:
        products.append([COUNTRIES.get(row["country"], (row["country"],))[0], row["category_path"], row["source"], row["source_date"], row["asin"], row["brand"], row["title"], row["price"], row["currency"], row["units"], row["revenue"], row["growth"], row["rating"], row["reviews"], "、".join(row["opportunity_tags"]), row["image_url"], row["product_url"]])
    for ws in book.worksheets:
        ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]: cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="17324D")
        for cells in ws.columns:
            ws.column_dimensions[cells[0].column_letter].width = min(48, max(12, max(len(str(c.value or "")) for c in cells[:100]) + 2))
    opp = book.create_sheet("机会定义")
    opp.append(["标签", "可复核定义", "所需字段"])
    opp.append(["高增长", "数据源增长率≥20%", "growth；需注明周期和来源"])
    opp.append(["流量款", "同国家+三级类目样本的月销量或月销售额达到P75", "units 或 revenue"])
    opp.append(["利润款候选", "同国家+三级类目样本售价达到P75；不代表净利高", "price；还需成本/费用判断利润"])
    feat = book.create_sheet("功能对照")
    feat.append(["产品名", "三级类目", "分析时间", "功能", "判定", "我方证据", "竞品证据", "ASIN"])
    for analysis in analyses:
        result = json.loads(analysis["result_json"])
        for item in result.get("competitors", []):
            for diff in item.get("feature_comparison", []):
                feat.append([analysis["product_name"], analysis["category_path"], analysis["created_at"], diff["feature"], diff["verdict"], ", ".join(diff["our_evidence"]), ", ".join(diff["competitor_evidence"]), item.get("asin")])
    output = io.BytesIO(); book.save(output); return output.getvalue()


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, value, status=200):
        body = json_bytes(value); self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)

    def body(self):
        return self.rfile.read(int(self.headers.get("Content-Length", "0")))

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/status":
            con=connect(); count=con.execute("SELECT COUNT(*) FROM products").fetchone()[0]; countries=con.execute("SELECT COUNT(DISTINCT country) FROM products").fetchone()[0]; latest=con.execute("SELECT MAX(source_date) FROM products").fetchone()[0]; con.close()
            return self.send_json({"app":"AM master","data_dir":str(DATA_DIR),"products":count,"countries_with_data":countries,"latest_update":latest,"tokenless":True})
        if path == "/api/products":
            q=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); country=q.get("country",[""])[0]; category=q.get("category",[""])[0]
            con=connect(); where=[]; args=[]
            if country: where.append("country=?"); args.append(country)
            if category: where.append("category_path=?"); args.append(category)
            sql="SELECT * FROM products"+(" WHERE "+" AND ".join(where) if where else "")+" ORDER BY source_date DESC LIMIT 1000"
            rows=[dict(x) for x in con.execute(sql,args)]; con.close(); return self.send_json({"items":opportunity_tags(rows)})
        if path == "/api/categories":
            con=connect(); values=[r[0] for r in con.execute("SELECT DISTINCT category_path FROM products WHERE category_path<>'' ORDER BY category_path")]; con.close(); return self.send_json({"items":values})
        if path == "/api/search-run":
            run_id=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id",[""])[0]
            con=connect(); row=con.execute("SELECT * FROM searches WHERE id=?",(run_id,)).fetchone(); con.close()
            if not row: return self.send_json({"error":"找不到该搜索任务"},404)
            result=dict(row)
            try: result["progress"]=json.loads(result["message"] or "[]")
            except json.JSONDecodeError: result["progress"]=[]
            return self.send_json(result)
        if path == "/" or path.startswith("/static/"):
            relative="static/index.html" if path == "/" else path.lstrip("/")
            file=(ROOT / relative).resolve()
            if STATIC not in file.parents: return self.send_error(404)
            if not file.is_file(): return self.send_error(404)
            body=file.read_bytes(); kind="text/html; charset=utf-8" if file.suffix==".html" else "text/css; charset=utf-8" if file.suffix==".css" else "text/csv; charset=utf-8" if file.suffix==".csv" else "application/javascript; charset=utf-8"
            self.send_response(200); self.send_header("Content-Type",kind); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body); return
        return self.send_error(404)

    def do_POST(self):
        path=urllib.parse.urlparse(self.path).path
        try:
            if path == "/api/import":
                content=self.body(); message=BytesParser(policy=default).parsebytes((f"Content-Type: {self.headers.get('Content-Type','application/octet-stream')}\r\nMIME-Version: 1.0\r\n\r\n".encode()+content))
                filename=urllib.parse.unquote(self.headers.get("X-File-Name", "import.csv")); payload=content
                if message.is_multipart():
                    part=next((p for p in message.iter_parts() if p.get_filename()),None)
                    if not part: return self.send_json({"error":"未找到上传文件"},400)
                    filename=part.get_filename(); payload=part.get_payload(decode=True)
                count=import_rows(filename,payload); return self.send_json({"imported":count})
            data=json.loads(self.body() or b"{}")
            if path == "/api/search":
                keyword=str(data.get("keyword","")).strip(); category=str(data.get("category_path","")).strip(); countries=[x for x in data.get("countries",list(COUNTRIES)) if x in COUNTRIES]
                if not keyword: return self.send_json({"error":"请输入产品名或关键词"},400)
                if not countries: return self.send_json({"error":"至少选择一个目标国家"},400)
                run_id=uuid.uuid4().hex; started=datetime.now(timezone.utc).isoformat(); con=connect(); con.execute("INSERT INTO searches(id,keyword,category_path,countries,status,started_at) VALUES(?,?,?,?,?,?)",(run_id,keyword,category,json.dumps(countries),"RUNNING",started)); con.commit(); con.close()
                thread=threading.Thread(target=execute_search,args=(run_id,keyword,category,countries),daemon=True); thread.start()
                return self.send_json({"run_id":run_id,"status":"RUNNING","countries":countries})
            if path == "/api/analyze":
                name=str(data.get("product_name","")).strip(); specs=str(data.get("product_text","")).strip(); category=str(data.get("category_path","")).strip(); countries=[x for x in data.get("countries",list(COUNTRIES)) if x in COUNTRIES]
                if not name or not specs: return self.send_json({"error":"产品名称和产品资料都必填"},400)
                if not countries: return self.send_json({"error":"至少选择一个对照市场"},400)
                result=compare_product(name,specs,category,countries); analysis_id=uuid.uuid4().hex; con=connect(); con.execute("INSERT INTO analyses VALUES(?,?,?,?,?,?)",(analysis_id,name,category,specs,result["created_at"],json.dumps(result,ensure_ascii=False))); con.commit(); con.close(); return self.send_json({"id":analysis_id,**result})
            return self.send_error(404)
        except Exception as exc:
            return self.send_json({"error":str(exc)},500)

class ExportHandler(Handler):
    def do_GET(self):
        if urllib.parse.urlparse(self.path).path == "/api/export.xlsx":
            try:
                q=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); payload=export_xlsx(q.get("category",[""])[0]); self.send_response(200); self.send_header("Content-Type","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"); self.send_header("Content-Disposition","attachment; filename=AM-master-market-analysis.xlsx"); self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload)
            except Exception as exc: self.send_json({"error":str(exc)},500)
            return
        super().do_GET()


def execute_search(run_id, keyword, category, countries):
    outcomes=[]; saved=0
    for code in countries:
        outcome={"country":code,"label":COUNTRIES[code][0],"status":"RUNNING","page":0,"count":0,"target":MAX_PRODUCTS_PER_MARKET}
        outcomes.append(outcome)
        def publish_progress(page, count, added):
            outcome.update({"page":page,"count":count,"added":added})
            con=connect(); con.execute("UPDATE searches SET message=? WHERE id=?",(json.dumps({"countries":outcomes,"saved":saved},ensure_ascii=False),run_id)); con.commit(); con.close()
        publish_progress(0, 0, 0)
        try:
            items=amazon_search(code,keyword,category,publish_progress); saved+=save_products(items); outcome.update({"status":"ok","count":len(items)})
        except Exception as exc:
            outcome.update({"status":"failed","error":str(exc)[:500]})
        con=connect(); con.execute("UPDATE searches SET message=? WHERE id=?",(json.dumps({"countries":outcomes,"saved":saved},ensure_ascii=False),run_id)); con.commit(); con.close()
        time.sleep(0.6)
    status="COMPLETED" if any(x["status"]=="ok" for x in outcomes) else "FAILED"
    con=connect(); con.execute("UPDATE searches SET status=?,finished_at=?,message=? WHERE id=?",(status,datetime.now(timezone.utc).isoformat(),json.dumps({"countries":outcomes,"saved":saved},ensure_ascii=False),run_id)); con.commit(); con.close()


if __name__ == "__main__":
    connect().close()
    server=ThreadingHTTPServer(("127.0.0.1",PORT),ExportHandler)
    print(f"AM master running at http://127.0.0.1:{PORT} | data: {DATA_DIR}",flush=True)
    server.serve_forever()
