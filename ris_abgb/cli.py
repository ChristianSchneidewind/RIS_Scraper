import time
import argparse
import json
import urllib.parse as _url
from typing import List, Dict

from .config import GESETZESNUMMER_ABGB
from .soap_client import version_check
from .search import search_page, extract_docrefs
from .writer import write_jsonl_from_docrefs
from .index_scraper import fetch_abgb_index_docrefs
from .toc_parser import get_current_abgb_paragraphs


def run(
    gesetzesnummer: str,
    output_path: str,
    delay_seconds: float,
    max_pages: int,
    page_size: int,
    all_pages: bool = False,
    from_index: bool = False,
    from_toc: bool = False,
    toc_date: str | None = None,
    toc_include_aufgehoben: bool = False,
    dump_toc: str | None = None,
    start_par: int = 0,
    max_par: int = 1502,
    probe_pause: float = 0.25,
    miss_limit: int = 150,
) -> None:
    version_check()

    # ---------- TOC-Modus ----------
    if from_toc:
        print("[TOC] Hole Paragraphenliste aus §0 (Inhaltsverzeichnis) …")
        toc = get_current_abgb_paragraphs(
            gesetzesnummer=gesetzesnummer,
            fassung_vom=toc_date,
            include_aufgehoben=toc_include_aufgehoben,
        )
        print(f"[TOC] {toc['count']} Paragraphen (Fassung: {toc['fassung_vom']}).")

        if dump_toc:
            with open(dump_toc, "w", encoding="utf-8") as f:
                json.dump(toc, f, ensure_ascii=False, indent=2)
            print(f"[TOC] Liste gespeichert → {dump_toc}")
            if not output_path:
                return

        if output_path:
            docrefs: List[Dict[str, str]] = []
            for pid in toc["paragraphs"]:
                pid_clean = pid.replace("§", "").strip()
                url = "https://www.ris.bka.gv.at/NormDokument.wxe?" + _url.urlencode({
                    "Abfrage": "Bundesnormen",
                    "Gesetzesnummer": gesetzesnummer,
                    "Paragraf": pid_clean,
                    "Uebergangsrecht": "",
                    "Anlage": "",
                    "Artikel": "",
                })
                docrefs.append({"id": "", "url": url})

            print(f"[TOC] {len(docrefs)} Ziel-URLs vorbereitet → schreibe JSONL …")
            rows = write_jsonl_from_docrefs(
                docrefs,
                out_path=output_path,
                delay=delay_seconds,
                gesetzesnummer=gesetzesnummer,
            )
            print(f"[OK] {rows} Zeilen → {output_path}")
            return

    # ---------- Index/Probe-Modus ----------
    if from_index:
        print("[Index] Hole NOR-Referenzen (Brute-Force §… inkl. a..z) …")
        docrefs = fetch_abgb_index_docrefs(
            start_par=start_par,
            max_par=max_par,
            probe_pause=probe_pause,
            miss_limit=miss_limit,
        )
        print(f"[Index] {len(docrefs)} Referenzen gefunden → schreibe JSONL …")
        rows = write_jsonl_from_docrefs(
            docrefs,
            out_path=output_path,
            delay=delay_seconds,
            gesetzesnummer=gesetzesnummer,
        )
        print(f"[OK] {rows} Zeilen → {output_path}")
        return


def main():
    ap = argparse.ArgumentParser(description="RIS → ABGB JSONL (Index oder TOC)")
    ap.add_argument("--gesetzesnummer", default=GESETZESNUMMER_ABGB)
    ap.add_argument("--out", default="abgb.jsonl")
    ap.add_argument("--delay", type=float, default=1.2)
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--page_size", type=int, default=20)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--from-index", action="store_true")
    ap.add_argument("--from-toc", action="store_true")
    ap.add_argument("--toc-date", type=str, default=None)
    ap.add_argument("--toc-include-aufgehoben", action="store_true")
    ap.add_argument("--dump-toc", type=str, default=None)
    ap.add_argument("--start-par", type=int, default=0)
    ap.add_argument("--max-par", type=int, default=1502)
    ap.add_argument("--probe-pause", type=float, default=0.25)
    ap.add_argument("--miss-limit", type=int, default=150)
    args = ap.parse_args()

    run(
        gesetzesnummer=args.gesetzesnummer,
        output_path=args.out,
        delay_seconds=args.delay,
        max_pages=args.pages,
        page_size=args.page_size,
        all_pages=args.all,
        from_index=args.from_index,
        from_toc=args.from_toc,
        toc_date=args.toc_date,
        toc_include_aufgehoben=args.toc_include_aufgehoben,
        dump_toc=args.dump_toc,
        start_par=args.start_par,
        max_par=args.max_par,
        probe_pause=args.probe_pause,
        miss_limit=args.miss_limit,
    )
