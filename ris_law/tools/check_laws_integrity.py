import json
from pathlib import Path

def check_laws(path="ris_law/data/laws.json"):
    file = Path(path)
    if not file.exists():
        raise FileNotFoundError(f"❌ Datei nicht gefunden: {file}")

    print(f"[🔍] Prüfe Gesetze in {file}")
    data = json.loads(file.read_text(encoding="utf-8"))

    missing_fallback = []
    missing_unit = []

    for law in data:
        name = law.get("kurz", "(unbekannt)") or law.get()
        gnr = law.get("gesetzesnummer", "?")

        if not law.get("fallback_end"):
            missing_fallback.append((gnr, name))
        if not law.get("unit_type"):
            missing_unit.append((gnr, name))

    print("\n📊 **Überblick**")
    print(f"   → Gesamt: {len(data)}")
    print(f"   → Ohne fallback_end: {len(missing_fallback)}")
    print(f"   → Ohne unit_type: {len(missing_unit)}")

    if missing_fallback:
        print("\n⚠️  Gesetze ohne fallback_end:")
        for gnr, name in missing_fallback:
            print(f"   - {name} ({gnr})")

    if missing_unit:
        print("\n⚠️  Gesetze ohne unit_type:")
        for gnr, name in missing_unit:
            print(f"   - {name} ({gnr})")

    if not missing_fallback and not missing_unit:
        print("\n✅ Alle Gesetze vollständig!")

if __name__ == "__main__":
    check_laws()
