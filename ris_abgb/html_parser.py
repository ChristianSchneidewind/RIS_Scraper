import re
import requests
from bs4 import BeautifulSoup
from .config import USER_AGENT

_RX_NOR = re.compile(r"\b(NOR\d{5,})\b", re.IGNORECASE)

def fetch_paragraph_text_via_html(url: str) -> dict:
    """
    Lädt die Bundesnormen-HTML und extrahiert Überschrift, Text und NOR.
    """
    if not url:
        return {"heading": "", "text": "", "nor": ""}

    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
    r.raise_for_status()
    html = r.text
    soup = BeautifulSoup(html, "html.parser")
    m = _RX_NOR.search(html)
    nor = m.group(1) if m else ""

    candidates = [
        soup.find("div", {"id": "content"}),
        soup.find("div", {"class": "content"}),
        soup.find("div", {"class": "norm"}),
        soup.find("body"),
    ]

    for cand in candidates:
        if cand:
            heading = (cand.find("h1") or cand.find("h2") or cand.find("h3"))
            heading = heading.get_text(strip=True) if heading else ""
            text = cand.get_text("\n", strip=True)
            if text:
                return {"heading": heading, "text": text, "nor": nor}

    full = soup.get_text("\n", strip=True)
    return {"heading": "", "text": full, "nor": nor}


def extract_para_id(s: str) -> str:
    m = re.search(r"(§+\s*\d+[a-zA-Z]*)", s or "")
    return m.group(1).strip() if m else ""
