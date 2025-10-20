import time
import json
from datetime import datetime
from .html_parser import fetch_paragraph_text_via_html, extract_para_id

license_note = "Datenquelle: RIS – https://www.ris.bka.gv.at/, Lizenz: CC BY 4.0"

def write_jsonl_from_docrefs(
    docrefs,
    out_path: str,
    delay: float = 1.0,
    gesetzesnummer: str = "10001622",
) -> int:
    """
    Holt HTML-Seiten zu den Docrefs und schreibt sie als JSONL-Datei.
    docrefs = [{'id': 'NOR123', 'url': '...'}, ...]
    """
    rows = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for i, ref in enumerate(docrefs, start=1):
            nor = ref.get("id", "")
            url = ref.get("url", "")
            print(f"[Fetch] {i}/{len(docrefs)} – {nor or '(keine NOR)'} – {url}")
            try:
                parsed = fetch_paragraph_text_via_html(url)
            except Exception as e:
                print(f"[ERR] {url} – {e}")
                time.sleep(delay)
                continue

            heading = (parsed.get("heading") or "").strip()
            text = (parsed.get("text") or "").strip()
            if not nor:
                nor = (parsed.get("nor") or "").strip()
            if not text:
                print(f"[WARN] Kein Text extrahiert für {nor or url}")
                time.sleep(delay)
                continue

            para_id = extract_para_id(heading or text)
            retrieved_at = datetime.utcnow().isoformat() + "Z"

            rec = {
                "law": "ABGB",
                "application": "Bundesnormen(HTML)",
                "gesetzesnummer": gesetzesnummer,
                "source": "RIS HTML",
                "license": license_note,
                "retrieved_at": retrieved_at,
                "document_number": nor,
                "url": url,
                "heading": heading,
                "paragraph_id": para_id,
                "text": text,
            }

            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows += 1
            time.sleep(delay)

    return rows
