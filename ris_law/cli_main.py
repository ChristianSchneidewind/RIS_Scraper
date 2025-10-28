# ris_law/cli_main.py
import argparse
from .api import write_jsonl, write_jsonl_full

def main():
    ap = argparse.ArgumentParser(description="RIS → JSONL (Library CLI)")
    ap.add_argument("--gesetzesnummer", required=True)
    ap.add_argument("--law", required=True)
    ap.add_argument("--out", required=True)

    ap.add_argument("--mode", choices=["toc", "full"], default="full",
                    help="toc = TOC-gesteuert; full = numerisch vollständig (dynamisches Ende aus TOC).")
    ap.add_argument("--granularity", choices=["para", "nor"], default="nor",
                    help="nur im mode=toc relevant")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--include-aufgehoben", action="store_true")
    ap.add_argument("--toc-date", default=None)

    ap.add_argument("--start-num", type=int, default=1,
                    help="nur im mode=full: Start-§ (default 1)")
    ap.add_argument("--end-num", type=int, default=None,
                    help="nur im mode=full: Ende-§ (default: automatisch aus TOC)")

    args = ap.parse_args()

    if args.mode == "full":
        rows = write_jsonl_full(
            gesetzesnummer=args.gesetzesnummer,
            law_name=args.law,
            out_path=args.out,
            delay=args.delay,
            include_aufgehoben=args.include_aufgehoben,
            toc_date=args.toc_date,
            start_num=args.start_num,
            end_num=args.end_num,
        )
    else:
        rows = write_jsonl(
            gesetzesnummer=args.gesetzesnummer,
            law_name=args.law,
            out_path=args.out,
            granularity=args.granularity,
            include_aufgehoben=args.include_aufgehoben,
            delay=args.delay,
        )

    print(f"{rows} Dokumente in {args.out} geschrieben.")
