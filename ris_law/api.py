from typing import Iterator, Literal, Dict, List
import re
import json
import urllib.parse as _url
from pathlib import Path

from .types import LawItem
from .toc_parser import get_current_abgb_paragraphs
from .html_parser import (
    resolve_nor_urls_from_toc_url,
    fetch_paragraph_text_via_html,
    extract_para_id,
)
from .writer import write_jsonl_from_docrefs
from .full_export import build_complete_numeric

Granularity = Literal["para", "nor"]


# ------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------

def _load_laws_json() -> list[dict]:
    """Lädt ris_law/data/laws.json"""
    laws_path = Path(__file__).parent / "data" / "laws.json"
    if not laws_path.exists():
        raise FileNotFoundError(f"laws.json nicht gefunden unter {laws_path}")
    with open(laws_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _find_law_entry(gesetzesnummer: str) -> dict | None:
    """Findet das passende Gesetz aus laws.json"""
    for law in _load_laws_json():
        if str(law.get("gesetzesnummer")) == str(gesetzesnummer):
            return law
    return None


# ------------------------------------------------------------
# RIS-Abfrage (bestehend)
# ------------------------------------------------------------

def _build_docrefs_from_toc(
    gesetzesnummer: str,
    paragraphs: List[str],
    granularity: Granularity,
) -> List[Dict[str, str]]:
    docrefs: List[Dict[str, str]] = []

    if granularity == "para":
        for pid in paragraphs:
            pid_clean = pid.replace("§", "").strip()
            url = "https://www.ris.bka.gv.at/NormDokument.wxe?" + _url.urlencode(
                {
                    "Abfrage": "Bundesnormen",
                    "Gesetzesnummer": gesetzesnummer,
                    "Paragraf": pid_clean,
                    "Uebergangsrecht": "",
                    "Anlage": "",
                    "Artikel": "",
                }
            )
            docrefs.append({"id": "", "url": url})
        return docrefs

    seen_nor = set()
    for pid in paragraphs:
        pid_clean = pid.replace("§", "").strip()
        toc_url = "https://www.ris.bka.gv.at/NormDokument.wxe?" + _url.urlencode(
            {
                "Abfrage": "Bundesnormen",
                "Gesetzesnummer": gesetzesnummer,
                "Paragraf": pid_clean,
                "Uebergangsrecht": "",
                "Anlage": "",
                "Artikel": "",
            }
        )
        try:
            nor_urls = resolve_nor_urls_from_toc_url(toc_url)
        except Exception:
            nor_urls = [toc_url]

        for nu in nor_urls:
            m = re.search(r"(NOR\d{5,})", nu, re.IGNORECASE)
            if m:
                nor = m.group(1)
                if nor in seen_nor:
                    continue
                seen_nor.add(nor)
                docrefs.append({"id": nor, "url": nu})
            else:
                docrefs.append({"id": "", "url": nu})

    return docrefs


def iter_law(
    gesetzesnummer: str,
    law_name: str,
    granularity: Granularity = "nor",
    include_aufgehoben: bool = True,
    delay: float = 1.0,
) -> Iterator[LawItem]:
    toc = get_current_abgb_paragraphs(
        gesetzesnummer=gesetzesnummer,
        include_aufgehoben=include_aufgehoben,
    )
    paragraphs = toc["paragraphs"]

    docrefs = _build_docrefs_from_toc(gesetzesnummer, paragraphs, granularity)

    for ref in docrefs:
        parsed = fetch_paragraph_text_via_html(ref["url"])
        heading = (parsed.get("heading") or "").strip()
        text = (parsed.get("text") or "").strip()
        nor = (parsed.get("nor") or ref.get("id") or "").strip()
        para_id = extract_para_id(heading or text)
        yield LawItem(
            law=law_name,
            gesetzesnummer=gesetzesnummer,
            paragraph_id=para_id or None,
            heading=heading or None,
            text=text,
            url=ref["url"],
            source="RIS HTML",
            document_number=nor or None,
            retrieved_at="",
        )


def write_jsonl(
    gesetzesnummer: str,
    law_name: str,
    out_path: str,
    granularity: Granularity = "nor",
    include_aufgehoben: bool = True,
    delay: float = 1.0,
) -> int:
    toc = get_current_abgb_paragraphs(
        gesetzesnummer=gesetzesnummer,
        include_aufgehoben=include_aufgehoben,
    )
    paragraphs = toc["paragraphs"]
    docrefs = _build_docrefs_from_toc(gesetzesnummer, paragraphs, granularity)

    return write_jsonl_from_docrefs(
        docrefs,
        out_path=out_path,
        delay=delay,
        gesetzesnummer=gesetzesnummer,
        law_name=law_name,
    )


# ------------------------------------------------------------
# Vollständiger Export (mit unit_type aus laws.json)
# ------------------------------------------------------------

def write_jsonl_full(
    gesetzesnummer: str,
    law_name: str,
    out_path: str,
    delay: float = 1.2,
    include_aufgehoben: bool = True,
    toc_date: str | None = None,
    start_num: int = 1,
    end_num: int | None = None,
) -> int:
    """
    Vollständiger Export – nutzt full_export.build_complete_numeric()
    und zieht unit_type und fallback_end automatisch aus laws.json.
    """
    law_entry = _find_law_entry(gesetzesnummer)
    unit_type = "paragraf"
    if law_entry:
        unit_type = (law_entry.get("unit_type") or "paragraf").lower()
        if end_num is None:
            end_num = int(law_entry.get("fallback_end") or 0) or None

    if end_num is None:
        raise ValueError(f"Keine fallback_end für {gesetzesnummer} gefunden.")

    print(f"[RIS] Starte Voll-Export {law_name} ({gesetzesnummer}) – {unit_type}, bis {end_num}")

    return build_complete_numeric(
        out_path=out_path,
        gesetzesnummer=gesetzesnummer,
        law_name=law_name,
        delay=delay,
        include_aufgehoben=include_aufgehoben,
        start_num=start_num,
        end_num=end_num,
        unit_type=unit_type,  # 👈 neu
    )
