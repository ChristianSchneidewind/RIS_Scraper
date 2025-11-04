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
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urljoin

import requests
from bs4 import BeautifulSoup

# ---------- Einstellungen ----------
DEFAULT_HEADERS = {
    "User-Agent": "RIS-Law-FallbackEnricher/SmartProbe+Context v3 (+https://github.com/yourrepo)"
}
REQUEST_TIMEOUT = 30
TOC_BASE = "https://www.ris.bka.gv.at/NormDokument.wxe"

PROBE_ON_EMPTY_TOC = True
PROBE_MIN_TOC_SIZE = 100
CACHE_DIR = Path("cache_toc")
CACHE_MAX_AGE_DAYS = 7
SLEEP_BETWEEN_LAWS = 0.8

PROBE_MAX = 4000
PROBE_RETRIES = 2
PROBE_BACKOFF = 1.6
MISSING_STREAK_ABORT = 100

# Optionaler Notanker (sollte mit v3 selten nötig sein)
KNOWN_MAX: Dict[str, int] = {
    "10001702": 909,  # UGB – nur falls SmartProbe trotz v3 nicht greift
}

# Regexe
_RE_HREF_ART = re.compile(r"(?:[?&])Artikel\s*=\s*(\d+)", re.IGNORECASE)
_RE_HREF_PAR = re.compile(r"(?:[?&])Paragraf\s*=\s*(\d+)", re.IGNORECASE)
_RE_UNIT_LOOSE = re.compile(r"\b(§|Art\.?)\s*(\d+[a-zA-Z]?)\b", re.IGNORECASE)
_RE_RANGE = re.compile(r"§{1,2}\s*(\d+)\s*(?:bis|-|–)\s*(\d+)", re.IGNORECASE)

# ---------- Logging ----------
def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# ---------- HTTP + Cache ----------
class NotFound404(Exception):
    pass

def http_get(url: str, timeout: int = REQUEST_TIMEOUT, tries: int = 3, backoff: float = 1.7) -> str:
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
            time.sleep((backoff ** i) * 0.6)
    if last_exc:
        raise last_exc
    raise RuntimeError("Unbekannter HTTP-Fehler")

