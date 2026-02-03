import json
import logging
import time
from datetime import datetime

from .html_parser import extract_para_id, fetch_paragraph_text_via_html
from .http_client import HttpClient, get_default_http_client
from .records import TocRecord

license_note = "Datenquelle: RIS – https://www.ris.bka.gv.at/, Lizenz: CC BY 4.0"

logger = logging.getLogger(__name__)


def write_jsonl_from_docrefs(
    docrefs,
    out_path: str,
    delay: float = 1.0,
    gesetzesnummer: str = "10001622",
    law_name: str = "ABGB",
    client: HttpClient | None = None,
) -> int:
    """
    Holt HTML-Seiten zu den Docrefs und schreibt sie als JSONL-Datei.
    docrefs = [{'id': 'NOR123', 'url': '...'}, ...]
    """
    rows = 0
    client = client or get_default_http_client()
    with open(out_path, "w", encoding="utf-8") as f:
        for i, ref in enumerate(docrefs, start=1):
            nor = ref.get("id", "")
            url = ref.get("url", "")
            logger.info("[Fetch] %s/%s – %s – %s", i, len(docrefs), nor or "(keine NOR)", url)
            try:
                parsed = fetch_paragraph_text_via_html(url, client=client)
            except Exception as exc:  # noqa: BLE001
                logger.error("[ERR] %s – %s", url, exc)
                time.sleep(delay)
                continue

            heading = (parsed.get("heading") or "").strip()
            text = (parsed.get("text") or "").strip()
            if not nor:
                nor = (parsed.get("nor") or "").strip()
            if not text:
                logger.warning("[WARN] Kein Text extrahiert für %s", nor or url)
                time.sleep(delay)
                continue

            para_id = extract_para_id(heading or text)
            retrieved_at = datetime.utcnow().isoformat() + "Z"

            record = TocRecord(
                law=law_name,
                application="Bundesnormen(HTML)",
                gesetzesnummer=gesetzesnummer,
                source="RIS HTML",
                license=license_note,
                retrieved_at=retrieved_at,
                document_number=nor or None,
                url=url,
                heading=heading or None,
                paragraph_id=para_id or None,
                text=text or None,
            )

            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            rows += 1
            time.sleep(delay)

    return rows
