"""
scraper.py – Synergy Teacher Dashboard
Web scraping via requests + BeautifulSoup.
The live field-mapping browser is handled by live_map_panel.py (QtWebEngine).
"""

import re
from typing import Optional, Dict, List

import requests
from bs4 import BeautifulSoup

FIELD_LABELS = [
    "student_name",
    "student_id",
    "year_group",
    "praise_points",
    "sanction_points",
    "phone_1",
    "phone_2",
]


class SynergyScaper:
    """
    Session-based scraper.  Cookies can be injected from the embedded
    QtWebEngine browser so pages that require login are accessible.
    """

    def __init__(self, base_url: str = "", mappings: Optional[Dict] = None):
        self.base_url = base_url.rstrip("/")
        self.mappings = mappings or {}
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0 Safari/537.36"}
        )

    def inject_cookies(self, cookies: List[Dict]):
        """Copy cookies from QtWebEngine (list of dicts with name/value/domain)."""
        for c in cookies:
            self.session.cookies.set(
                c["name"], c["value"], domain=c.get("domain", "")
            )

    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        try:
            r = self.session.get(url, timeout=15)
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"[scraper] fetch error {url}: {e}")
            return None

    def extract_with_selector(self, soup: BeautifulSoup, selector: str) -> str:
        try:
            el = soup.select_one(selector)
            return (el.get_text(strip=True) if el else "").strip()
        except Exception:
            return ""

    def scrape_student_page(self, url: str) -> Dict:
        """
        Pull data from a student page using saved CSS mappings.
        Falls back to regex keyword patterns if a mapping is missing.
        """
        soup = self.fetch_page(url)
        if not soup:
            return {}

        data: Dict = {}

        for field, mapping in self.mappings.items():
            sel = mapping.get("selector", "")
            if sel:
                data[field] = self.extract_with_selector(soup, sel)

        text = soup.get_text(" ", strip=True)

        if not data.get("phone_1"):
            phones = re.findall(r"(?:0|\+44)\s?\d[\d\s\-]{8,11}", text)
            for i, p in enumerate(phones[:2], 1):
                data[f"phone_{i}"] = re.sub(r"\s+", " ", p).strip()

        if not data.get("praise_points"):
            m = re.search(r"praise[\s:]+(\d+)", text, re.IGNORECASE)
            if m:
                data["praise_points"] = m.group(1)

        if not data.get("sanction_points"):
            m = re.search(r"sanction[\s:]+(\d+)", text, re.IGNORECASE)
            if m:
                data["sanction_points"] = m.group(1)

        return data

    def keyword_scan(self, url: str, keywords: List[str]) -> Dict[str, List[str]]:
        soup = self.fetch_page(url)
        if not soup:
            return {}
        results: Dict[str, List[str]] = {k: [] for k in keywords}
        for tag in soup.find_all(True):
            text = (tag.get_text(strip=True) or "").lower()
            for kw in keywords:
                if kw.lower() in text and len(text) < 300:
                    snippet = tag.get_text(strip=True)[:150]
                    if snippet not in results[kw]:
                        results[kw].append(snippet)
        return results
