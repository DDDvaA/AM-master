from __future__ import annotations

import html
import re
import time
from datetime import datetime, timezone
from pathlib import Path
import urllib.request


def _selenium():
    try:
        from selenium import webdriver
    except ImportError as exc:
        raise RuntimeError("缺少 Selenium。请重新运行 setup_windows.bat。") from exc
    return webdriver


def _open_edge(profile_dir):
    webdriver = _selenium()
    profile_dir = Path(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    options = webdriver.EdgeOptions()
    options.add_argument(f"--user-data-dir={profile_dir.resolve()}")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-features=msEdgeFirstRunExperience")
    return webdriver.Edge(options=options)


def _is_challenge(source):
    lowered = str(source or "").lower()
    return any(token in lowered for token in (
        "bm-verify", "interstitialchallenge", "captcha", "robot check",
        "validatecaptcha", "geben sie die zeichen", "saisissez les caractères",
        "inserisci i caratteri", "introduce los caracteres", "awswaf",
    ))


def _rating(value):
    match = re.search(r"(\d+(?:[.,]\d+)?)", str(value or ""))
    return float(match.group(1).replace(",", ".")) if match else None


def _helpful(value):
    text = str(value or "").lower()
    if not text:
        return 0
    match = re.search(r"([\d,.]+)", text)
    if not match:
        return 1 if any(token in text for token in ("one person", "eine person", "une personne", "una persona")) else 0
    try:
        return int(float(match.group(1).replace(",", "")))
    except ValueError:
        return 0


def _text(fragment):
    value = re.sub(r"<[^>]+>", " ", fragment or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _hook_text(card, hooks):
    for hook in hooks:
        match = re.search(rf'<([a-z0-9]+)[^>]*data-hook=["\']{re.escape(hook)}["\'][^>]*>(.*?)</\1>', card, re.I | re.S)
        if match:
            value = _text(match.group(2))
            if value:
                return value
    return ""


def parse_public_product_reviews(source, base_url):
    text = str(source or "")
    starts = [match.start() for match in re.finditer(r'<div[^>]*data-hook=["\']review["\'][^>]*>', text, re.I)]
    rows = []
    for index, start in enumerate(starts):
        card = text[start:starts[index + 1] if index + 1 < len(starts) else min(len(text), start + 80000)]
        review_id = ""
        for pattern in (r'customer_review-([A-Z0-9]+)', r'/srp/-/([A-Z0-9]+)', r'/customer-reviews/([A-Z0-9]+)'):
            match = re.search(pattern, card, re.I)
            if match:
                review_id = match.group(1).upper()
                break
        body = _hook_text(card, ("reviewRichContentContainer", "reviewText", "review-body"))
        title = _hook_text(card, ("reviewTitle", "review-title"))
        if not body or not review_id:
            continue
        rating_match = re.search(r'data-hook=["\'](?:review-star-rating|cmps-review-star-rating)["\'][^>]*>.*?<span[^>]*class=["\'][^"\']*a-icon-alt[^"\']*["\'][^>]*>(.*?)</span>', card, re.I | re.S)
        reviewer_match = re.search(r'class=["\'][^"\']*a-profile-name[^"\']*["\'][^>]*>(.*?)</span>', card, re.I | re.S)
        href_match = re.search(r'href=["\']([^"\']*(?:customer-reviews|/srp/-/)[^"\']*)["\']', card, re.I)
        url = href_match.group(1) if href_match else ""
        if url.startswith("/"):
            url = base_url.rstrip("/") + url
        rows.append({
            "review_id": review_id, "rating_text": _text(rating_match.group(1)) if rating_match else "",
            "title": title, "body": body, "date_text": _hook_text(card, ("review-date",)),
            "verified": bool(re.search(r'data-hook=["\']avp-badge["\']', card, re.I)),
            "helpful_text": _hook_text(card, ("helpful-vote-statement",)),
            "reviewer": _text(reviewer_match.group(1)) if reviewer_match else "", "url": url,
        })
    return rows


def fetch_public_product_reviews(host, asin, raw_dir):
    url = f"https://{host}/dp/{asin}"
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    last_error = ""
    for attempt in range(1, 5):
        request = urllib.request.Request(url, headers={
            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
            "Accept-Language":"en-US,en;q=0.9", "Cache-Control":"no-cache",
        })
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                source = response.read().decode("utf-8", "replace")
            (raw_dir / f"{host.replace('.', '_')}_{asin}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{attempt}.html").write_text(source, encoding="utf-8")
            rows = parse_public_product_reviews(source, f"https://{host}")
            if rows:
                return rows
            last_error = "商品页本次未包含公开评论卡片"
        except Exception as exc:
            last_error = str(exc)
        if attempt < 4:
            time.sleep(1.5 * attempt)
    if last_error:
        raise RuntimeError(last_error)
    return []


def _read_page(driver, url, progress, country, asin, page, wait_seconds=300):
    driver.get(url)
    started = time.time()
    deadline = started + 35
    challenge_reported = False
    while time.time() < deadline:
        source = driver.page_source or ""
        if _is_challenge(source):
            if not challenge_reported:
                challenge_reported = True
                deadline = started + wait_seconds
                progress(f"{country} {asin}：Amazon 要求人工验证，请在弹出的 Edge 中完成", page, 0)
            time.sleep(1)
            continue
        cards = driver.execute_script(r"""
            return Array.from(document.querySelectorAll('[data-hook="review"]')).map(card => {
              const text = (selector) => {
                const node = card.querySelector(selector);
                return node ? (node.innerText || node.textContent || '').trim() : '';
              };
              const titleNode = card.querySelector('[data-hook="review-title"]');
              const titleSpans = titleNode ? Array.from(titleNode.querySelectorAll('span')) : [];
              const profile = card.querySelector('.a-profile-name');
              const permalink = card.querySelector('a[data-hook="review-title"]');
              return {
                review_id: card.id || card.getAttribute('data-review-id') || '',
                rating_text: text('[data-hook="review-star-rating"]') || text('[data-hook="cmps-review-star-rating"]'),
                title: titleSpans.length ? (titleSpans[titleSpans.length - 1].innerText || '').trim() : (titleNode?.innerText || '').trim(),
                body: text('[data-hook="review-body"]'),
                date_text: text('[data-hook="review-date"]'),
                verified: !!card.querySelector('[data-hook="avp-badge"]'),
                helpful_text: text('[data-hook="helpful-vote-statement"]'),
                reviewer: profile ? (profile.innerText || '').trim() : '',
                url: permalink ? permalink.href : ''
              };
            });
        """)
        if cards:
            return cards
        current_url = str(driver.current_url or "")
        if "/ap/signin" in current_url:
            raise RuntimeError(f"{country} {asin} 独立评论页要求 Amazon 登录；程序未提交账号信息。")
        elapsed = time.time() - started
        if 3 < elapsed < 6:
            driver.execute_script("document.querySelector('#reviewsMedley')?.scrollIntoView({block:'center'})")
        elif 7 < elapsed < 10:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.75)")
        elif 11 < elapsed < 14:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        if elapsed > 22:
            return []
        time.sleep(0.8)
    raise RuntimeError(f"{country} {asin} 评论页验证等待超时。")


def collect_reviews(country, host, asin, product_title, profile_dir, raw_dir, max_reviews, progress):
    max_reviews = max(1, min(int(max_reviews or 10), 50))
    rows = []
    seen = set()
    cards = []
    try:
        progress(f"{country} {asin}：读取公开商品页评论", 1, 0)
        cards = fetch_public_product_reviews(host, asin, raw_dir)
    except Exception as exc:
        progress(f"{country} {asin}：公开请求失败，切换可见 Edge（{exc}）", 1, 0)
    driver = None
    try:
        for page in range(1, 2):
            url = f"https://{host}/dp/{asin}"
            if not cards:
                driver = _open_edge(profile_dir)
                progress(f"{country} {asin}：读取商品页公开评论", page, len(rows))
                cards = _read_page(driver, url, progress, country, asin, page)
            added = 0
            for card in cards:
                review_id = re.sub(r"[^A-Za-z0-9_-]", "", str(card.get("review_id") or ""))
                body = str(card.get("body") or "").strip()
                title = str(card.get("title") or "").strip()
                key = review_id or f"{title}\n{body}"[:500]
                if not key or key in seen or not body:
                    continue
                seen.add(key)
                rows.append({
                    "country": country, "asin": asin, "product_title": product_title,
                    "review_id": review_id or f"local-{abs(hash(key))}",
                    "rating": _rating(card.get("rating_text")), "review_title": title,
                    "review_body": body, "review_date_text": str(card.get("date_text") or "").strip(),
                    "verified": 1 if card.get("verified") else 0,
                    "helpful_count": _helpful(card.get("helpful_text")),
                    "reviewer": str(card.get("reviewer") or "").strip(),
                    "review_url": str(card.get("url") or url).strip(),
                    "source": "Amazon product reviews", "collected_at": datetime.now(timezone.utc).isoformat(),
                })
                added += 1
                if len(rows) >= max_reviews:
                    break
            progress(f"{country} {asin}：商品页新增 {added} 条，累计 {len(rows)}/{max_reviews}", page, len(rows))
            if len(rows) >= max_reviews or not cards or added == 0:
                break
            time.sleep(0.8)
    finally:
        try:
            if driver is not None:
                driver.quit()
        except Exception:
            pass
    return rows
