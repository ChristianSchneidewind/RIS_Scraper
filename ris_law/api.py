from typing import Iterator, Literal, Dict, List
import re
import urllib.parse as _url

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


def _build_docrefs_from_toc(
    gesetzesnummer: str,
    paragraphs: List[str],
    granularity: Granularity,
) -> List[Dict[str, str]]:
    """
    Baut Ziel-URLs wie in cli.py:
      - granularity='para' → eine §-URL pro Paragraph
      - granularity='nor'  → pro § alle NOR-HTML-URLs expandieren
    Rückgabe: [{'id': 'NOR…'|'' , 'url': 'https://…'}, …]
    """
    docrefs: List[Dict[str, str]] = []

    if granularity == "para":
        # 1:1 §-URLs
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

    # granularity == "nor"
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
    """
    Streamt LawItem-Objekte (keine Datei nötig).
    """
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
        # retrieved_at wird aus writer.py normalerweise mit UTC+Z gebaut; hier lassen wir es leer/None
        yield LawItem(
            law=law_name,
            gesetzesnummer=gesetzesnummer,
            paragraph_id=para_id or None,
            heading=heading or None,
            text=text,
            url=ref["url"],
            source="RIS HTML",
            document_number=nor or None,
            retrieved_at="",  # wenn du willst: hier Datum setzen
        )


def write_jsonl(
    gesetzesnummer: str,
    law_name: str,
    out_path: str,
    granularity: Granularity = "nor",
    include_aufgehoben: bool = True,
    delay: float = 1.0,
) -> int:
    """
    Komfort: schreibt direkt JSONL (nutzt deinen writer).
    """
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
    Vollständiger Export im Stil abgb_komplett – aber mit dynamischem end_num (aus TOC).
    """
    return build_complete_numeric(
        out_path=out_path,
        gesetzesnummer=gesetzesnummer,
        law_name=law_name,
        delay=delay,
        toc_date=toc_date,
        include_aufgehoben=include_aufgehoben,
        start_num=start_num,
        end_num=end_num,  # None ⇒ automatisch aus TOC
    )
