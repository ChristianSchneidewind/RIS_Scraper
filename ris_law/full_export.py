from __future__ import annotations

import time
import json
from typing import Optional, Dict, Any
from urllib.parse import urlencode

import requests

from .html_parser import fetch_paragraph_text_via_html
from .soap_client import get_law_metadata, parse_dates_from_html  # zentrale Datumslogik hier!

RIS_NORMDOK_BASE = "https://www.ris.bka.gv.at/NormDokument.wxe"

_HTML_HEADERS = {
    "User-Agent": "ris-law/0.1 (+local full_export)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _unit_url(gesetzesnummer: str, unit_type: str, nr_or_label: int | str) -> str:
    key = "Artikel" if str(unit_type).lower().startswith("art") else "Paragraf"
    q = {
        "Abfrage": "Bundesnormen",
        "Gesetzesnummer": gesetzesnummer,
        key: str(nr_or_label),
        "Uebergangsrecht": "",
        "Anlage": "",
    }
    return f"{RIS_NORMDOK_BASE}?{urlencode(q)}"


def _fetch_unit_html(gesetzesnummer: str, unit_type: str, nr_or_label: int | str) -> Optional[str]:
    url = _unit_url(gesetzesnummer, unit_type, nr_or_label)
    try:
        r = requests.get(url, headers=_HTML_HEADERS, timeout=30)
        if r.status_code == 200 and "<html" in r.text.lower():
            return r.text
    except requests.RequestException:
        pass
    return None


def export_full_jsonl(
    *,
    gesetzesnummer: str,
    law_name: str,
    unit_type: str,           # "artikel" | "paragraf"
    start_num: int = 1,
    end_num: int = 1,
    out_path: str = "out.jsonl",
    delay: float = 1.0,
    include_aufgehoben: bool = False,
    laws_json_path: Optional[str] = None,   # nur Signatur-Kompatibilität
) -> int:
    """
    Voll-Export (start_num..end_num).
    Pro Basisnummer wird zusätzlich eine Suffix-Schleife (a..z) probiert und
    beim ersten Loch beendet (typische RIS-Struktur: zusammenhängende Kette).
    """
    print(f"[RIS] Starte Voll-Export {law_name} ({gesetzesnummer}) – {unit_type}, bis {end_num}")

    # Fallback-Metadaten vom Gesetz (Art.0/§0)
    law_meta = get_law_metadata(gesetzesnummer) or {}
    law_date_in  = law_meta.get("date_in_force")
    law_date_out = law_meta.get("date_out_of_force")
    law_pub      = law_meta.get("kundmachungsdatum")

    def _write_unit(nr_or_label: str | int) -> bool:
        """
        Schreibt EINE Einheit. Gibt True zurück, wenn die Einheit existierte und
        eine Zeile geschrieben wurde; sonst False (z. B. 404/kein HTML).
        """
        unit_url = _unit_url(gesetzesnummer, unit_type, nr_or_label)

        # 1) HTML (Existenz + Metadaten)
        html = _fetch_unit_html(gesetzesnummer, unit_type, nr_or_label)
        if not html:
            return False

        # 2) Text der Einheit (dein bestehender Parser)
        parsed: Dict[str, Any] = {}
        try:
            parsed = fetch_paragraph_text_via_html(unit_url) or {}
        except Exception:
            parsed = {}

        text = (parsed.get("text") or "").strip()
        heading = (parsed.get("heading") or "").strip()
        nor = (parsed.get("nor") or "").strip()

        # 3) Einheits-Metadaten: zentral aus soap_client.parse_dates_from_html
        u_meta = parse_dates_from_html(html) or {}
        date_in  = u_meta.get("date_in_force")     or law_date_in
        date_out = u_meta.get("date_out_of_force") or law_date_out
        date_pub = u_meta.get("kundmachungsdatum") or law_pub

        row: Dict[str, Any] = {
            "gesetzesnummer": gesetzesnummer,
            "law": law_name,
            "unit_type": unit_type,
            "unit": f"{'Art.' if unit_type.lower().startswith('art') else '§'} {nr_or_label}",
            "unit_number": str(nr_or_label),
            "date_in_force": date_in,
            "date_out_of_force": date_out,
            "kundmachungsdatum": date_pub,
            "status": "ok" if text else "resolve_failed",
            "text": text,
            "heading": heading,
            "nor": nor,
            "url": unit_url,
        }

        f.write(json.dumps(row, ensure_ascii=False))
        f.write("\n")
        return True

    written = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for nr in range(int(start_num), int(end_num) + 1):
            # Basisnummer
            if _write_unit(nr):
                written += 1

            # Suffixe a..z
            for code in range(ord('a'), ord('z') + 1):
                label = f"{nr}{chr(code)}"
                if _write_unit(label):
                    written += 1
                else:
                    # Suffix-Kette für diese Basisnummer endet hier
                    break

            if delay:
                time.sleep(delay)
            if nr % 50 == 0 or nr == end_num:
                print(f"  ║ Fortschritt: {nr}/{end_num}")

    print(f"[RIS] ✅ Fertig: {written} Einträge gespeichert ({law_name})")
    return written


# --- Kompatibilitäts-Wrapper für api.py (nicht anfassen) -------------------------

def build_complete_numeric(
    *,
    gesetzesnummer: str,
    law_name: str,
    unit_type: str,
    start_num: int = 1,
    end_num: int = 1,
    out_path: str = "out.jsonl",
    delay: float = 1.0,
    include_aufgehoben: bool = False,
    laws_json_path: Optional[str] = None,
) -> int:
    return export_full_jsonl(
        gesetzesnummer=gesetzesnummer,
        law_name=law_name,
        unit_type=unit_type,
        start_num=start_num,
        end_num=end_num,
        out_path=out_path,
        delay=delay,
        include_aufgehoben=include_aufgehoben,
        laws_json_path=laws_json_path,
    )
