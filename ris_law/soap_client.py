import requests
from lxml import etree
from .config import BASE_URL, NS_SOAP, NS_SVC, HEADERS_SOAP, USER_AGENT

def soap_envelope(inner_xml: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        f'xmlns:soap="{NS_SOAP}"><soap:Body>{inner_xml}</soap:Body></soap:Envelope>'
    )

def post_soap(action: str, body_xml: str, timeout: int = 120) -> etree._Element:
    h = dict(HEADERS_SOAP)
    h["SOAPAction"] = action
    h["User-Agent"] = USER_AGENT
    resp = requests.post(BASE_URL, data=body_xml.encode("utf-8"), headers=h, timeout=timeout)
    try:
        with open("last_envelope_raw.xml", "w", encoding="utf-8") as dbg:
            dbg.write(resp.text)
    except Exception:
        pass
    resp.raise_for_status()
    return etree.fromstring(resp.content)

def result_embedded_xml(res: etree._Element) -> str:
    if res is None:
        return ""
    if len(res):
        return "".join(etree.tostring(child, encoding="unicode") for child in res)
    return (res.text or "").strip()

def version_check() -> None:
    try:
        body = f'<Version xmlns="{NS_SVC}"/>'
        post_soap(f"{NS_SVC}/Version", soap_envelope(body))
        print("[OK] Version-Call")
    except Exception as e:
        print("[WARN] Version-Call:", e)


# ---------------------------------------------------------------------------
# Metadaten via HTML (§0/Art.0) – robuste Extraktion
# ---------------------------------------------------------------------------


from typing import Dict, Optional, Tuple, Iterable
import re
from urllib.parse import urlencode
from bs4 import BeautifulSoup, NavigableString, Tag

RIS_NORMDOK_BASE = "https://www.ris.bka.gv.at/NormDokument.wxe"

_HTML_HEADERS = {
    "User-Agent": USER_AGENT or "Mozilla/5.0 (compatible; RISLawMeta/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_AT_MONTHS = {
    "jänner": 1, "jaenner": 1, "januar": 1,
    "februar": 2,
    "märz": 3, "maerz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}

def _normalize_ws(s: str) -> str:
    if not s:
        return s
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def _normalize_date(d: str) -> str:
    if not d:
        return d
    s = _normalize_ws(d)
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        dd, mm, yyyy = m.groups()
        return f"{yyyy}-{int(mm):02d}-{int(dd):02d}"
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        yyyy, mm, dd = m.groups()
        return f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d}"
    m = re.match(r"(\d{1,2})\.\s*([A-Za-zäöüÄÖÜß]+)\.?\s+(\d{4})", s, flags=re.IGNORECASE)
    if m:
        dd, mon, yyyy = m.groups()
        mon_key = (
            mon.lower()
            .replace("ä","ae").replace("ö","oe").replace("ü","ue").replace("ß","ss")
        )
        if mon_key in _AT_MONTHS:
            mm = _AT_MONTHS[mon_key]
            return f"{int(yyyy):04d}-{mm:02d}-{int(dd):02d}"
    return s

# Sehr großzügige Datums-Suche im Plaintext
_DATE_RX = re.compile(
    r"(?P<d>\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}\.\s*[A-Za-zäöüÄÖÜß]+\.?\s+\d{4}|\d{4}-\d{1,2}-\d{1,2})"
)

def _iter_forward_text_after(node: Tag, stop_at_h3: bool = True, max_nodes: int = 25) -> Iterable[str]:
    """
    Geht ab 'node' in Dokumentreihenfolge weiter und liefert Textstücke,
    bis max_nodes erreicht sind oder (optional) das nächste <h3> kommt.
    """
    count = 0
    cur = node.next_sibling
    while cur and count < max_nodes:
        if isinstance(cur, NavigableString):
            txt = _normalize_ws(str(cur))
            if txt:
                yield txt
        elif isinstance(cur, Tag):
            if stop_at_h3 and cur.name and cur.name.lower() == "h3":
                break
            # eigener Text
            t = _normalize_ws(cur.get_text(" ", strip=True))
            if t:
                yield t
        count += 1
        cur = cur.next_sibling

def _find_date_near_heading(soup: BeautifulSoup, heading_keywords: Iterable[str]) -> Optional[str]:
    """
    Sucht ein <h3>, dessen Text einen der 'heading_keywords' enthält,
    und findet das erste Datum im nachfolgenden Text (einige Geschwister weiter),
    bevor das nächste <h3> beginnt.
    """
    for h in soup.find_all("h3"):
        htxt = _normalize_ws(h.get_text(" ", strip=True)).lower()
        if any(kw in htxt for kw in heading_keywords):
            # 1) direkt im selben Container?
            parent_text = _normalize_ws(h.parent.get_text(" ", strip=True)) if h.parent else ""
            if parent_text:
                m = _DATE_RX.search(parent_text)
                if m:
                    return _normalize_date(m.group("d"))
            # 2) in den nächsten Geschwistern (bis zum nächsten <h3>)
            for chunk in _iter_forward_text_after(h, stop_at_h3=True, max_nodes=20):
                m = _DATE_RX.search(chunk)
                if m:
                    return _normalize_date(m.group("d"))
    return None

