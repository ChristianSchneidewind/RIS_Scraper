#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import re
import time
import urllib.parse as _url
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

from ris_abgb.toc_parser import get_current_abgb_paragraphs
from ris_abgb.html_parser import resolve_nor_urls_from_toc_url, fetch_paragraph_text_via_html, extract_para_id

USER_LICENSE_NOTE = "Datenquelle: RIS – https://www.ris.bka.gv.at/, Lizenz: CC BY 4.0"
NOR_RX = re.compile(r"\b(NOR\d{5,})\b", re.IGNORECASE)

def _norm_display(pid: str) -> str:
    pid = pid.strip()
    if not pid.startswith("§"):
        pid = "§ " + pid
    pid = re.sub(r"^§\s*(\d+)$", r"§ \1", pid)
    return pid

def _make_toc_url(gesetzesnummer: str, numeric_pid: int) -> str:
    return "https://www.ris.bka.gv.at/NormDokument.wxe?" + _url.urlencode({
        "Abfrage": "Bundesnormen",
        "Gesetzesnummer": gesetzesnummer,
        "Paragraf": str(numeric_pid),
        "Uebergangsrecht": "",
        "Anlage": "",
        "Artikel": "",
    })

def build_complete_numeric(
    out_path: Path,
    gesetzesnummer: str = "10001622",
    delay: float = 1.2,
    toc_date: str | None = None,
    include_aufgehoben: bool = True,
    start_num: int = 1,
    end_num: int = 1502,
) -> None:
    toc = get_current_abgb_paragraphs(
        gesetzesnummer=gesetzesnummer,
        fassung_vom=toc_date,
        include_aufgehoben=include_aufgehoben,
    )
    toc_list: List[str] = [_norm_display(p) for p in toc["paragraphs"]]
    toc_set: Set[str] = set(toc_list)

    with out_path.open("w", encoding="utf-8") as fout:
        total = 0
        seen_nor: Set[str] = set()

        for n in range(start_num, end_num + 1):
            pid_disp = _norm_display(f"{n}")
            retrieved_at = datetime.utcnow().isoformat() + "Z"

            if pid_disp not in toc_set:
                rec = {
                    "law": "ABGB",
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
                    "law": "ABGB",
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
                m = NOR_RX.search(nu)
                nor = m.group(1) if m else ""

                if nor and nor in seen_nor:
                    continue

                try:
                    parsed = fetch_paragraph_text_via_html(nu)
                except Exception as e:
                    rec = {
                        "law": "ABGB",
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
                        "law": "ABGB",
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
                    "law": "ABGB",
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
                    "law": "ABGB",
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

        print(f"[OK] geschrieben: {total} Zeilen → {out_path} (sollte {end_num - start_num + 1} sein)")

def main():
    ap = argparse.ArgumentParser(description="Vollständige ABGB-Ausgabe §1..§1502 (mit Platzhaltern)")
    ap.add_argument("--out-numeric", default="abgb_complete_numeric.jsonl", help="Ziel-JSONL für §1..§1502 (genau 1502 Zeilen).")
    ap.add_argument("--gesetzesnummer", default="10001622")
    ap.add_argument("--delay", type=float, default=1.2)
    ap.add_argument("--toc-date", type=str, default=None, help="FassungVom=YYYY-MM-DD (optional)")
    ap.add_argument("--toc-include-aufgehoben", action="store_true", help="Aufgehoben/Weggefallen im TOC mitführen (empfohlen).")
    args = ap.parse_args()

    out_numeric = Path(args.out_numeric)
    build_complete_numeric(
        out_path=out_numeric,
        gesetzesnummer=args.gesetzesnummer,
        delay=args.delay,
        toc_date=args.toc_date,
        include_aufgehoben=True if args.toc_include_aufgehoben else True,
        start_num=1,
        end_num=1502,
    )

if __name__ == "__main__":
    main()