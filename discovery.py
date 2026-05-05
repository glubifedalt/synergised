"""
discovery.py – Synergy Teacher Dashboard
Auto-discovers students from a Synergy class/student-list page.

Two modes:
  1. Pattern-based  – given a CSS selector for a student row, finds all
                      matching elements on the page (and follows pagination).
  2. Heuristic      – no mapping needed; scans the page for name-like text
                      near phone numbers, year/form references, and student IDs.

The result is a list of candidate dicts that the UI presents for the teacher
to confirm before they are written to the database.
"""

import re
import json
from typing import List, Dict, Optional, Callable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ── Patterns for common Synergy/MIS field text ────────────────────────────
_RE_PHONE  = re.compile(r"(?:0|\+44)\s?\d[\d\s\-]{8,11}")
_RE_YEAR   = re.compile(r"\bYear\s*(\d{1,2})\b", re.I)
_RE_FORM   = re.compile(r"\b([7-9]|1[0-3])[A-Z]\b")          # e.g. 9A, 10B
_RE_REFID  = re.compile(r"\b(\d{4,8})\b")                     # numeric ID
_RE_NAME   = re.compile(
    r"\b([A-Z][a-z]{1,20}(?:\s[A-Z][a-z]{1,20}){1,3})\b"    # Title Case words
)

# Common Synergy URL path fragments that indicate student-list pages
_LIST_PATH_HINTS = [
    "studentlist", "student_list", "students", "classlist",
    "class_list", "register", "pupillist", "pupil_list",
    "search", "directory",
]