def cached_toc_fetch(url: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()
    p = CACHE_DIR / f"{key}.html"
    if p.exists() and (time.time() - p.stat().st_mtime < CACHE_MAX_AGE_DAYS * 86400):
        return p.read_text(encoding="utf-8")
    html = http_get(url)
    p.write_text(html, encoding="utf-8")
    return html

# ---------- Helpers ----------
def _param_for_type(unit_type: str) -> str:
    return "Artikel" if str(unit_type).lower().startswith("art") else "Paragraf"

def _norm_para(s: str) -> str:
    s = s.strip()
    return "§ " + re.sub(r"^§?\s*(\d+[a-zA-Z]?)$", r"\1", s)

def _norm_art(s: str) -> str:
    s = s.strip()
    return "Art. " + re.sub(r"^(?:Art\.?|Artikel)?\s*(\d+[a-zA-Z]?)$", r"\1", s)

def _toc_url0(gnr: str, unit_type: str) -> str:
    param = _param_for_type(unit_type)
    params = {"Abfrage": "Bundesnormen", "Gesetzesnummer": gnr, param: "0", "Uebergangsrecht": "", "Anlage": ""}
    return TOC_BASE + "?" + _url.urlencode(params)

def _root_toc_urls(gnr: str) -> list[str]:
    base = TOC_BASE + "?" + _url.urlencode({"Abfrage": "Bundesnormen", "Gesetzesnummer": gnr})
    return [
        base + "&Paragraf=0&Uebergangsrecht=&Anlage=",
        base + "&Artikel=0&Uebergangsrecht=&Anlage=",
        base + "&Index=",
        base + "&Gliederung=",
    ]

# ---------- TOC-Parsing (Heuristik) ----------
def _parse_units_from_toc_html(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    units = []
    for a in soup.find_all("a", href=True):
        href = a["href"] or ""
        m = _RE_HREF_PAR.search(href)
        if m and m.group(1) != "0":
            units.append(_norm_para(m.group(1))); continue
        m = _RE_HREF_ART.search(href)
        if m and m.group(1) != "0":
            units.append(_norm_art(m.group(1))); continue
        txt = (a.get_text() or "").strip()
        for mm in _RE_UNIT_LOOSE.finditer(txt):
            kind, num = mm.group(1), mm.group(2)
            if num != "0":
                units.append(_norm_art(num) if kind.lower().startswith("art") else _norm_para(num))
    text_all = soup.get_text(" ", strip=True).replace("\xa0", " ")
    for m in _RE_RANGE.finditer(text_all):
        lo, hi = int(m.group(1)), int(m.group(2))
        if 0 < lo <= hi and (hi - lo) < 5000:
            for n in range(lo, hi + 1):
                units.append(_norm_para(str(n)))
    soup.decompose()
    seen, out = set(), []
    for u in units:
        if u not in seen:
            seen.add(u); out.append(u)
    def _key(u: str):
        s = u.replace("Art.", "").replace("§", "").strip()
        m = re.search(r"(\d+)([a-zA-Z]*)$", s)
        return (int(m.group(1)) if m else 10**9, m.group(2) if m else "")
    out.sort(key=_key)
    return out

# ---------- Kontext-Ermittlung (NEU: breiter + Single-Key) ----------
_CONTEXT_KEYS = {
    "dokumentteil", "gliederung", "untergliederung", "gliederungsnummer",
    "buch", "teil", "abschnitt", "unterabschnitt", "kapitel", "glied",
    "seite", "pos", "anlage"
}

_ROMANS = ["I","II","III","IV","V","VI","VII","VIII","IX","X","XI","XII","XIII","XIV","XV","XVI","XVII","XVIII","XIX","XX"]

# erweiterte Guess-Liste
_GUESS_CONTEXTS_ORDERED: List[Tuple[str, List[str]]] = [
    ("Dokumentteil", _ROMANS),
    ("Buch", _ROMANS + [str(i) for i in range(1, 11)]),
    ("Teil", [str(i) for i in range(1, 31)]),
    ("Abschnitt", [str(i) for i in range(1, 81)]),
    ("Kapitel", [str(i) for i in range(1, 201)]),
    ("Untergliederung", [str(i) for i in range(1, 51)]),
]

def _discover_probe_contexts(gnr: str, unit_type: str, max_pages: int = 60) -> List[Dict[str, str]]:
    """
    Sammelt Single-Key-Kontexte aus ALLEN Links gleicher GNR (auch ohne Paragraf/Artikel).
    """
    start_urls = _root_toc_urls(gnr)
    start_urls.insert(0, _toc_url0(gnr, unit_type))
    queue = list(dict.fromkeys(start_urls))
    visited = set()
    contexts: List[Dict[str, str]] = []
    seen_pairs = set()

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            html = cached_toc_fetch(url)
        except Exception:
            continue

        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            full = urljoin("https://www.ris.bka.gv.at/", a["href"])
            p = urlparse(full)
            if not p.path.endswith("NormDokument.wxe"):
                continue
            qs = parse_qs(p.query)
            if (qs.get("Gesetzesnummer") or [""])[0] != gnr:
                continue

            # 1) Single-Key-Kontexte sammeln
            for k, v in qs.items():
                kl = k.lower()
                if kl in _CONTEXT_KEYS and v and v[0] != "":
                    pair = (k, v[0])
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        contexts.append({k: v[0]})

            # 2) weitere TOC-/Gliederungspfade
            keys = {k.lower() for k in qs.keys()}
            param = _param_for_type(unit_type)
            if (param in qs and qs[param][0] == "0") or "gliederung" in keys or "index" in keys:
                if full not in visited and full not in queue:
                    queue.append(full)

        soup.decompose()
        if len(contexts) >= 60:
            break

    return contexts

# ---------- Smart-Probe (Kontexte + Guesses) ----------
def _unit_exists_with_context(gnr: str, unit_type: str, n: int, ctx: Dict[str, str]) -> bool:
    param = _param_for_type(unit_type)
    base = {"Abfrage": "Bundesnormen", "Gesetzesnummer": gnr, param: str(n)}
    base.update(ctx)
    url = TOC_BASE + "?" + _url.urlencode(base)
    try:
        html = http_get(url, timeout=REQUEST_TIMEOUT, tries=PROBE_RETRIES, backoff=PROBE_BACKOFF)
        return ("NOR" in html) or ("§" in html) or ("Art" in html)
    except NotFound404:
        return False
    except requests.RequestException:
        return False

def _quick_context_ok(gnr: str, unit_type: str, ctx: Dict[str, str]) -> bool:
    for probe_n in (1, 50, 200, 500, 900):
        if _unit_exists_with_context(gnr, unit_type, probe_n, ctx):
            return True
    return False

def _smart_probe_single_context(gnr: str, unit_type: str, ctx: Dict[str, str]) -> Optional[int]:
    low, high = 0, 1
    miss = 0
    while high <= PROBE_MAX:
        ok = _unit_exists_with_context(gnr, unit_type, high, ctx)
        if ok:
            low = high
            high *= 2
            miss = 0
        else:
            miss += 1
            if miss >= MISSING_STREAK_ABORT and low == 0:
                return None
            break
    if low == 0:
        return None
    if high > PROBE_MAX:
        high = PROBE_MAX
    lo, hi = low, high
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if _unit_exists_with_context(gnr, unit_type, mid, ctx):
            lo = mid
        else:
            hi = mid
    return lo

def smart_probe_upper_bound(gnr: str, unit_type: str, contexts: List[Dict[str, str]]) -> Optional[int]:
    param = _param_for_type(unit_type)
    all_contexts: List[Tuple[str, Dict[str, str]]] = [("none", {})]

    for ctx in contexts:
        all_contexts.append(("discovered", ctx))

    # Wenn keine Kontexte gefunden wurden: aggressive, aber begrenzte Guess-Liste
    if len(contexts) == 0:
        for key, vals in _GUESS_CONTEXTS_ORDERED:
            for val in vals:
                all_contexts.append(("guess", {key: val}))

    # Begrenzungen, damit wir nicht „ewig“ probieren
    MAX_GUESSES = 120           # höchstens so viele Kontext-Versuche insgesamt
    EARLY_STOP_THRESHOLD = 300  # wenn wir >=300 finden, reicht uns das i.d.R.
    best = None

    disc = sum(1 for k, _ in all_contexts if k == "discovered")
    guess = sum(1 for k, _ in all_contexts if k == "guess")
    log(f"🔍 SmartProbe für {gnr} ({param}) mit {disc} Kontexte(n) + {guess} Guess …")

    tried = 0
    for kind, ctx in all_contexts:
        if ctx:
            # schneller Vorcheck – wenn nichts trifft, Kontext überspringen
            if not _quick_context_ok(gnr, unit_type, ctx):
                tried += 1
                if tried % 25 == 0:
                    log(f"   … SmartProbe Fortschritt: {tried} Kontexte geprüft")
                if tried >= MAX_GUESSES:
                    log("   ⛔ Guess-Limit erreicht.")
                    break
                continue

        res = _smart_probe_single_context(gnr, unit_type, ctx)
        tried += 1
        if res is not None:
            best = res if best is None else max(best, res)
            if best >= EARLY_STOP_THRESHOLD:
                log(f"   ✅ Frühabbruch: ausreichende Obergrenze erkannt ({best} ≥ {EARLY_STOP_THRESHOLD})")
                break

        if tried % 25 == 0:
            log(f"   … SmartProbe Fortschritt: {tried} Kontexte geprüft")
        if tried >= MAX_GUESSES:
            log("   ⛔ Guess-Limit erreicht.")
            break

    if best is not None:
        log(f"   ✅ SmartProbe-Ergebnis (max): {best}")
    else:
        log("   ❌ SmartProbe: kein Kontext lieferte Treffer.")
    return best


# ---------- Sammeln aller Einheiten (nur Info) ----------
def collect_all_units(gnr: str, unit_type: str, include_annexes: bool, max_pages: int = 60, deep: bool = False) -> list[str]:
    start_urls = _root_toc_urls(gnr)
    start_urls.insert(0, _toc_url0(gnr, unit_type))
    queue, seen_roots = [], set()
    for u in start_urls:
        if u not in seen_roots:
            seen_roots.add(u); queue.append(u)

    visited, all_units = set(), []
    visited_count = 0
    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited: continue
        visited.add(url); visited_count += 1
        try:
            html = cached_toc_fetch(url)
        except NotFound404:
            continue
        except requests.RequestException:
            continue
        all_units.extend(_parse_units_from_toc_html(html))

        soup = BeautifulSoup(html, "lxml")
        base = "https://www.ris.bka.gv.at/"
        for a in soup.find_all("a", href=True):
            full = urljoin(base, a["href"])
            p = urlparse(full)
            if not p.path.endswith("NormDokument.wxe"):
                continue
            qs = parse_qs(p.query)
            g = (qs.get("Gesetzesnummer") or [""])[0]
            if g != gnr: continue
            keys = {k.lower() for k in qs.keys()}
            param = _param_for_type(unit_type)
            if (param in qs and qs[param][0] == "0") or "gliederung" in keys or "index" in keys:
                if full not in visited and full not in queue:
                    queue.append(full)
        soup.decompose()

    out, seen = [], set()
    for u in all_units:
        key = u.strip().lower()
        if key in {"§ 0","§0","art. 0","art.0"}: continue
        if u not in seen:
            seen.add(u); out.append(u)
    log(f"   ↪ TOC/Unter-TOC Seiten besucht: {visited_count}")
    return out

# ---------- Hauptprozess ----------
def enrich_laws(input_path: Path, output_path: Path, overwrite_existing: bool = False,
                include_annexes: bool = False, max_pages: int = 60, deep: bool = False) -> Tuple[int, int]:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    changed = 0
    unchanged = 0
    log(f"📘 {len(data)} Gesetze geladen.")

    for i, law in enumerate(data, 1):
        gnr = str(law.get("gesetzesnummer") or "").strip()
        kurz = law.get("kurz", law.get("titel", "???"))
        if not gnr:
            continue

        if (not overwrite_existing) and isinstance(law.get("fallback_end"), int) and law.get("unit_type"):
            unchanged += 1
            continue

        log(f"[{i}/{len(data)}] 🧩 {kurz} ({gnr}) – TOC sammeln …")

        units_art = collect_all_units(gnr, "artikel", include_annexes, max_pages=max_pages, deep=deep)
        units_par = collect_all_units(gnr, "paragraf", include_annexes, max_pages=max_pages, deep=deep)

        if len(units_art) > len(units_par):
            unit_type = "artikel"; units = units_art
        else:
            unit_type = "paragraf"; units = units_par

        mx_from_toc = 0
        for u in units:
            m = re.search(r"(\d+)", u)
            if m:
                mx_from_toc = max(mx_from_toc, int(m.group(1)))
        log(f"   → {len(units)} {unit_type}-Einheiten gefunden, max = {mx_from_toc}")

        contexts = _discover_probe_contexts(gnr, unit_type, max_pages=max_pages)
        if contexts:
            log(f"   ↪ gefundene Kontexte: {len(contexts)} (z. B. {contexts[0]})")

        if len(units) >= PROBE_MIN_TOC_SIZE and mx_from_toc > 0:
            mx = mx_from_toc
            source = "toc_crawl"
        else:
            log("   ⚠️ TOC klein/leer – starte SmartProbe (Kontexte/Guesses) …")
            mx = smart_probe_upper_bound(gnr, unit_type, contexts) or 0
            source = f"smartprobe:{unit_type}"

            # Wenn wir nach der Probe immer noch zu niedrig sind und ein Notanker existiert:
            if mx < 200 and gnr in KNOWN_MAX:
                log(f"   ℹ️ Verwende bekannten Max-Wert für {kurz}: {KNOWN_MAX[gnr]}")
                mx = KNOWN_MAX[gnr]
                source = "known_max"


        if (mx < 2) and (gnr in KNOWN_MAX):
            mx = KNOWN_MAX[gnr]; source = "known_max"

        if mx > 1:
            if overwrite_existing or not isinstance(law.get("fallback_end"), int):
                law["fallback_end"] = mx
            if overwrite_existing or not law.get("unit_type"):
                law["unit_type"] = unit_type
            law["fallback_source"] = source
            changed += 1
            log(f"   ✅ Ergebnis: {unit_type} bis {mx} ({source})")
        else:
            unchanged += 1
            log("   ❌ Keine Grenze ermittelbar.")

        time.sleep(SLEEP_BETWEEN_LAWS)

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"💾 geschrieben: {output_path}")
    log(f"✅ ergänzt: {changed}, unverändert: {unchanged}")
    return changed, unchanged

def main():
    ap = argparse.ArgumentParser(description="RIS Fallback-End Enrichment (SmartProbe + Context v3)")
    ap.add_argument("--in", dest="in_path",  default="ris_law/data/laws.json")
    ap.add_argument("--out", dest="out_path", default="ris_law/data/laws_enriched.json")
    ap.add_argument("--overwrite-existing", action="store_true")
    ap.add_argument("--include-annexes", action="store_true")
    ap.add_argument("--max-pages", type=int, default=60)
    ap.add_argument("--deep", action="store_true")
    args = ap.parse_args()

    log(f"🚀 Starte Enrichment: {args.in_path}")
    try:
        enrich_laws(Path(args.in_path), Path(args.out_path),
                    overwrite_existing=args.overwrite_existing,
                    include_annexes=args.include_annexes,
                    max_pages=args.max_pages, deep=args.deep)
    except KeyboardInterrupt:
        log("⛔ Abgebrochen (Ctrl+C).")
    log("🏁 Fertig!")

if __name__ == "__main__":
    main()
