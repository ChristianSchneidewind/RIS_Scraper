import json
import time
import datetime as dt
from typing import List, Dict
from .html_parser import fetch_paragraph_text_via_html, extract_para_id

def write_jsonl_from_docrefs(
    docrefs: List[Dict[str, str]],
    out_path: str,
    delay: float = 1.2,
    gesetzesnummer: str = "10001622",
) -> int:
    retrieved_at = dt.datetime.now(dt.timezone.utc).isoformat()
    license_note = "Daten: Rechtsinformationssystem des Bundes (RIS), CC-BY 4.0"
    written = 0

    with open(out_path, "w", encoding="utf-8") as f:
        for i, ref in enumerate(docrefs, 1):
            nor = ref.get("id", "")
            url = ref.get("url", "")
            print(f"[Fetch] {i}/{len(docrefs)} – {nor} – {url or '(keine URL)'}")

            try:
                parsed = fetch_paragraph_text_via_html(url)
            except Exception as e:
                print(f"[WARN] Fehler beim Laden {nor}: {e}; überspringe.")
                time.sleep(delay)
                continue

            heading = (parsed.get("heading") or "").strip()
            text    = (parsed.get("text") or "").strip()
            if not text:
                print(f"[WARN] Kein Text extrahiert für {nor}; überspringe.")
                time.sleep(delay)
                continue

            para_id = extract_para_id(heading) or extract_para_id(text)

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
            written += 1
            time.sleep(delay)
    return written
