import re
import time
import urllib.parse as _url
from typing import List, Tuple, Dict, Optional

import requests
from bs4 import BeautifulSoup

# -----------------------------------------------------
# Offizielle §0-Seite (Inhaltsverzeichnis) im RIS
# -----------------------------------------------------
RIS_TOC_URL = "https://www.ris.bka.gv.at/NormDokument.wxe"

DEFAULT_HEADERS = {
    "User-Agent": "RIS-Law-Scraper/1.1 (+https://github.com/yourrepo; contact: you@example.com)"
}

_AUFGEHOBEN_MARKERS = ["aufgehoben", "weggefallen"]

# Einzel-§: erlaube auch Buchstabenanhänge (z. B. § 2a)
_RE_PARA_SINGLE = re.compile(r"§\s*(\d+[a-zA-Z]?)", re.IGNORECASE)
# Ranges: § 3 bis 7, § 10–15, § 21-23, etc.
_RE_RANGE = re.compile(r"§\s*(\d+)\s*(?:bis|-|–)\s*§?\s*(\d+)", re.IGNORECASE)
# Fragment-Anker in Hrefs:  #Paragraf12  oder  #Paragraf12a
_RE_HREF_ANCHOR = re.compile(r"#\s*Paragraf\s*([0-9]+[a-zA-Z]?)", re.IGNORECASE)


def _normalize_para_id(s: str) -> str:
    s = s.strip()
    if not s.startswith("§"):
        s = "§ " + s
    # § 1a → § 1a (einheitliche Spationierung)
    s = re.sub(r"§\s*(\d+)\s*([a-zA-Z]?)", lambda m: f"§ {m.group(1)}{m.group(2)}", s)
    return s


def _extract_paragraph_from_href(href: str) -> Optional[str]:
    """
    Holt §-Kennungen aus href:
      - ...?Paragraf=12
      - ...#Paragraf12   bzw. #Paragraf12a
    """
    try:
        # 1) Query-Parameter prüfen (…Paragraf=12)
        qs = _url.urlparse(href).query
        params = _url.parse_qs(qs)
        raw = params.get("Paragraf", [None])[0]
        if raw:
            raw = raw.strip()
            return _normalize_para_id(raw if raw.startswith("§") else f"§ {raw}")

        # 2) Fragment/Anker prüfen (…#Paragraf12)
        m = _RE_HREF_ANCHOR.search(href)
        if m:
            return _normalize_para_id(m.group(1))

        return None
    except Exception:
        return None


def _has_aufgehoben_marker(text: str) -> bool:
    t = (text or "").lower()
    return any(marker in t for marker in _AUFGEHOBEN_MARKERS)


def fetch_toc_html(
    gesetzesnummer: str = "10002296",
    fassung_vom: Optional[str] = None,
    timeout: int = 60,
    tries: int = 3,
    headers: Optional[Dict[str, str]] = None,
) -> str:
    headers = {**DEFAULT_HEADERS, **(headers or {})}
    params = {
        "Abfrage": "Bundesnormen",
        "Gesetzesnummer": gesetzesnummer,
        "Paragraf": "0",          # §0: Inhaltsverzeichnis
        "Uebergangsrecht": "",
        "Anlage": "",
        "Artikel": "",
    }
    if fassung_vom:
        params["FassungVom"] = fassung_vom

    last = None
    for i in range(tries):
        r = requests.get(RIS_TOC_URL, params=params, headers=headers, timeout=timeout)
        last = r
        if r.status_code == 200 and len(r.text) > 2000:
            return r.text
        time.sleep(1.5 * (i + 1))
    if last is not None:
        last.raise_for_status()
        return last.text
    raise RuntimeError("Unbekannter Fehler beim Laden der TOC-Seite")


def parse_toc(html: str, include_aufgehoben: bool = False) -> Tuple[List[str], List[str]]:
    soup = BeautifulSoup(html, "html.parser")
    para_ids: List[str] = []
    aufgehoben_ids: List[str] = []

    # -----------------------------
    # 1) Links mit Paragraf=... ODER #Paragraf...
    # -----------------------------
    for a in soup.find_all("a", href=True):
        href = a["href"] or ""
        if ("Paragraf=" not in href) and ("#Paragraf" not in href and "#paragraf" not in href):
            # nicht relevant
            continue
        para = _extract_paragraph_from_href(href)
        if not para:
            continue

        # Kontexttext prüfen (für "aufgehoben"/"weggefallen")
        text_block = " ".join(a.get_text(" ", strip=True).split())
        parent_text = a.find_parent().get_text(" ", strip=True) if a.find_parent() else ""
        context = f"{text_block} {parent_text}".strip()
        if _has_aufgehoben_marker(context):
            aufgehoben_ids.append(para)

        para_ids.append(para)

    # -----------------------------
    # 2) Textuelle Fallbacks: Ranges und einzelne § im Volltext
    # -----------------------------
    # Hinweis: \n als Separator behält etwas Struktur (manche Layouts verlieren sonst §-Folgen)
    text_all = soup.get_text("\n", strip=True)

    # Ranges zuerst expandieren (z. B. "§ 2 bis § 5")
    for m in _RE_RANGE.finditer(text_all):
        start, end = int(m.group(1)), int(m.group(2))
        # Schutz gegen abwegige Matches
        if start <= end and (end - start) < 5000:
            for n in range(start, end + 1):
                para_ids.append(_normalize_para_id(str(n)))

    # Einzel-§ (z. B. "§ 12", "§ 12a")
    for m in _RE_PARA_SINGLE.finditer(text_all):
        para_ids.append(_normalize_para_id(m.group(1)))

    # -----------------------------
    # 3) Deduplizieren & Sortieren & §0 herausfiltern
    # -----------------------------
    def _sort_key(p: str):
        m = re.match(r"§\s*(\d+)([a-zA-Z]?)$", p)
        if not m:
            return (10**9, p)
        return (int(m.group(1)), m.group(2) or "")

    # Set + Sort
    para_set = sorted(set(para_ids), key=_sort_key)
    aufgehoben_set = sorted(set(aufgehoben_ids), key=_sort_key)

    # § 0 (TOC) grundsätzlich nicht als "echter" Paragraph
    para_set = [p for p in para_set if p.strip().lower() not in {"§ 0", "§0"}]

    # Aufgehobene ggf. rausfiltern
    if not include_aufgehoben:
        para_set = [p for p in para_set if p not in aufgehoben_set]

    return para_set, aufgehoben_set


def get_current_abgb_paragraphs(
    gesetzesnummer: str = "10001622",
    fassung_vom: Optional[str] = None,
    include_aufgehoben: bool = False,
) -> Dict[str, List[str]]:
    """
    Liefert Paragraphenliste + Aufhebungen für die 'geltende Fassung' (oder ein Datum).
    Rückgabeform:
      {
        "gesetzesnummer": "...",
        "fassung_vom": "YYYY-MM-DD" | "geltende Fassung",
        "count": <int>,
        "paragraphs": [...],
        "aufgehoben": [...]
      }
    """
    html = fetch_toc_html(gesetzesnummer=gesetzesnummer, fassung_vom=fassung_vom)
    paragraphs, aufgehoben = parse_toc(html, include_aufgehoben=include_aufgehoben)
    return {
        "gesetzesnummer": gesetzesnummer,
        "fassung_vom": fassung_vom or "geltende Fassung",
        "count": len(paragraphs),
        "paragraphs": paragraphs,
        "aufgehoben": aufgehoben,
    }