class StudentDiscovery:
    """Discovers student records from a Synergy page."""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        on_progress: Optional[Callable[[str], None]] = None,
    ):
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        self.on_progress = on_progress or (lambda msg: None)

    # ── Public API ────────────────────────────────────────────────────────

    def discover_from_url(
        self,
        url: str,
        row_selector: str = "",
        name_selector: str = "",
        detail_url_selector: str = "",
        next_page_selector: str = "",
        max_pages: int = 20,
    ) -> List[Dict]:
        """
        Main entry point.
        If selectors are provided, uses mapped extraction.
        Otherwise falls back to heuristic scan.
        Returns list of candidate dicts ready for DB import.
        """
        visited: set = set()
        all_students: List[Dict] = []
        current_url = url

        for page_num in range(1, max_pages + 1):
            if current_url in visited:
                break
            visited.add(current_url)
            self.on_progress(f"Scanning page {page_num}: {current_url}")

            soup = self._fetch(current_url)
            if not soup:
                break

            if row_selector:
                found = self._extract_mapped(
                    soup, current_url,
                    row_selector, name_selector, detail_url_selector,
                )
            else:
                found = self._extract_heuristic(soup, current_url)

            all_students.extend(found)
            self.on_progress(f"  Found {len(found)} students on page {page_num}")

            # Follow pagination
            next_url = self._find_next_page(
                soup, current_url, next_page_selector
            )
            if not next_url or next_url in visited:
                break
            current_url = next_url

        # Deduplicate by name+ref
        seen = set()
        unique = []
        for s in all_students:
            key = (s.get("name","").lower(), s.get("student_ref",""))
            if key not in seen and s.get("name"):
                seen.add(key)
                unique.append(s)

        self.on_progress(
            f"Discovery complete — {len(unique)} unique students found"
        )
        return unique

    def discover_from_html(self, html: str, base_url: str = "") -> List[Dict]:
        """Run heuristic discovery on an already-fetched HTML string."""
        soup = BeautifulSoup(html, "html.parser")
        return self._extract_heuristic(soup, base_url)

    # ── Mapped extraction ─────────────────────────────────────────────────

    def _extract_mapped(
        self,
        soup: BeautifulSoup,
        base_url: str,
        row_selector: str,
        name_selector: str,
        detail_url_selector: str,
    ) -> List[Dict]:
        students = []
        rows = soup.select(row_selector)
        for row in rows:
            student: Dict = {}

            # Name
            if name_selector:
                el = row.select_one(name_selector)
                student["name"] = el.get_text(strip=True) if el else ""
            else:
                student["name"] = row.get_text(strip=True)[:60]

            # Detail page URL
            if detail_url_selector:
                link = row.select_one(detail_url_selector)
                if link and link.get("href"):
                    student["synergy_url"] = urljoin(base_url, link["href"])
            if not student.get("synergy_url"):
                link = row.select_one("a[href]")
                if link:
                    student["synergy_url"] = urljoin(base_url, link["href"])

            # Try to parse year/form from row text
            text = row.get_text(" ", strip=True)
            self._parse_common_fields(text, student)

            if student.get("name"):
                students.append(student)
        return students

    # ── Heuristic extraction ──────────────────────────────────────────────

    def _extract_heuristic(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """
        Scan the page for table rows or list items that look like student
        records, using text patterns.
        """
        students = []

        # Strategy 1: look for <table> rows
        for table in soup.find_all("table"):
            headers = [
                th.get_text(strip=True).lower()
                for th in table.find_all("th")
            ]
            # Only process tables that look like student lists
            if not any(h in " ".join(headers) for h in
                       ["name","student","pupil","year","form","class"]):
                continue
            col_map = self._map_columns(headers)
            for tr in table.find_all("tr")[1:]:
                cells = tr.find_all(["td","th"])
                student = self._student_from_cells(cells, col_map, base_url)
                if student:
                    students.append(student)

        # Strategy 2: look for repeated <li> or <div> blocks with name-like text
        if not students:
            students = self._scan_repeated_blocks(soup, base_url)

        # Strategy 3: flat text scan as last resort
        if not students:
            students = self._flat_text_scan(soup, base_url)

        return students

    def _map_columns(self, headers: List[str]) -> Dict[str, int]:
        """Map field names to column indices from table headers."""
        mapping = {}
        for i, h in enumerate(headers):
            if any(x in h for x in ["name","pupil","student"]):
                mapping.setdefault("name", i)
            if any(x in h for x in ["year","yr"]):
                mapping.setdefault("year_group", i)
            if any(x in h for x in ["form","class","group","reg"]):
                mapping.setdefault("form_class", i)
            if any(x in h for x in ["ref","id","number","no"]):
                mapping.setdefault("student_ref", i)
            if any(x in h for x in ["phone","tel","contact","mobile"]):
                mapping.setdefault("phone", i)
        return mapping

    def _student_from_cells(
        self,
        cells: list,
        col_map: Dict[str, int],
        base_url: str,
    ) -> Optional[Dict]:
        def cell_text(key):
            idx = col_map.get(key)
            if idx is not None and idx < len(cells):
                return cells[idx].get_text(strip=True)
            return ""

        name = cell_text("name")
        if not name or len(name) < 3:
            return None

        student: Dict = {"name": name}

        ref = cell_text("student_ref")
        if ref:
            student["student_ref"] = ref

        year_text = cell_text("year_group")
        if year_text:
            m = re.search(r"\d{1,2}", year_text)
            if m:
                y = int(m.group())
                if 7 <= y <= 13:
                    student["year_group"] = y

        form = cell_text("form_class")
        if form:
            student["form_class"] = form

        phone = cell_text("phone")
        if phone:
            student["phones"] = [phone]

        # Look for a detail-page link in any cell
        for cell in cells:
            link = cell.find("a", href=True)
            if link:
                href = link["href"]
                if any(x in href.lower() for x in ["student","pupil","profile","detail"]):
                    student["synergy_url"] = urljoin(base_url, href)
                    break

        # If no year yet, try parsing all cell text
        if "year_group" not in student:
            row_text = " ".join(c.get_text(" ", strip=True) for c in cells)
            self._parse_common_fields(row_text, student)

        return student

    def _scan_repeated_blocks(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Look for repeated div/li patterns that might be student cards."""
        students = []
        for container in soup.find_all(["ul","ol","div"], recursive=False):
            items = container.find_all(["li","div"], recursive=False)
            if len(items) < 3:
                continue
            # Check if items look homogeneous (similar structure)
            texts = [i.get_text(" ", strip=True) for i in items]
            names_found = [_RE_NAME.search(t) for t in texts]
            if sum(1 for n in names_found if n) < len(items) * 0.5:
                continue
            for item, text in zip(items, texts):
                m = _RE_NAME.search(text)
                if not m:
                    continue
                student: Dict = {"name": m.group(1)}
                self._parse_common_fields(text, student)
                link = item.find("a", href=True)
                if link:
                    student["synergy_url"] = urljoin(base_url, link["href"])
                students.append(student)
            if students:
                break
        return students

    def _flat_text_scan(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Last resort: find all Title Case names near student-like context."""
        students = []
        body_text = soup.get_text("\n", strip=True)
        lines = body_text.split("\n")
        for line in lines:
            line = line.strip()
            if len(line) < 4 or len(line) > 80:
                continue
            m = _RE_NAME.match(line)
            if m:
                student: Dict = {"name": m.group(1)}
                self._parse_common_fields(line, student)
                students.append(student)
        return students

    # ── Helpers ───────────────────────────────────────────────────────────

    def _parse_common_fields(self, text: str, student: Dict):
        if "year_group" not in student:
            m = _RE_YEAR.search(text)
            if m:
                y = int(m.group(1))
                if 7 <= y <= 13:
                    student["year_group"] = y

        if "form_class" not in student:
            m = _RE_FORM.search(text)
            if m:
                student["form_class"] = m.group(0)

        if "phones" not in student:
            phones = _RE_PHONE.findall(text)
            if phones:
                student["phones"] = [re.sub(r"\s+", " ", p).strip() for p in phones[:3]]

        if "student_ref" not in student:
            ids = _RE_REFID.findall(text)
            if ids:
                student["student_ref"] = ids[0]

    def _find_next_page(
        self,
        soup: BeautifulSoup,
        current_url: str,
        selector: str,
    ) -> Optional[str]:
        # Try explicit selector first
        if selector:
            el = soup.select_one(selector)
            if el and el.get("href"):
                return urljoin(current_url, el["href"])

        # Auto-detect: look for "Next", "›", "»" links
        for a in soup.find_all("a", href=True):
            label = a.get_text(strip=True).lower()
            if label in ("next", "›", "»", "next page", ">", "forward"):
                return urljoin(current_url, a["href"])

        # Look for rel="next"
        tag = soup.find("a", rel="next")
        if tag and tag.get("href"):
            return urljoin(current_url, tag["href"])

        return None

    def _fetch(self, url: str) -> Optional[BeautifulSoup]:
        try:
            r = self.session.get(url, timeout=15)
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            self.on_progress(f"  Fetch error: {e}")
            return None


# ── JS injected into embedded browser for live-page discovery ─────────────
# Returns all candidate student rows as JSON via pyBridge

DISCOVERY_JS = r"""
(function(){
    // Auto-detect the most likely student-list table or container
    var results = [];

    // Try tables first
    var tables = document.querySelectorAll('table');
    var bestTable = null, bestScore = 0;
    tables.forEach(function(t){
        var headers = Array.from(t.querySelectorAll('th')).map(function(h){
            return h.innerText.toLowerCase();
        });
        var combined = headers.join(' ');
        var score = 0;
        if(/name|student|pupil/.test(combined)) score += 3;
        if(/year|form|class/.test(combined)) score += 2;
        if(/phone|contact/.test(combined)) score += 1;
        var rowCount = t.querySelectorAll('tr').length;
        if(rowCount > 2) score += 1;
        if(score > bestScore){ bestScore = score; bestTable = t; }
    });

    if(bestTable && bestScore >= 3){
        var headers = Array.from(bestTable.querySelectorAll('th')).map(function(h){
            return h.innerText.trim().toLowerCase();
        });
        var nameCol = -1, yearCol = -1, formCol = -1, refCol = -1;
        headers.forEach(function(h,i){
            if(/name|student|pupil/.test(h) && nameCol<0) nameCol=i;
            if(/year|yr/.test(h) && yearCol<0) yearCol=i;
            if(/form|class|group|reg/.test(h) && formCol<0) formCol=i;
            if(/ref|id|number/.test(h) && refCol<0) refCol=i;
        });
        var rows = bestTable.querySelectorAll('tr');
        rows.forEach(function(tr, ri){
            if(ri===0) return;
            var cells = Array.from(tr.querySelectorAll('td'));
            if(cells.length < 2) return;
            var name = nameCol>=0 ? cells[nameCol] && cells[nameCol].innerText.trim() : '';
            if(!name) name = cells[0] ? cells[0].innerText.trim() : '';
            if(!name || name.length < 3) return;
            var link = tr.querySelector('a[href]');
            var entry = {
                name: name,
                year_group: yearCol>=0 && cells[yearCol] ? cells[yearCol].innerText.trim() : '',
                form_class: formCol>=0 && cells[formCol] ? cells[formCol].innerText.trim() : '',
                student_ref: refCol>=0 && cells[refCol] ? cells[refCol].innerText.trim() : '',
                synergy_url: link ? link.href : ''
            };
            results.push(entry);
        });
    }

    // Fallback: look for repeated anchor text matching Title Case names
    if(results.length === 0){
        var links = document.querySelectorAll('a[href]');
        links.forEach(function(a){
            var t = a.innerText.trim();
            if(/^[A-Z][a-z]+ [A-Z][a-z]+/.test(t) && t.length < 60){
                results.push({name: t, synergy_url: a.href,
                               year_group:'', form_class:'', student_ref:''});
            }
        });
    }

    try {
        window.pyBridge.receiveDiscovery(JSON.stringify(results));
    } catch(e) {
        console.warn('discovery bridge error', e);
    }
    return results.length;
})();
"""
