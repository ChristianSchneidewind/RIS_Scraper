# ris_abgb/html_parser.py
import re
from bs4 import BeautifulSoup

from .http_client import HttpClient

_RX_NOR = re.compile(r"\b(NOR\d{5,})\b", re.IGNORECASE)
_RX_NOR_LINK = re.compile(r"/Dokumente/[^/]+/(NOR\d{5,})/(?:\1)\.html", re.IGNORECASE)

def _get_with_retry(url: str, tries: int = 3, timeout: int = 120, client: HttpClient | None = None):
    client = client or HttpClient(retries=tries)
    return client.get(url, timeout=timeout, allow_redirects=True, min_content_length=500)

def _strip_obvious_nav(soup: BeautifulSoup):
    # Navigations-/Meta-Bereiche entfernen, wenn vorhanden
    for sel in [
        "header", "nav", "footer",
        "#menu", ".menu", ".breadcrumb", ".nav", ".breadcrumbs",
        "#header", "#footer", ".footer", ".header",
        ".druck", ".druckansicht", "#druck", "#print"
    ]:
        for n in soup.select(sel):
            n.decompose()

def _extract_nors_from_html(html: str) -> list[str]:
    """Extrahiert alle NOR-IDs, die im Text vorkommen oder als Dokument-Links eingebunden sind."""
    nors = set()
    for m in _RX_NOR.finditer(html):
        nors.add(m.group(1))
    for m in _RX_NOR_LINK.finditer(html):
        nors.add(m.group(1))
    return sorted(nors)

def resolve_nor_urls_from_toc_url(toc_url: str, *, client: HttpClient | None = None) -> list[str]:
    """
    Nimmt eine §-Seiten-URL (NormDokument.wxe?...&Paragraf=...) und liefert
    alle dazugehörigen *kanonischen* NOR-HTML-URLs.
    Falls nichts gefunden wird, wird die Eingabe-URL als Fallback zurückgegeben.
    """
    r = _get_with_retry(toc_url, client=client)
    html = r.text
    nors = _extract_nors_from_html(html)
    if not nors:
        m = _RX_NOR.search(html)
        if m:
            nors = [m.group(1)]
    if not nors:
        return [toc_url]  # Fallback: wenigstens diese Seite verarbeiten

    base = "https://www.ris.bka.gv.at/Dokumente/Bundesnormen"
    return [f"{base}/{nor}/{nor}.html" for nor in nors]

def fetch_paragraph_text_via_html(url: str, *, client: HttpClient | None = None) -> dict:
    """
    Lädt eine (NOR- oder §-)HTML-Seite und extrahiert Überschrift, Text und NOR.
    """
    if not url:
        return {"heading": "", "text": "", "nor": ""}

    r = _get_with_retry(url, client=client)
    html = r.text
    soup = BeautifulSoup(html, "html.parser")
    _strip_obvious_nav(soup)

    m = _RX_NOR.search(html)
    nor = m.group(1) if m else ""

    candidates = [
        soup.select_one("div#content div.norm"),
        soup.select_one("div#content div.dokument"),
        soup.select_one("div#content"),
        soup.select_one("div.content"),
        soup.select_one("article"),
        soup.select_one("main"),
        soup.body,
    ]

    for cand in candidates:
        if not cand:
            continue
        h = cand.find(["h1", "h2", "h3"])
        heading = h.get_text(strip=True) if h else ""
        text = cand.get_text("\n", strip=True)
        if text and len(text) >= 50:
            return {"heading": heading, "text": text, "nor": nor}

    full = soup.get_text("\n", strip=True)
    if full and len(full) >= 50:
        return {"heading": "", "text": full, "nor": nor}
    return {"heading": "", "text": full or "", "nor": nor}

def extract_para_id(s: str) -> str:
    m = re.search(r"(§+\s*\d+[a-zA-Z]*)", s or "")
    return m.group(1).strip() if m else ""