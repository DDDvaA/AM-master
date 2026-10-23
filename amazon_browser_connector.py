from __future__ import annotations

import time
from pathlib import Path


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
    return any(token in lowered for token in ("bm-verify", "interstitialchallenge", "captcha", "robot check"))


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

    def fetch(self, url, progress=None, page=0, wait_seconds=300):
        self.driver.get(url)
        started = time.time()
        deadline = started + 25
        challenge_reported = False
        while time.time() < deadline:
            source = self.driver.page_source or ""
            if _has_products(source):
                return source.encode("utf-8")
            if _is_challenge(source) and not challenge_reported:
                challenge_reported = True
                deadline = started + wait_seconds
                if progress:
                    progress(page, 0, 0, "Amazon 要求人工验证；请在弹出的 Edge 中完成，程序将自动续抓")
            time.sleep(1)
        return None

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass
