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
REQUEST_TIMEOUT = 30


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
    """Gibt die Fallback-Obergrenze (End-§) zurück, falls konfiguriert."""
    law = find_law(gesetzesnummer_or_kurz)
    if not law:
        return None
    return law.get("fallback_end")
