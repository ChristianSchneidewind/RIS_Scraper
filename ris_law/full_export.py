# ris_law/full_export.py
from __future__ import annotations

import json
import re
import time
import urllib.parse as _url
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Set, Optional

from .toc_parser import get_current_abgb_paragraphs
from .html_parser import resolve_nor_urls_from_toc_url, fetch_paragraph_text_via_html, extract_para_id
from .config import fallback_end_for  # ⬅️ neu

USER_LICENSE_NOTE = "Datenquelle: RIS – https://www.ris.bka.gv.at/, Lizenz: CC BY 4.0"
_RX_NOR = re.compile(r"\b(NOR\d{5,})\b", re.IGNORECASE)
_RX_NUM = re.compile(r"§\s*(\d+)", re.IGNORECASE)


def _norm_display(pid: str) -> str:
    """Normalisiert eine Paragraphenanzeige, z. B. '1' → '§ 1', '§1a' → '§ 1a'."""
    pid = pid.strip()
    if not pid.startswith("§"):
        pid = "§ " + pid
    pid = re.sub(r"^§\s*(\d+)$", r"§ \1", pid)
    return pid


def _make_toc_url(gesetzesnummer: str, numeric_pid: int) -> str:
    """Baut die Standard-HTML-URL für einen numerischen § (wie in abgb_komplett)."""
    return "https://www.ris.bka.gv.at/NormDokument.wxe?" + _url.urlencode({
        "Abfrage": "Bundesnormen",
        "Gesetzesnummer": gesetzesnummer,
        "Paragraf": str(numeric_pid),
        "Uebergangsrecht": "",
        "Anlage": "",
        "Artikel": "",
    })


def infer_max_numeric_from_toc(paragraphs: Iterable[str]) -> int:
    """Ermittelt die höchste §-Nummer aus einer TOC-Liste (ignoriert Buchstabenanhänge)."""
    max_n = 0
    for p in paragraphs:
        m = _RX_NUM.search(p)
        if not m:
            continue
        try:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
        except ValueError:
            pass
    return max_n if max_n > 0 else 1