def _fetch_ris_html(gesetzesnummer: str) -> Optional[str]:
    base = {"Abfrage": "Bundesnormen", "Gesetzesnummer": gesetzesnummer, "Uebergangsrecht": "", "Anlage": ""}
    for key, val in (("Paragraf", "0"), ("Artikel", "0"), ("Paragraf", "1"), ("Artikel", "1")):
        q = dict(base); q[key] = val
        url = f"{RIS_NORMDOK_BASE}?{urlencode(q)}"
        try:
            r = requests.get(url, headers=_HTML_HEADERS, timeout=30)
            if r.status_code == 200 and "<html" in r.text.lower():
                return r.text
        except requests.RequestException:
            pass
    return None

def _extract_title(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.string:
        t = _normalize_ws(soup.title.string)
        if t: return t
    h1 = soup.find("h1")
    if h1:
        t = _normalize_ws(h1.get_text(" ", strip=True))
        if t: return t
    return None

def get_law_metadata(gesetzesnummer: str) -> Dict[str, Optional[str]]:
    """
    Liefert: date_in_force, date_out_of_force, kundmachungsdatum, title.
    Strategie:
      - §0/Art.0 laden
      - Datum direkt „nahe“ den <h3>-Überschriften suchen
      - sonst breiter Fallback im Plaintext
    """
    html = _fetch_ris_html(gesetzesnummer)
    if not html:
        return {"date_in_force": None, "date_out_of_force": None, "kundmachungsdatum": None, "title": None}

    soup = BeautifulSoup(html, "lxml")
    title = _extract_title(html)

    # 1) gezielt an den Überschriften suchen
    date_in  = _find_date_near_heading(soup, ("inkrafttret",))
    date_out = _find_date_near_heading(soup, ("außerkraft", "ausserkraft"))
    date_pub = _find_date_near_heading(soup, ("kundmachungsdatum", "kundmachung"))

    # 2) Fallback: ganzer Plaintext
    if not (date_in and date_pub):
        txt = _normalize_ws(soup.get_text(" ", strip=True))
        m_in  = re.search(r"tritt\s+mit\s+" + _DATE_RX.pattern + r"\s+in\s+kraft", txt, flags=re.IGNORECASE)
        m_pub = re.search(r"\bBGBl\b[^.,;]*?\bvom\s+" + _DATE_RX.pattern, txt, flags=re.IGNORECASE)
        if not date_in and m_in:
            date_in = _normalize_date(m_in.group(1))
        if not date_pub and m_pub:
            date_pub = _normalize_date(m_pub.group(1))

    return {
        "date_in_force": date_in,
        "date_out_of_force": date_out,
        "kundmachungsdatum": date_pub,
        "title": title,
    }

def parse_dates_from_html(html: str) -> dict:
    """
    Extrahiert date_in_force, date_out_of_force, kundmachungsdatum aus einer
    RIS-HTML-Seite (egal ob Gesetzes- oder Einheitsseite).
    Nutzt die vorhandenen Normalizer/Heuristiken in dieser Datei.
    """
    if not html:
        return {"date_in_force": None, "date_out_of_force": None, "kundmachungsdatum": None}

    soup = BeautifulSoup(html, "lxml")

    date_in  = _find_date_near_heading(soup, ("inkrafttret",))
    date_out = _find_date_near_heading(soup, ("außerkraft", "ausserkraft"))
    date_pub = _find_date_near_heading(soup, ("kundmachungsdatum", "kundmachung"))

    # großzügiger Fallback auf Fließtext (BGBl / „tritt mit … in Kraft“)
    if not (date_in and date_pub):
        txt = _normalize_ws(soup.get_text(" ", strip=True))
        m_in  = re.search(r"tritt\s+mit\s+" + _DATE_RX.pattern + r"\s+in\s+kraft", txt, flags=re.IGNORECASE)
        m_pub = re.search(r"\bBGBl\b[^.,;]*?\bvom\s+" + _DATE_RX.pattern, txt, flags=re.IGNORECASE)
        if not date_in and m_in:
            date_in = _normalize_date(m_in.group("d") if "d" in m_in.groupdict() else m_in.group(1))
        if not date_pub and m_pub:
            date_pub = _normalize_date(m_pub.group("d") if "d" in m_pub.groupdict() else m_pub.group(1))

    return {
        "date_in_force": date_in,
        "date_out_of_force": date_out,
        "kundmachungsdatum": date_pub,
    }
