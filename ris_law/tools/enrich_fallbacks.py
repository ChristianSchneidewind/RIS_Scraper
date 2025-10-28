#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.parse as _url
from pathlib import Path
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

# ---------- Einstellungen ----------
DEFAULT_HEADERS = {
    "User-Agent": "RIS-Law-FallbackEnricher/LowMem+Robust (+https://github.com/yourrepo)"
}
REQUEST_TIMEOUT = 30
TOC_BASE = "https://www.ris.bka.gv.at/NormDokument.wxe"

PROBE_ON_EMPTY_TOC = True
PROBE_MAX = 800
PROBE_CONSEC_MISS = 40
PROBE_DELAY = 0.3  # langsamer, aber stabiler

CACHE_DIR = Path("cache_toc")  # kleiner Cache nur für TOCs
CACHE_MAX_AGE_DAYS = 7
SLEEP_BETWEEN_LAWS = 0.8       # kleine Pause zwischen Gesetzen

_RX_NUM = re.compile(r"§\s*(\d+)", re.IGNORECASE)
_RE_PARA_SINGLE = re.compile(r"§\s*(\d+[a-zA-Z]?)", re.IGNORECASE)
_RE_ART_SINGLE  = re.compile(r"(?:Art\.|Artikel)\s*(\d+[a-zA-Z]?)", re.IGNORECASE)
_RE_HREF_ART    = re.compile(r"Artikel\s*=\s*(\d+)", re.IGNORECASE)
_RE_HREF_PAR    = re.compile(r"Paragraf\s*=\s*(\d+)", re.IGNORECASE)


# ---------- Logging ----------
def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------- HTTP robust + Cache (nur TOC) ----------
class NotFound404(Exception):
    pass

def http_get(url: str, timeout: int = REQUEST_TIMEOUT, tries: int = 3, backoff: float = 1.7) -> str:
    """Robuster GET mit Retry/Backoff. Wirft NotFound404 bei 404, sonst Requests-Fehler nach letztem Versuch."""
    last_exc = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
            if r.status_code == 404:
                raise NotFound404(f"404 for {url}")
            r.raise_for_status()
            return r.text
        except NotFound404:
            raise
        except requests.RequestException as e:
            last_exc = e
            # kurzer Backoff, dann nochmal
            time.sleep((backoff ** i) * 0.6)
    # nach tries aufgegeben
    if last_exc:
        raise last_exc
    raise RuntimeError("Unbekannter HTTP-Fehler")

