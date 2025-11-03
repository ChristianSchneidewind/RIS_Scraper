# ris_law/full_export.py
# --------------------------------------------
# Reduziertes Logging: Nur Start/Ende + Fortschritt pro 50 Einheiten
# --------------------------------------------

from __future__ import annotations
import json
import time
import datetime as dt
from typing import Optional
from urllib.parse import urlencode
import requests
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    "User-Agent": "ris-law/0.1 (+github.com/christianschneidewind/ris-law)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
REQUEST_TIMEOUT = 30


def _make_toc_url(gesetzesnummer: str, numeric_pid: int, unit_type: str = "paragraf") -> str:
    param = "Artikel" if str(unit_type).lower().startswith("art") else "Paragraf"
    query = {
        "Abfrage": "Bundesnormen",
        "Gesetzesnummer": gesetzesnummer,
        param: str(numeric_pid),
        "Uebergangsrecht": "",
        "Anlage": "",
    }
    return "https://www.ris.bka.gv.at/NormDokument.wxe?" + urlencode(query)


def _http_get(url: str, *, tries: int = 2, backoff: float = 1.6) -> requests.Response:
    attempt = 0
    last_exc: Optional[Exception] = None
    while attempt < tries:
        try:
            r = requests.get(url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                return r
            return r
        except Exception as e:
            last_exc = e
            time.sleep(backoff * (attempt + 1))
        attempt += 1
    if last_exc:
        raise last_exc
    raise RuntimeError("Unbekannter Fehler bei HTTP-GET")


def _extract_plain_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    main = soup.find(id="content") or soup.find("body") or soup
    text = main.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def _write_jsonl_line(path: str, obj: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def build_complete_numeric(
    out_path: str,
    gesetzesnummer: str,
    law_name: str,
    *,
    start_num: int = 1,
    end_num: int,
    granularity: str = "para",
    include_aufgehoben: bool = False,
    delay: float = 1.0,
    unit_type: str = "paragraf",
) -> int:
    """
    Holt Einheiten (Paragraf/Artikel) im Bereich [start_num, end_num]
    und schreibt sie als JSONL-Zeilen.
    """
    rows = 0
    now_iso = dt.datetime.utcnow().isoformat() + "Z"
    unit_label = "Artikel" if str(unit_type).lower().startswith("art") else "§"

    print(f"[RIS] → Starte Export {law_name} ({gesetzesnummer}) [{unit_label} {start_num}–{end_num}]")

    for n in range(int(start_num), int(end_num) + 1):
        url = _make_toc_url(gesetzesnummer, n, unit_type)
        try:
            r = _http_get(url, tries=2, backoff=1.6)
        except Exception as e:
            _write_jsonl_line(
                out_path,
                {
                    "law": law_name,
                    "gesetzesnummer": gesetzesnummer,
                    "unit_type": unit_type,
                    "unit": f"{unit_label} {n}",
                    "status": f"resolve_failed: {type(e).__name__} {e}",
                    "url": url,
                    "fetched_at": now_iso,
                },
            )
            continue

        if r.status_code == 404:
            _write_jsonl_line(
                out_path,
                {
                    "law": law_name,
                    "gesetzesnummer": gesetzesnummer,
                    "unit_type": unit_type,
                    "unit": f"{unit_label} {n}",
                    "status": "not_found",
                    "url": url,
                    "fetched_at": now_iso,
                },
            )
            continue

        if r.status_code != 200:
            _write_jsonl_line(
                out_path,
                {
                    "law": law_name,
                    "gesetzesnummer": gesetzesnummer,
                    "unit_type": unit_type,
                    "unit": f"{unit_label} {n}",
                    "status": f"http_{r.status_code}",
                    "url": url,
                    "fetched_at": now_iso,
                },
            )
            continue

        text = _extract_plain_text(r.text).strip()
        status = "ok" if text else "empty"

        _write_jsonl_line(
            out_path,
            {
                "law": law_name,
                "gesetzesnummer": gesetzesnummer,
                "unit_type": unit_type,
                "unit": f"{unit_label} {n}",
                "status": status,
                "text": text,
                "url": url,
                "fetched_at": now_iso,
                "granularity": granularity,
            },
        )
        rows += 1

        # Fortschrittsanzeige nur jede 50. Einheit
        if n % 50 == 0:
            print(f"   ↳ Fortschritt: {n}/{end_num}")

        if delay:
            time.sleep(delay)

    print(f"[RIS] ✅ Fertig: {rows} Einträge gespeichert ({law_name})")
    return rows
