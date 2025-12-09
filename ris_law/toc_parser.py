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


def _extract_paragraph_from_href(href: str) -> Optional[str]:
    """
    Extrahiert "§"-IDs aus Links wie:
      - ?Paragraf=1
      - ?Paragraf=1a
      - #Paragraf1
      - #Paragraf1a
    """
    # Direkte Query ?Paragraf=...
    parsed = _url.urlparse(href)
    qs = _url.parse_qs(parsed.query)
    if "Paragraf" in qs and qs["Paragraf"]:
        return qs["Paragraf"][0].strip()

    # oder Anker #Paragraf1 (bzw. #paragraf1)
    m = re.search(r"#(?:Paragraf|paragraf)(\d+[a-zA-Z]?)", href)
    if m:
        return m.group(1).strip()

    return None


def _has_aufgehoben_marker(text: str) -> bool:
    """
    Ermittelt, ob im Kontexttext erkennbar ist, dass die Norm "aufgehoben"
    bzw. "weggefallen" ist.
    """
    text_low = text.lower()
    # typische Muster
    if "aufgehoben" in text_low:
        return True
    if "weggefallen" in text_low:
        return True
    if "tritt außer kraft" in text_low:
        return True
    return False


def fetch_toc_html(
    gesetzesnummer: str = "10002296",
    fassung_vom: Optional[str] = None,
    timeout: int = 20,
    tries: int = 2,
    headers: Optional[Dict[str, str]] = None,
) -> str:
    """
    Lädt die Inhaltsverzeichnis-Seite (§ 0) für ein Gesetz aus dem RIS.

    - timeout: Timeout pro HTTP-Request in Sekunden
    - tries:   Anzahl der Versuche, bevor ein Fehler geworfen wird

    NEU:
      - kürzeres Timeout und weniger Versuche, damit das Skript nicht ewig "hängt"
      - Debug-Ausgaben, damit man sieht, ob der TOC-Request überhaupt rausgeht
    """
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

    last: Optional[requests.Response] = None

    for i in range(tries):
        attempt = i + 1
        print(
            f"[RIS] TOC-Request ({attempt}/{tries}) für Gesetzesnummer "
            f"{gesetzesnummer} (Paragraf=0)..."
        )
        try:
            r = requests.get(RIS_TOC_URL, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            print(f"[RIS] Fehler beim TOC-Request (Versuch {attempt}): {e}")
            last = None
            # kleiner Backoff, bevor erneut versucht wird
            time.sleep(1.5 * attempt)
            continue

        last = r
        text_len = len(r.text or "")
        if r.status_code == 200 and text_len > 2000:
            print(f"[RIS] TOC erfolgreich geladen (Status=200, Länge={text_len}).")
            return r.text

        print(
            f"[RIS] Unerwartete TOC-Antwort (Status={r.status_code}, Länge={text_len}) "
            f"für Gesetzesnummer {gesetzesnummer} – neuer Versuch..."
        )
        time.sleep(1.5 * attempt)

    # Nach allen Versuchen
    if last is not None:
        print(
            f"[RIS] Letzter TOC-Versuch fehlgeschlagen "
            f"(Status={last.status_code}, Länge={len(last.text or '')})."
        )
        # raise_for_status wirft eine aussagekräftige Exception
        last.raise_for_status()
        return last.text

    raise RuntimeError(f"Fehler beim Laden der TOC-Seite für Gesetzesnummer {gesetzesnummer}")


def parse_toc(html: str, include_aufgehoben: bool = True) -> Tuple[List[str], List[str]]:
    """
    Parst die Inhaltsverzeichnis-Seite und extrahiert:
      - Liste aller Paragraph-IDs (z.B. "1", "1a", "2", "3", ...)
      - Liste "aufgehobener" Paragraph-IDs, sofern erkennbar

    include_aufgehoben:
      - True:  aufhebungs-Marker werden ausgewertet
      - False: aufhebungsstatus wird ignoriert
    """
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

    # Wenn nichts gefunden wurde, versuchen wir einen heuristischen Fallback über
    # den Volltext, z.B. für exotische Layouts.
    if not para_ids:
        text = soup.get_text(" ", strip=True)
        # Erkennung von Mustern wie "§ 1", "§ 1a", "§ 3 bis 7"
        matches = re.findall(r"§\s*(\d+[a-zA-Z]?)", text)
        para_ids.extend(matches)

        # Aufhebungs-Marker heuristisch erkennen
        if include_aufgehoben:
            # z.B. "§ 3 (aufgehoben)", "§ 4 (weggefallen)"
            aufhebungs_matches = re.findall(
                r"§\s*(\d+[a-zA-Z]?).{0,30}?(aufgehoben|weggefallen)",
                text,
                flags=re.IGNORECASE,
            )
            aufgehoben_ids.extend([m[0] for m in aufhebungs_matches])

    # Deduplizieren & sortieren
    def _sort_key(pid: str):
        # Split in numerischen Teil + Buchstaben
        m = re.match(r"(\d+)([a-zA-Z]?)", pid)
        if not m:
            return (999999, pid)
        num = int(m.group(1))
        letter = m.group(2)
        return (num, letter)

    para_ids = sorted(set(para_ids), key=_sort_key)
    aufgehoben_ids = sorted(set(aufgehoben_ids), key=_sort_key)

    if not include_aufgehoben:
        return para_ids, []

    # Nur Paragraphen, die in para_ids vorkommen, als aufgehoben markieren
    aufgehoben_ids = [pid for pid in aufgehoben_ids if pid in para_ids]

    return para_ids, aufgehoben_ids


def get_current_abgb_paragraphs(
    gesetzesnummer: str,
    fassung_vom: Optional[str] = None,
    include_aufgehoben: bool = True,
) -> Dict[str, object]:
    """
    High-Level-Funktion, die die aktuelle Liste von Paragraphen liefert.

    Rückgabe-Format:
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