def cached_toc_fetch(url: str) -> str:
    """Nur TOC-URLs cachen; 404 wird durchgereicht."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()
    cache_file = CACHE_DIR / f"{key}.html"

    if cache_file.exists() and (time.time() - cache_file.stat().st_mtime < CACHE_MAX_AGE_DAYS * 86400):
        return cache_file.read_text(encoding="utf-8")

    html = http_get(url)
    cache_file.write_text(html, encoding="utf-8")
    return html


# ---------- Parser ----------
def _norm_para(s: str) -> str:
    s = s.strip()
    return "§ " + re.sub(r"^§?\s*(\d+[a-zA-Z]?)$", r"\1", s)

def _norm_art(s: str) -> str:
    s = s.strip()
    return "Art. " + re.sub(r"^(?:Art\.?|Artikel)?\s*(\d+[a-zA-Z]?)$", r"\1", s)

def fetch_toc_html(gesetzesnummer: str, param: str) -> str:
    params = {
        "Abfrage": "Bundesnormen",
        "Gesetzesnummer": gesetzesnummer,
        param: "0",
        "Uebergangsrecht": "",
        "Anlage": "",
    }
    url = TOC_BASE + "?" + _url.urlencode(params)
    return cached_toc_fetch(url)

# --- ERSETZEN: parse_toc() komplett ---

def parse_toc(html: str) -> Tuple[List[str], str]:
    """
    TOC parsen:
    - Units NUR aus Links (verlässlich) + optional Text-Einzel (nur wenn Links leer sind)
    - unit_type ausschließlich nach Link-Counts bestimmen
    - § 0 / Art. 0 werden ignoriert
    """
    soup = BeautifulSoup(html, "html.parser")
    units_link_par: List[str] = []
    units_link_art: List[str] = []
    units_text_par: List[str] = []
    units_text_art: List[str] = []

    # 1) Links (zuverlässig) – 0 ignorieren
    for a in soup.find_all("a", href=True):
        href = a["href"]
        mp = _RE_HREF_PAR.search(href)
        if mp:
            num = mp.group(1).strip()
            if num != "0":
                units_link_par.append(_norm_para(num))
            continue
        ma = _RE_HREF_ART.search(href)
        if ma:
            num = ma.group(1).strip()
            if num != "0":
                units_link_art.append(_norm_art(num))
            continue

    # 2) Text (vorsichtig) – 0 ignorieren
    text_all = soup.get_text("\n", strip=True)
    for m in _RE_PARA_SINGLE.finditer(text_all):
        num = m.group(1).strip()
        if num != "0":
            units_text_par.append(_norm_para(num))
    for m in _RE_ART_SINGLE.finditer(text_all):
        num = m.group(1).strip()
        if num != "0":
            units_text_art.append(_norm_art(num))

    # 3) unit_type NUR nach Link-Counts
    if len(units_link_art) > len(units_link_par):
        unit_type = "artikel"
    elif len(units_link_par) > 0:
        unit_type = "paragraf"
    elif len(units_link_art) > 0:
        unit_type = "artikel"
    else:
        unit_type = "artikel" if len(units_text_art) > len(units_text_par) else "paragraf"

    # 4) Finale Units: Links bevorzugt, Text nur wenn Links leer und genug Treffer
    if unit_type == "paragraf":
        units = sorted(set(units_link_par)) or (sorted(set(units_text_par)) if len(units_text_par) > 10 else [])
    else:
        units = sorted(set(units_link_art)) or (sorted(set(units_text_art)) if len(units_text_art) > 10 else [])

    soup.decompose()
    return units, unit_type



# ---------- Numerische Probe (ohne Cache) ----------
def probe_upper_bound(gesetzesnummer: str, unit_type: str = "paragraf") -> Tuple[Optional[int], str]:
    """
    Numerisches Probing der Obergrenze. 404 (NotFound) wird als 'Miss' behandelt
    und führt NICHT mehr zum Abbruch. Auch Netzfehler werden weich behandelt.
    """
    param = "Artikel" if unit_type == "artikel" else "Paragraf"
    last_hit: Optional[int] = None
    consec_miss = 0

    log(f"🔍 Probe für {gesetzesnummer} ({param}) gestartet …")

    for n in range(1, PROBE_MAX + 1):
        params = {
            "Abfrage": "Bundesnormen",
            "Gesetzesnummer": gesetzesnummer,
            param: str(n),
        }
        url = TOC_BASE + "?" + _url.urlencode(params)

        try:
            html = http_get(url, timeout=REQUEST_TIMEOUT, tries=2, backoff=1.6)
            ok = ("RIS" in html) and ("NOR" in html or "Art" in html or "§" in html)
        except NotFound404:
            # Lücke (z. B. Artikel existiert nicht) → einfach als Miss zählen
            ok = False
        except requests.RequestException:
            # temporärer Netzfehler → als Miss zählen, nicht abbrechen
            ok = False

        if ok:
            last_hit = n
            consec_miss = 0
        else:
            consec_miss += 1
            if consec_miss >= PROBE_CONSEC_MISS:
                break

        if n % 50 == 0:
            log(f"   ... Probe-Fortschritt: {param} {n}")

        time.sleep(PROBE_DELAY)

    log(f"✅ Probe beendet: letzte Treffer-Nr. = {last_hit}")
    return last_hit, unit_type

    


# ---------- Hauptprozess ----------
def enrich_laws(input_path: Path, output_path: Path, overwrite_existing: bool = False) -> Tuple[int, int]:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    changed = 0
    unchanged = 0
    log(f"📘 {len(data)} Gesetze geladen.")

    for i, law in enumerate(data, 1):
        gnr = str(law.get("gesetzesnummer") or "").strip()
        kurz = law.get("kurz", "???")
        if not gnr:
            continue

        if (not overwrite_existing) and isinstance(law.get("fallback_end"), int):
            unchanged += 1
            continue

        log(f"[{i}/{len(data)}] 🧩 {kurz} ({gnr}) – TOC lesen …")
        units: List[str] = []
        unit_type = "paragraf"

        # 1) Erst Artikel=0 versuchen, 404 ist ok → dann Paragraf=0
        try:
            html = fetch_toc_html(gnr, "Artikel")
            units, unit_type = parse_toc(html)
        except NotFound404:
            log("   ℹ️ Artikel-TOC existiert nicht (404) – versuche Paragraf-TOC …")
        except requests.RequestException as e:
            log(f"   ⚠️ Netzfehler bei Artikel-TOC: {e} – versuche Paragraf-TOC …")

        if not units:
            try:
                html = fetch_toc_html(gnr, "Paragraf")
                units, unit_type = parse_toc(html)
            except NotFound404:
                log("   ℹ️ Paragraf-TOC existiert nicht (404).")
            except requests.RequestException as e:
                log(f"   ⚠️ Netzfehler bei Paragraf-TOC: {e} – überspringe Gesetz.")
                # zum nächsten Gesetz weiter
                unchanged += 1
                time.sleep(SLEEP_BETWEEN_LAWS)
                continue

        # 2) Max bestimmen
        mx = 0
        for u in units:
            m = re.search(r"(\d+)", u)
            if m:
                mx = max(mx, int(m.group(1)))

        log(f"   → {len(units)} {unit_type}-Einheiten gefunden, max = {mx}")
        if len(units) < 10 and mx >= 300:
            log("   ⚠️ Unplausibler TOC-max (zu wenige Einheiten, sehr hoher max) – ignoriere und probe …")
            mx = 0  # zwingt den Probe-Zweig unten

        # 3) Falls wenig/leer → Probe
        if PROBE_ON_EMPTY_TOC and (mx < 2 or len(units) < 50):
            log("   ⚠️ TOC unvollständig – starte Probe …")
            # 1) zuerst im erkannten Typ
            ub, utype = probe_upper_bound(gnr, unit_type)
            # 2) wenn nichts gefunden: automatisch den anderen Typ versuchen
            if not ub:
                other = "artikel" if unit_type == "paragraf" else "paragraf"
                log(f"   ℹ️ Erste Probe ohne Ergebnis – versuche alternativ: {other} …")
                ub2, utype2 = probe_upper_bound(gnr, other)
                if ub2:
                    ub, utype = ub2, utype2

            if ub and ub > 1:
                mx = ub
                unit_type = utype
                log(f"   ✅ Probe erfolgreich: max = {mx} ({unit_type})")

        # 4) Speichern / weiter
        if mx > 1:
            law["fallback_end"] = mx
            law["unit_type"] = unit_type
            law["fallback_source"] = "toc_lowmem" if len(units) >= 50 else f"probe:{unit_type}"
            changed += 1
        else:
            unchanged += 1
            log("   ❌ Keine Grenze ermittelbar.")

        time.sleep(SLEEP_BETWEEN_LAWS)

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"💾 geschrieben: {output_path}")
    log(f"✅ ergänzt: {changed}, unverändert: {unchanged}")
    return changed, unchanged


def main():
    ap = argparse.ArgumentParser(description="Low-memory RIS Fallback Tool (robust)")
    ap.add_argument("--in", dest="in_path",  default="ris_law/data/laws.json")
    ap.add_argument("--out", dest="out_path", default="ris_law/data/laws_enriched.json")
    ap.add_argument("--overwrite-existing", action="store_true")
    args = ap.parse_args()

    log(f"🚀 Starte Low-Mem-Enrichment: {args.in_path}")
    try:
        enrich_laws(Path(args.in_path), Path(args.out_path), args.overwrite_existing)
    except KeyboardInterrupt:
        log("⛔ Abgebrochen (Ctrl+C).")
    log("🏁 Fertig!")


if __name__ == "__main__":
    main()
