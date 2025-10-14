import re
import requests
from bs4 import BeautifulSoup
from .config import USER_AGENT

def fetch_paragraph_text_via_html(url: str) -> dict:
    """
    Lädt die Bundesnormen-HTML und extrahiert heading + text.
    """
    if not url:
        return {"heading": "", "text": ""}

    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    candidates = [
        ("div", {"id": "content"}),
        ("div", {"class": "content"}),
        ("div", {"class": "norm"}),
        ("article", {}),
        ("main", {}),
    ]
    main = None
    for name, attrs in candidates:
        main = soup.find(name, attrs=attrs)
        if main:
            break
    if not main:
        full = soup.get_text("\n", strip=True)
        return {"heading": "", "text": full}

    heading_el = main.find(["h1", "h2"]) or soup.find(["h1", "h2"])
    heading = heading_el.get_text(" ", strip=True) if heading_el else ""

    for sel in ["nav", "header", "footer", ".breadcrumb", ".toolbar", ".meta", ".buttons"]:
        for junk in main.select(sel):
            junk.decompose()

    text = main.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return {"heading": heading, "text": text}

def extract_para_id(s: str) -> str:
    m = re.search(r"(§+\s*\d+[a-zA-Z]*)", s or "")
    return m.group(1).strip() if m else ""
