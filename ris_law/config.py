# ris_law/config.py
from __future__ import annotations
import json
from importlib.resources import files
from typing import Any, Dict, List, Optional

BASE_URL = "https://www.ris.bka.gv.at"
NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_SVC = "http://webservice.bka.gv.at/ris/services/RISWebService"
HEADERS_SOAP = {"Content-Type": "text/xml; charset=utf-8"}
USER_AGENT = "RISLawClient/1.0"
REQUEST_TIMEOUT = 20


def load_laws() -> List[Dict[str, Any]]:
    """Lädt die Gesetze-Liste aus ris_law/data/laws.json."""
    path = files("ris_law.data") / "laws.json"
    return json.loads(path.read_text(encoding="utf-8"))


def find_law(identifier: str) -> Optional[Dict[str, Any]]:
    """
    Sucht ein Gesetz per Kurzbezeichnung (z.B. 'StGB', case-insensitive)
    ODER per Gesetzesnummer (z.B. '10002296').
    """
    ident = identifier.strip().lower()
    for law in load_laws():
        if law.get("gesetzesnummer") == identifier:
            return law
        if law.get("kurz", "").lower() == ident:
            return law
    return None


def fallback_end_for(gesetzesnummer_or_kurz: str) -> Optional[int]:
    """
    Gibt die Fallback-Obergrenze zurück.

    Unterstützt:
      - fallback_end (alt)
      - fallback_end_paragraf / fallback_end_artikel (neu)
      - unit_type kann String oder Liste sein (bei Liste: erste Position = Priorität)
    """
    law = find_law(gesetzesnummer_or_kurz)
    if not law:
        return None

    # 1) Wenn das alte Feld existiert, bleibt das Verhalten identisch
    if "fallback_end" in law and law.get("fallback_end") is not None:
        return law.get("fallback_end")

    unit_type = law.get("unit_type")

    # unit_type kann Liste sein
    if isinstance(unit_type, list):
        unit_type = unit_type[0] if unit_type else None

    if isinstance(unit_type, str):
        ut = unit_type.lower()
        if ut.startswith("art"):
            return (
                law.get("fallback_end_artikel")
                or law.get("fallback_end_paragraf")
            )
        else:
            return (
                law.get("fallback_end_paragraf")
                or law.get("fallback_end_artikel")
            )

    # Fallback, falls unit_type gar nicht gesetzt ist
    return law.get("fallback_end_paragraf") or law.get("fallback_end_artikel")

