from __future__ import annotations

import re
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


MARKETS = {
    "US": ("USD", "美国"), "CA": ("CAD", "加拿大"), "UK": ("GBP", "英国"),
    "DE": ("EUR", "德国"), "FR": ("EUR", "法国"), "IT": ("EUR", "意大利"),
    "ES": ("EUR", "西班牙"),
}


def validate_sellersprite_url(value):
    parsed = urllib.parse.urlparse(str(value or "").strip())
    if parsed.scheme != "https" or parsed.hostname not in {"sellersprite.com", "www.sellersprite.com"}:
        raise ValueError("请粘贴 https://www.sellersprite.com/ 开头的结果页地址。")
    if not parsed.path.startswith(("/v2/", "/v3/")):
        raise ValueError("该地址不是卖家精灵工作台结果页。")
    query = urllib.parse.parse_qs(parsed.query)
    market = query.get("market", [""])[0].upper()
    if market not in MARKETS:
        raise ValueError("结果页地址中缺少受支持的 market 站点参数。")
    return parsed, market


def parse_money(value):
    text = str(value or "").replace("\xa0", " ").strip()
    number = re.search(r"-?[\d,.]+", text)
    if not number:
        return None
    cleaned = number.group(0).replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_card_text(text, product_url="", image_url=""):
    flat = re.sub(r"\s+", " ", str(text or "")).strip()
    asin_match = re.search(r"\b([A-Z0-9]{10})\b", flat)
    if not asin_match:
        asin_match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", product_url, re.I)
    if not asin_match:
        return None
    asin = asin_match.group(1).upper()
    prefix = flat[:asin_match.start()].strip()
    prefix = re.sub(r"^(?:(?:A\+|V|BS|AC)\s+)+", "", prefix).strip()
    brand_match = re.search(r"品牌:\s*(.*?)\s+(?:#|销量\(父\)|子体销量|销售额|价格:)", flat)
    units_match = re.search(r"销量\(父\):\s*([\d,]+)", flat)
    revenue_match = re.search(r"销售额:\s*(.*?)\s+变体数:", flat)
    price_match = re.search(r"价格:\s*(.*?)\s+评分/评分数:", flat)
    rating_match = re.search(r"评分/评分数:\s*([\d.]+)\s*/\s*([\d,]+)", flat)
    rank_match = re.search(r"#([\d,]+)\s+in\s+", flat, re.I)
    date_match = re.search(r"上架时间:\s*([^ ]+)", flat)
    return {
        "asin": asin,
        "title": prefix or asin,
        "brand": brand_match.group(1).strip(" ") if brand_match else "",
        "units": parse_money(units_match.group(1)) if units_match else None,
        "revenue": parse_money(revenue_match.group(1)) if revenue_match else None,
        "price": parse_money(price_match.group(1)) if price_match else None,
        "rating": parse_money(rating_match.group(1)) if rating_match else None,
        "reviews": parse_money(rating_match.group(2)) if rating_match else None,
        "rank": parse_money(rank_match.group(1)) if rank_match else None,
        "launch_date": date_match.group(1) if date_match else "",
        "product_url": product_url,
        "image_url": image_url,
    }


def _selenium():
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
    except ImportError as exc:
        raise RuntimeError("缺少 Selenium。请重新运行 setup_windows.bat。") from exc
    return webdriver, By


def _open_edge(profile_dir):
    webdriver, _by = _selenium()
    options = webdriver.EdgeOptions()
    options.add_argument(f"--user-data-dir={Path(profile_dir).resolve()}")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-features=msEdgeFirstRunExperience")
    return webdriver.Edge(options=options)


def open_login(profile_dir, progress):
    profile_dir = Path(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    marker = profile_dir / ".logged_in"
    progress("正在打开卖家精灵登录窗口", 0, 0)
    driver = _open_edge(profile_dir)
    try:
        driver.get("https://www.sellersprite.com/v2/welcome")
        progress("请在弹出的 Edge 窗口中完成登录，不要把密码粘贴到 AM master", 0, 0)
        deadline = time.time() + 600
        while time.time() < deadline:
            body = driver.find_element("tag name", "body").text
            if "我的导出" in body and ("查竞品" in body or "选市场" in body):
                progress("登录已确认，正在保存本机会话", 0, 0)
                marker.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
                return {"logged_in": True}
            time.sleep(1)
    finally:
        driver.quit()
    raise RuntimeError("等待登录超时。请重新点击“打开登录窗口”。")


def sync_results(url, category_path, profile_dir, max_products, progress):
    parsed, market = validate_sellersprite_url(url)
    currency, label = MARKETS[market]
    profile_dir = Path(profile_dir)
    if not (profile_dir / ".logged_in").exists():
        raise RuntimeError("尚未建立卖家精灵本机会话，请先点击“打开登录窗口”。")
    max_products = max(1, min(int(max_products or 100), 100))
    rows = []
    seen = set()
    driver = _open_edge(profile_dir)
    try:
        for page_number in range(1, 11):
            query = urllib.parse.parse_qs(parsed.query)
            query["page"] = [str(page_number)]
            query["size"] = ["60"]
            page_url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query, doseq=True)))
            progress(f"{label}：正在读取第 {page_number} 页", page_number, len(rows))
            driver.get(page_url)
            deadline = time.time() + 45
            while time.time() < deadline and not driver.find_elements("css selector", 'a[href*="/dp/"]'):
                time.sleep(0.5)
            if not driver.find_elements("css selector", 'a[href*="/dp/"]'):
                body = driver.find_element("tag name", "body").text
                if "登录" in body and "立即查询" not in body:
                    raise RuntimeError("卖家精灵登录会话已失效，请重新登录。")
                if "验证码" in body or "安全验证" in body:
                    raise RuntimeError("卖家精灵要求安全验证，请先在浏览器窗口中人工完成。")
                raise RuntimeError("结果页没有加载出商品，请检查 URL、账号权限或查询条件。")
            cards = driver.execute_script("""
                return Array.from(document.querySelectorAll('a[href*="/dp/"]')).map(link => {
                  let node = link;
                  while (node && node !== document.body) {
                    const text = node.innerText || '';
                    if (text.includes('销量(父)') && text.includes('销售额:') && text.includes('评分/评分数:')) {
                      const img = node.querySelector('img');
                      return {text, href: link.href, image: img ? (img.currentSrc || img.src || '') : ''};
                    }
                    node = node.parentElement;
                  }
                  return null;
                }).filter(Boolean);
            """)
            added = 0
            for card in cards:
                row = parse_card_text(card.get("text"), card.get("href"), card.get("image"))
                if not row or row["asin"] in seen:
                    continue
                seen.add(row["asin"])
                row.update({
                    "country": market, "category_path": category_path, "source": "SellerSprite authorized browser",
                    "source_date": datetime.now(timezone.utc).isoformat(), "currency": currency, "growth": None,
                    "raw_period": urllib.parse.parse_qs(parsed.query).get("monthName", [""])[0],
                })
                rows.append(row)
                added += 1
                if len(rows) >= max_products:
                    break
            progress(f"{label}：第 {page_number} 页新增 {added} 条，累计 {len(rows)}/{max_products}", page_number, len(rows))
            if len(rows) >= max_products or added == 0:
                break
            time.sleep(1.2)
    finally:
        driver.quit()
    if not rows:
        raise RuntimeError("没有读取到有效商品。请确认结果页中已显示商品明细。")
    return rows[:max_products]