def build_complete_numeric(
    out_path: Path | str,
    gesetzesnummer: str,
    law_name: str,
    delay: float = 1.2,
    toc_date: Optional[str] = None,
    include_aufgehoben: bool = True,
    start_num: int = 1,
    end_num: Optional[int] = None,
) -> int:
    """
    'Vollständiger' Export wie abgb_komplett – aber mit *dynamischem* end_num.
    Wenn das TOC keine oder kaum Einträge hat, wird automatisch auf ein
    numerisches Fallback (z. B. 1–321 für StGB) umgeschaltet – die Grenze
    kommt aus config.fallback_end_for().
    """
    # 1) TOC holen
    toc = get_current_abgb_paragraphs(
        gesetzesnummer=gesetzesnummer,
        fassung_vom=toc_date,
        include_aufgehoben=include_aufgehoben,
    )
    toc_list: List[str] = [_norm_display(p) for p in toc["paragraphs"]]
    toc_set: Set[str] = set(toc_list)

    # 2) Fallback, falls TOC leer oder unvollständig
    if len(toc_list) <= 2:
        # Grenze aus der zentralen Liste (ris_law/data/laws.json) – oder 1000 als Default
        end_num = fallback_end_for(gesetzesnummer) or 1000
        print(f"[WARN] Kein oder unvollständiges TOC – Fallback auf §1–{end_num}")
        toc_list = [f"§ {i}" for i in range(1, end_num + 1)]
        toc_set = set(toc_list)

    # 3) Endgrenze automatisch bestimmen, wenn nicht angegeben
    if end_num is None:
        end_num = infer_max_numeric_from_toc(toc_list)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    seen_nor: Set[str] = set()

    with out_path.open("w", encoding="utf-8") as fout:
        for n in range(start_num, end_num + 1):
            pid_disp = _norm_display(f"{n}")
            retrieved_at = datetime.utcnow().isoformat() + "Z"

            if pid_disp not in toc_set:
                rec = {
                    "law": law_name,
                    "application": "Bundesnormen(HTML)",
                    "gesetzesnummer": gesetzesnummer,
                    "source": "RIS HTML",
                    "license": USER_LICENSE_NOTE,
                    "retrieved_at": retrieved_at,
                    "document_number": "",
                    "url": "",
                    "heading": "",
                    "paragraph_id": pid_disp,
                    "text": "",
                    "status": "not_in_toc_geltende_fassung"
                }
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                total += 1
                continue

            toc_url = _make_toc_url(gesetzesnummer, n)
            try:
                nor_urls = resolve_nor_urls_from_toc_url(toc_url)
            except Exception as e:
                rec = {
                    "law": law_name,
                    "application": "Bundesnormen(HTML)",
                    "gesetzesnummer": gesetzesnummer,
                    "source": "RIS HTML",
                    "license": USER_LICENSE_NOTE,
                    "retrieved_at": retrieved_at,
                    "document_number": "",
                    "url": toc_url,
                    "heading": "",
                    "paragraph_id": pid_disp,
                    "text": "",
                    "status": f"resolve_failed: {e}"
                }
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                total += 1
                time.sleep(delay)
                continue

            wrote_for_this_number = False
            for nu in nor_urls:
                m = _RX_NOR.search(nu)
                nor = m.group(1) if m else ""

                if nor and nor in seen_nor:
                    continue

                try:
                    parsed = fetch_paragraph_text_via_html(nu)
                except Exception as e:
                    rec = {
                        "law": law_name,
                        "application": "Bundesnormen(HTML)",
                        "gesetzesnummer": gesetzesnummer,
                        "source": "RIS HTML",
                        "license": USER_LICENSE_NOTE,
                        "retrieved_at": retrieved_at,
                        "document_number": nor,
                        "url": nu,
                        "heading": "",
                        "paragraph_id": pid_disp,
                        "text": "",
                        "status": f"fetch_failed: {e}"
                    }
                    fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    total += 1
                    time.sleep(delay)
                    continue

                heading = (parsed.get("heading") or "").strip()
                text    = (parsed.get("text") or "").strip()
                nor     = (parsed.get("nor") or nor).strip()
                if nor:
                    seen_nor.add(nor)

                if not text:
                    rec = {
                        "law": law_name,
                        "application": "Bundesnormen(HTML)",
                        "gesetzesnummer": gesetzesnummer,
                        "source": "RIS HTML",
                        "license": USER_LICENSE_NOTE,
                        "retrieved_at": retrieved_at,
                        "document_number": nor,
                        "url": nu,
                        "heading": heading,
                        "paragraph_id": pid_disp,
                        "text": "",
                        "status": "empty_text"
                    }
                    fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    total += 1
                    time.sleep(delay)
                    wrote_for_this_number = True
                    continue

                para_id = extract_para_id(heading or text) or pid_disp
                rec = {
                    "law": law_name,
                    "application": "Bundesnormen(HTML)",
                    "gesetzesnummer": gesetzesnummer,
                    "source": "RIS HTML",
                    "license": USER_LICENSE_NOTE,
                    "retrieved_at": retrieved_at,
                    "document_number": nor,
                    "url": nu,
                    "heading": heading,
                    "paragraph_id": para_id,
                    "text": text,
                    "status": "ok"
                }
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                total += 1
                time.sleep(delay)
                wrote_for_this_number = True

            if not wrote_for_this_number:
                rec = {
                    "law": law_name,
                    "application": "Bundesnormen(HTML)",
                    "gesetzesnummer": gesetzesnummer,
                    "source": "RIS HTML",
                    "license": USER_LICENSE_NOTE,
                    "retrieved_at": retrieved_at,
                    "document_number": "",
                    "url": toc_url,
                    "heading": "",
                    "paragraph_id": pid_disp,
                    "text": "",
                    "status": "no_nor_found"
                }
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                total += 1

    return total
