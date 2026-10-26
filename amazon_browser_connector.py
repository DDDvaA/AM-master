from __future__ import annotations

import html
import re
import time
from pathlib import Path
from urllib.parse import urlparse


def _selenium():
    try:
        from selenium import webdriver
    except ImportError as exc:
        raise RuntimeError("缺少 Selenium。请重新运行 setup_windows.bat。") from exc
    return webdriver


def _has_products(source):
    lowered = str(source or "").lower()
    return "s-search-result" in lowered and "data-asin" in lowered


def _is_challenge(source):
    lowered = str(source or "").lower()
    return any(token in lowered for token in (
        "bm-verify", "interstitialchallenge", "captcha", "robot check",
        "validatecaptcha", "type the characters", "enter the characters",
        "geben sie die zeichen", "saisissez les caractères", "inserisci i caratteri",
        "introduce los caracteres", "awswaf",
    ))


def _same_search_page(current_url, target_url):
    try:
        current = urlparse(current_url)
        target = urlparse(target_url)
        return current.hostname == target.hostname and current.path == target.path and current.path == "/s"
    except ValueError:
        return False


def _cards_to_markup(cards):
    parts = []
    seen = set()
    for card in cards or []:
        asin = re.sub(r"[^A-Z0-9]", "", str(card.get("asin") or "").upper())
        title = str(card.get("title") or "").strip()
        if len(asin) != 10 or not title or asin in seen:
            continue
        seen.add(asin)
        href = html.escape(str(card.get("href") or ""), quote=True)
        image = html.escape(str(card.get("image") or ""), quote=True)
        price = html.escape(str(card.get("price") or ""))
        parts.append(
            f'<div data-component-type="s-search-result" data-asin="{asin}">'
            f'<h2><span>{html.escape(title)}</span></h2><a href="{href}"><img src="{image}"></a>'
            f'<span class="a-price-whole">{price}</span></div>'
        )
    return "".join(parts)


class AmazonBrowserSession:
    """Visible, persistent Edge session used only after normal HTTP recovery fails."""

    def __init__(self, profile_dir):
        webdriver = _selenium()
        profile_dir = Path(profile_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)
        options = webdriver.EdgeOptions()
        options.add_argument(f"--user-data-dir={profile_dir.resolve()}")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-features=msEdgeFirstRunExperience")
        self.driver = webdriver.Edge(options=options)

    def fetch(self, url, progress=None, page=0, wait_seconds=300, verification_expected=False):
        self.driver.get(url)
        started = time.time()
        deadline = started + (wait_seconds if verification_expected else 25)
        challenge_reported = verification_expected
        last_reload = started
        if verification_expected and progress:
            progress(page, 0, 0, "Amazon 已触发验证；请在弹出的 Edge 中完成，验证后程序会重新打开原搜索页")
        while time.time() < deadline:
            source = self.driver.page_source or ""
            if _has_products(source):
                return source.encode("utf-8")
            cards = self.driver.execute_script(r"""
                const seen = new Set();
                const rows = [];
                for (const link of document.querySelectorAll('a[href*="/dp/"]')) {
                  const match = (link.href || '').match(/\/dp\/([A-Z0-9]{10})/i);
                  if (!match || seen.has(match[1])) continue;
                  let card = link.closest('[data-asin], [data-component-type="s-search-result"]');
                  if (!card) {
                    card = link;
                    for (let i = 0; i < 8 && card && !card.querySelector?.('h2'); i++) card = card.parentElement;
                  }
                  const heading = card?.querySelector?.('h2');
                  const title = (heading?.getAttribute('aria-label') || heading?.innerText || link.getAttribute('aria-label') || '').trim();
                  if (!title) continue;
                  const img = card?.querySelector?.('img');
                  const price = card?.querySelector?.('.a-price-whole');
                  seen.add(match[1]);
                  rows.push({asin: match[1], title, href: link.href, image: img ? (img.currentSrc || img.src || '') : '', price: price?.innerText || ''});
                }
                return rows;
            """)
            markup = _cards_to_markup(cards)
            if markup:
                return markup.encode("utf-8")
            challenged = _is_challenge(source)
            if challenged and not challenge_reported:
                challenge_reported = True
                deadline = started + wait_seconds
                if progress:
                    progress(page, 0, 0, "Amazon 要求人工验证；请在弹出的 Edge 中完成，程序将自动续抓")
            # Amazon may redirect to a home/consent page after verification. Once the
            # challenge is gone, revisit the exact search URL without interrupting it.
            now = time.time()
            if challenge_reported and not challenged and now - last_reload >= 6:
                if not _same_search_page(self.driver.current_url, url) or now - last_reload >= 12:
                    if progress:
                        progress(page, 0, 0, "已检测到验证页面消失，正在重新加载原搜索页")
                    self.driver.get(url)
                    last_reload = now
            time.sleep(1)
        return None

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass
