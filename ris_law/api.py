from typing import Iterator, Literal, Dict, List, Optional
import json
import logging
import re
import time
import urllib.parse as _url
from pathlib import Path

from .types import LawItem
from .toc_parser import get_current_abgb_paragraphs
from .html_parser import (
    resolve_nor_urls_from_toc_url,
    fetch_paragraph_text_via_html,
    extract_para_id,
)
from .http_client import HttpClient, get_default_http_client
from .records import FullRecord
from .writer import write_jsonl_from_docrefs
from .full_export import build_complete_numeric

Granularity = Literal["para", "nor"]

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Gesetzesindex laden
# ------------------------------------------------------------

def _load_laws_json() -> list[dict]:
    """
    Lädt ris_law/data/ris_gesetze.json.
    """
    laws_path = Path(__file__).parent / "data" / "ris_gesetze.json"
    if not laws_path.exists():
        raise FileNotFoundError(f"ris_gesetze.json nicht gefunden unter {laws_path}")
    with open(laws_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _find_law_entry(gesetzesnummer: str) -> Optional[dict]:
    """
    Sucht den Eintrag zu einer Gesetzesnummer in ris_gesetze.json.
    """
    for law in _load_laws_json():
        if str(law.get("gesetzesnummer")) == str(gesetzesnummer):
            return law
    return None


# ------------------------------------------------------------
# TOC → Docrefs (NOR- oder §-Links)
# ------------------------------------------------------------

def _build_docrefs_from_toc(
    gesetzesnummer: str,
    paragraphs: List[str],
    granularity: Granularity,
    *,
    client: HttpClient | None = None,
) -> List[Dict[str, str]]:
    """
    Baut eine Liste von Dokument-Referenzen (URL + evtl. NOR-ID) aus dem Inhaltsverzeichnis.
    """
    docrefs: List[Dict[str, str]] = []

    # Einfacher Paragraph-Modus
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

    # NOR-Modus: aus TOC alle NOR-Dokumente herauslösen
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
            nor_urls = resolve_nor_urls_from_toc_url(toc_url, client=client)
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


# ------------------------------------------------------------
# Iteration über ein Gesetz (Generator)
# ------------------------------------------------------------

def iter_law(
    gesetzesnummer: str,
    law_name: str,
    granularity: Granularity = "nor",
    include_aufgehoben: bool = True,
    delay: float = 1.0,
    client: HttpClient | None = None,
) -> Iterator[LawItem]:
    """
    Iteriert über ein Gesetz und liefert LawItem-Objekte.
    """
    toc = get_current_abgb_paragraphs(
        gesetzesnummer=gesetzesnummer,
        include_aufgehoben=include_aufgehoben,
    )
    paragraphs = toc["paragraphs"]

    client = client or get_default_http_client()
    docrefs = _build_docrefs_from_toc(gesetzesnummer, paragraphs, granularity, client=client)
    total = len(docrefs)
    logger.info(
        "[RIS] iter_law: %s Dokument-Referenzen für %s (%s) gefunden (granularity=%s).",
        total,
        law_name,
        gesetzesnummer,
        granularity,
    )

    for idx, ref in enumerate(docrefs, start=1):
        parsed = fetch_paragraph_text_via_html(ref["url"], client=client)
        heading = (parsed.get("heading") or "").strip()
        text = (parsed.get("text") or "").strip()
        nor = (parsed.get("nor") or ref.get("id") or "").strip()
        para_id = extract_para_id(heading or text)

        if total and (idx == total or idx % 10 == 0):
            logger.info("  ║ Fortschritt (iter_law/NOR): %s/%s", idx, total)

        yield LawItem(
            law=law_name,
            gesetzesnummer=gesetzesnummer,
            paragraph_id=para_id or None,
            heading=heading or None,
            text=text or None,
            url=ref["url"],
            source="RIS HTML",
            document_number=nor or None,
            retrieved_at="",
        )

        if delay:
            time.sleep(delay)


# ------------------------------------------------------------
# TOC-/NOR-Export in JSONL (CLI mode=toc)
# ------------------------------------------------------------

def write_jsonl(
    gesetzesnummer: str,
    law_name: str,
    out_path: str,
    granularity: Granularity = "nor",
    include_aufgehoben: bool = True,
    delay: float = 1.0,
    client: HttpClient | None = None,
) -> int:
    """
    TOC/NOR-basierter Export in eine JSONL-Datei.
    Dieses Format ist das „einfache“ Ausgabeformat für mode=toc.
    """
    toc = get_current_abgb_paragraphs(
        gesetzesnummer=gesetzesnummer,
        include_aufgehoben=include_aufgehoben,
    )
    paragraphs = toc["paragraphs"]

    client = client or get_default_http_client()
    docrefs = _build_docrefs_from_toc(gesetzesnummer, paragraphs, granularity, client=client)
    total = len(docrefs)
    logger.info(
        "[RIS] TOC/NOR-Export %s (%s) – %s Dokument-Referenzen gefunden (granularity=%s).",
        law_name,
        gesetzesnummer,
        total,
        granularity,
    )

    if total == 0:
        logger.warning(
            "[RIS] WARNUNG: Keine Dokumente für %s (%s) gefunden.",
            law_name,
            gesetzesnummer,
        )
        return 0

    return write_jsonl_from_docrefs(
        docrefs,
        out_path=out_path,
        delay=delay,
        gesetzesnummer=gesetzesnummer,
        law_name=law_name,
        client=client,
    )


# ------------------------------------------------------------
# Vollständiger Export (CLI mode=full)
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
    client: HttpClient | None = None,
) -> int:
    """
    Vollständiger Export eines Gesetzes im „full“-Schema (wie build_complete_numeric).

    - Für „normale“ Gesetze (nur Paragraphen ODER nur Artikel):
        → numerischer Voll-Export via build_complete_numeric(...)

    - Für Mischgesetze (Artikel UND Paragraphen laut ris_gesetze.json):
        → Export über NOR-Dokumente, aber mit dem gleichen JSON-Schema
          wie der numerische Voll-Export (gesetzesnummer, law, unit_type,
          unit, unit_number, date_in_force, date_out_of_force, license,
          status, text, heading, nor, url).
    """
    law_entry = _find_law_entry(gesetzesnummer)
    unit_type = "paragraf"
    client = client or get_default_http_client()

    # --- 1) Mischgesetze: Artikel + Paragraphen ---
    if law_entry:
        has_par = bool(law_entry.get("has_paragraphs"))
        has_art = bool(law_entry.get("has_articles"))

        if has_par and has_art:
            logger.info(
                "[RIS] Mischgesetz erkannt (%s) – verwende NOR-Export mit full-Schema.",
                gesetzesnummer,
            )

            # unit_type für das Schema (z.B. "artikel" beim DSG)
            unit_type_mixed = (law_entry.get("unit_type") or "paragraf").lower()

            # TOC laden und NOR-Docrefs bauen
            toc = get_current_abgb_paragraphs(
                gesetzesnummer=gesetzesnummer,
                include_aufgehoben=include_aufgehoben,
            )
            paragraphs = toc["paragraphs"]
            docrefs = _build_docrefs_from_toc(
                gesetzesnummer,
                paragraphs,
                "nor",
                client=client,
            )
            total = len(docrefs)
            logger.info(
                "[RIS] NOR-Dokumente für Mischgesetz %s (%s) – %s gefunden.",
                law_name,
                gesetzesnummer,
                total,
            )

            written = 0
            with open(out_path, "w", encoding="utf-8") as f:
                for idx, ref in enumerate(docrefs, start=1):
                    parsed = fetch_paragraph_text_via_html(ref["url"], client=client)
                    heading = (parsed.get("heading") or "").strip()
                    text = (parsed.get("text") or "").strip()
                    nor = (parsed.get("nor") or ref.get("id") or "").strip()
                    para_id = extract_para_id(heading or text)

                    record = FullRecord(
                        gesetzesnummer=gesetzesnummer,
                        law=law_name,
                        unit_type=unit_type_mixed,
                        # keine reine Nummer wie "1" → para_id/heading als Einheit
                        unit=para_id or heading or "",
                        unit_number=para_id or heading or "",
                        date_in_force=None,
                        date_out_of_force=None,
                        license=None,
                        status="ok" if text else "resolve_failed",
                        text=text,
                        heading=heading,
                        nor=nor or None,
                        url=ref["url"],
                    )
                    f.write(json.dumps(record.to_dict(), ensure_ascii=False))
                    f.write("\n")
                    written += 1

                    if total and (idx == total or idx % 10 == 0):
                        logger.info(
                            "  ║ Fortschritt (full/Mischgesetz): %s/%s",
                            idx,
                            total,
                        )

                    if delay:
                        time.sleep(delay)

            logger.info(
                "[RIS] ✅ Mischgesetz-Export abgeschlossen: %s Einträge für %s in %s gespeichert.",
                written,
                law_name,
                out_path,
            )
            return written

    # --- 2) „Normale“ Gesetze: numerischer Voll-Export wie bisher ---
    if law_entry:
        unit_type = (law_entry.get("unit_type") or "paragraf").lower()
        if end_num is None:
            try:
                end_num = int(law_entry.get("fallback_end") or 0) or None
            except (TypeError, ValueError):
                end_num = None

    if end_num is None:
        raise ValueError(f"Keine fallback_end für {gesetzesnummer} gefunden.")

    logger.info(
        "[RIS] Starte Voll-Export %s (%s) – %s, bis %s",
        law_name,
        gesetzesnummer,
        unit_type,
        end_num,
    )

    return build_complete_numeric(
        out_path=out_path,
        gesetzesnummer=gesetzesnummer,
        law_name=law_name,
        delay=delay,
        include_aufgehoben=include_aufgehoben,
        start_num=start_num,
        end_num=end_num,
        unit_type=unit_type,
        client=client,
    )
