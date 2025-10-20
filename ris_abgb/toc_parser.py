import re
import time
import urllib.parse as _url
from typing import List, Tuple, Dict, Optional

import requests
from bs4 import BeautifulSoup

# -----------------------------------------------------
# Offizielle §0-Seite (Inhaltsverzeichnis) des ABGB im RIS
# -----------------------------------------------------
RIS_TOC_URL = "https://www.ris.bka.gv.at/NormDokument.wxe"

DEFAULT_HEADERS = {
    "User-Agent": "RIS-ABGB-Scraper/1.1 (+https://github.com/yourrepo; contact: you@example.com)"
}

_AUFGEHOBEN_MARKERS = ["aufgehoben", "weggefallen"]

_RE_PARA_SINGLE = re.compile(r"§\s*(\d+[a-z]?)", re.IGNORECASE)
_RE_RANGE = re.compile(r"§\s*(\d+)\s*(?:bis|-|–)\s*§?\s*(\d+)", re.IGNORECASE)


def _normalize_para_id(s: str) -> str:
    s = s.strip()
    if not s.startswith("§"):
        s = "§ " + s
    s = re.sub(r"§\s*(\d+)\s*([a-z]?)", lambda m: f"§ {m.group(1)}{m.group(2)}", s)
    return s


def _extract_paragraph_from_href(href: str) -> Optional[str]:
    try:
        qs = _url.urlparse(href).query
        params = _url.parse_qs(qs)
        raw = params.get("Paragraf", [None])[0]
        if not raw:
            return None
        raw = raw.strip()
        return _normalize_para_id(raw if raw.startswith("§") else f"§ {raw}")
    except Exception:
        return None


def _has_aufgehoben_marker(text: str) -> bool:
    t = (text or "").lower()
    return any(marker in t for marker in _AUFGEHOBEN_MARKERS)


def fetch_toc_html(
    gesetzesnummer: str = "10001622",
    fassung_vom: Optional[str] = None,
    timeout: int = 60,
    tries: int = 3,
    headers: Optional[Dict[str, str]] = None,
) -> str:
    headers = {**DEFAULT_HEADERS, **(headers or {})}
    params = {
        "Abfrage": "Bundesnormen",
        "Gesetzesnummer": gesetzesnummer,
        "Paragraf": "0",
        "Uebergangsrecht": "",
        "Anlage": "",
        "Artikel": "",
    }
    if fassung_vom:
        params["FassungVom"] = fassung_vom

    for i in range(tries):
        r = requests.get(RIS_TOC_URL, params=params, headers=headers, timeout=timeout)
        if r.status_code == 200 and len(r.text) > 2000:
            return r.text
        time.sleep(1.5 * (i + 1))
    r.raise_for_status()
    return r.text


def parse_toc(html: str, include_aufgehoben: bool = False) -> Tuple[List[str], List[str]]:
    soup = BeautifulSoup(html, "html.parser")
    para_ids: List[str] = []
    aufgehoben_ids: List[str] = []

    # 1) Links mit Paragraf=...
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "Paragraf=" not in href:
            continue
        para = _extract_paragraph_from_href(href)
        if not para:
            continue
        text_block = " ".join(a.get_text(" ", strip=True).split())
        context = text_block + " " + (a.find_parent().get_text(" ", strip=True) if a.find_parent() else "")
        if _has_aufgehoben_marker(context):
            aufgehoben_ids.append(para)
        para_ids.append(para)

    # 2) Textuelle Fallbacks: Ranges und Einzel-§
    text_all = soup.get_text(" ", strip=True)
    for m in _RE_RANGE.finditer(text_all):
        start, end = int(m.group(1)), int(m.group(2))
        if start <= end and (end - start) < 2000:
            for n in range(start, end + 1):
                para_ids.append(_normalize_para_id(str(n)))
    for m in _RE_PARA_SINGLE.finditer(text_all):
        para_ids.append(_normalize_para_id(m.group(1)))

    # 3) Deduplizieren & sortieren
    def _sort_key(p: str):
        m = re.match(r"§\s*(\d+)([a-z]?)$", p)
        if not m:
            return (10**9, p)
        return (int(m.group(1)), m.group(2) or "")

    para_set = sorted(set(para_ids), key=_sort_key)
    aufgehoben_set = sorted(set(aufgehoben_ids), key=_sort_key)

    if not include_aufgehoben:
        para_set = [p for p in para_set if p not in aufgehoben_set]

    return para_set, aufgehoben_set


def get_current_abgb_paragraphs(
    gesetzesnummer: str = "10001622",
    fassung_vom: Optional[str] = None,
    include_aufgehoben: bool = False,
) -> Dict[str, List[str]]:
    html = fetch_toc_html(gesetzesnummer=gesetzesnummer, fassung_vom=fassung_vom)
    paragraphs, aufgehoben = parse_toc(html, include_aufgehoben=include_aufgehoben)
    return {
        "gesetzesnummer": gesetzesnummer,
        "fassung_vom": fassung_vom or "geltende Fassung",
        "count": len(paragraphs),
        "paragraphs": paragraphs,
        "aufgehoben": aufgehoben,
    }
