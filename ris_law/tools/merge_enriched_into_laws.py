import json
from pathlib import Path

def merge_laws(base_path: str, enriched_path: str, out_path: str = None):
    base = json.loads(Path(base_path).read_text(encoding="utf-8"))
    enriched = json.loads(Path(enriched_path).read_text(encoding="utf-8"))

    enriched_by_nr = {e["gesetzesnummer"]: e for e in enriched}

    merged = []
    updated, unchanged = 0, 0

    for law in base:
        gnr = law["gesetzesnummer"]
        if gnr in enriched_by_nr:
            enriched_law = enriched_by_nr[gnr]
            if "fallback_end" in enriched_law:
                law["fallback_end"] = enriched_law["fallback_end"]
            if "unit_type" in enriched_law:
                law["unit_type"] = enriched_law["unit_type"]
            updated += 1
        else:
            unchanged += 1
        merged.append(law)

    Path(out_path or base_path).write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"✅ {updated} Gesetze aktualisiert, {unchanged} unverändert.")
    print(f"Gespeichert nach: {out_path or base_path}")

if __name__ == "__main__":
    merge_laws(
        base_path="ris_law/data/laws.json",
        enriched_path="ris_law/data/laws_enriched.json",
        out_path="ris_law/data/laws.json"
    )
