# ris_abgb/cli.py
import time
import argparse
from typing import List, Dict

from .config import GESETZESNUMMER_ABGB
from .soap_client import version_check
from .search import search_page, extract_docrefs
from .writer import write_jsonl_from_docrefs
from .index_scraper import fetch_abgb_index_docrefs


def run(
    gesetzesnummer: str,
    output_path: str,
    delay_seconds: float,
    max_pages: int,
    page_size: int,
    all_pages: bool = False,
    from_index: bool = False,
    # NEU (werden nur im Index-Modus genutzt):
    start_par: int = 0,
    max_par: int = 1502,
    probe_pause: float = 0.25,
    miss_limit: int = 150,
) -> None:
    version_check()

    # ---------- Variante A: Index/Probe (empfohlen) ----------
    if from_index:
        print("[Index] Hole NOR-Referenzen (Brute-Force §… inkl. a..z) …")
        refs = fetch_abgb_index_docrefs(
            start_par=start_par,
            max_par=max_par,
            pause=probe_pause,
            consecutive_miss_limit=miss_limit,
        )
        print(f"[Index] {len(refs)} Referenzen gefunden.")
        rows = write_jsonl_from_docrefs(
            refs,
            out_path=output_path,
            delay=delay_seconds,
            gesetzesnummer=gesetzesnummer,
        )
        print(f"[OK] {rows} Zeilen → {output_path}")
        return

    # ---------- Variante B: SOAP-Suche (liefert nur 20/Seite; Paging oft ignoriert) ----------
    all_refs: List[Dict[str, str]] = []
    page = 1
    while True:
        print(f"[Suche] Seite {page} (pageSize={page_size}) – BrKons/Gesetzesnummer={gesetzesnummer}")
        embedded = search_page(gesetzesnummer, page=page, page_size=page_size)
        if not embedded:
            print(">> Leere Suchantwort (embedded). Abbruch Paging.")
            break

        preview = embedded[:300].replace("\n", " ")
        print("  preview:", preview, "…")

        refs = extract_docrefs(embedded)
        print(f"  Treffer: {len(refs)} (NOR + HTML-URL)")

        if refs:
            all_refs.extend(refs)

        # Letzte Seite erkannt → raus
        if not refs:
            break

        page += 1
        # Nur weiterblättern, wenn --all ODER noch unter dem --pages-Limit
        if not all_pages and page > max_pages:
            break

        time.sleep(1.0)  # höflich zwischen Suchseiten

    if not all_refs:
        print(">> Keine Treffer-Referenzen – siehe last_search_embedded.xml / ...envelope.xml")
        return

    rows = write_jsonl_from_docrefs(
        all_refs,
        out_path=output_path,
        delay=delay_seconds,
        gesetzesnummer=gesetzesnummer,
    )
    print(f"[OK] {rows} Zeilen → {output_path}")


def main():
    ap = argparse.ArgumentParser(description="RIS → ABGB JSONL (Index-Probe oder SOAP-Suche + HTML-Scraping)")
    ap.add_argument("--gesetzesnummer", default=GESETZESNUMMER_ABGB, help="z. B. 10001622 (ABGB)")
    ap.add_argument("--out", default="abgb.jsonl")
    ap.add_argument("--delay", type=float, default=1.2, help="Delay zwischen Fetches (Sek.)")
    ap.add_argument("--pages", type=int, default=1, help="Anzahl Suchseiten (nur SOAP)")
    ap.add_argument("--page_size", type=int, default=20, help="Treffer/Seite (nur SOAP)")
    ap.add_argument("--all", action="store_true", help="alle Seiten automatisch ziehen (nur SOAP)")
    ap.add_argument("--from-index", action="store_true",
                    help="ABGB-Index-Strategie (brute-force §0..1502 inkl. a..z)")

    # NEU: Parameter für die Index/Probe-Variante (werden nur mit --from-index genutzt)
    ap.add_argument("--start-par", type=int, default=0, help="Start-Paragraph (Default 0)")
    ap.add_argument("--max-par", type=int, default=1502, help="Max-Paragraph (Default 1502)")
    ap.add_argument("--probe-pause", type=float, default=0.25, help="Pause pro Probe-Request in Sekunden")
    ap.add_argument("--miss-limit", type=int, default=150, help="Abbruch nach so vielen aufeinanderfolgenden Misses")

    args = ap.parse_args()  # << parse_args NACH allen add_argument!

    run(
        gesetzesnummer=args.gesetzesnummer,
        output_path=args.out,
        delay_seconds=args.delay,
        max_pages=args.pages,
        page_size=args.page_size,
        all_pages=args.all,
        from_index=args.from_index,
        start_par=args.start_par,
        max_par=args.max_par,
        probe_pause=args.probe_pause,
        miss_limit=args.miss_limit,
    )
