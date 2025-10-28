import json
from pathlib import Path
import shutil

def merge_laws(base_path: str, enriched_path: str, out_path: str = None):
    base_file = Path(base_path)
    enriched_file = Path(enriched_path)
    out_file = Path(out_path or base_path)

    if not base_file.exists():
        raise FileNotFoundError(f"❌ Basisdatei nicht gefunden: {base_file}")
    if not enriched_file.exists():
        raise FileNotFoundError(f"❌ Enriched-Datei nicht gefunden: {enriched_file}")

    print(f"[🔍] Lade Basisdaten aus {base_file}")
    base_data = json.loads(base_file.read_text(encoding="utf-8"))

    print(f"[🔍] Lade Enriched-Daten aus {enriched_file}")
    enriched_data = json.loads(enriched_file.read_text(encoding="utf-8"))

    enriched_map = {item["gesetzesnummer"]: item for item in enriched_data}

    # Backup der Originaldatei
    backup_path = base_file.with_suffix(".bak")
    print(f"[💾] Erstelle Backup: {backup_path}")
    shutil.copy2(base_file, backup_path)

    updated = 0
    skipped_existing = 0
    unchanged = 0

    for entry in base_data:
        gnr = entry.get("gesetzesnummer")
        if not gnr:
            continue
        enriched = enriched_map.get(gnr)
        if not enriched:
            unchanged += 1
            continue

        changed = False

        # fallback_end nur setzen, wenn es noch nicht existiert
        if "fallback_end" in enriched and enriched["fallback_end"]:
            if "fallback_end" not in entry or not entry["fallback_end"]:
                entry["fallback_end"] = enriched["fallback_end"]
                changed = True
            else:
                skipped_existing += 1

        # unit_type nur setzen, wenn es noch nicht existiert
        if "unit_type" in enriched and enriched["unit_type"]:
            if "unit_type" not in entry or not entry["unit_type"]:
                entry["unit_type"] = enriched["unit_type"]
                changed = True
            else:
                skipped_existing += 1

        if changed:
            updated += 1
        else:
            unchanged += 1

    out_file.write_text(json.dumps(base_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[✅] {updated} Gesetze aktualisiert, {skipped_existing} vorhandene übersprungen, {unchanged} unverändert.")
    print(f"[📘] Gespeichert nach: {out_file}")
    print(f"[🧾] Backup liegt unter: {backup_path}")

if __name__ == "__main__":
    merge_laws(
        base_path="ris_law/data/laws.json",
        enriched_path="ris_law/data/laws_enriched.json",
        out_path="ris_law/data/laws.json"
    )
