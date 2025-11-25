import json
import re
from pathlib import Path
from datetime import date

INPUT_FILE = Path("ris_gesetze.json")
OUTPUT_FILE = Path("ris_gesetze_gesetze_only.json")


# --------------------------
# 1) Nur Einträge vom Typ "BG"
# --------------------------

def is_law_type(entry: dict) -> bool:
    """
    Akzeptiere NUR Bundesgesetze.
    Alles andere (V, Vertrag, BGBl. III, Vereinbarung etc.) raus.
    """
    typ = (entry.get("typ") or "").strip().lower()

    # Eindeutiges Bundesgesetz
    if typ == "bg":
        return True

    # Manche Einträge haben "bundesgesetz" ausgeschrieben
    if "bundesgesetz" in typ:
        return True

    return False


# --------------------------
# 2) Titel-Filter (Variante A – sehr streng)
# --------------------------

def is_relevant_title(entry: dict) -> bool:
    """
    Sehr strenger Titel-Filter.
    Alles raus, was nach Münzen, Sonder-Ausgaben, Verordnungen etc. aussieht.
    """
    title = (entry.get("titel") or "").strip()
    tl = title.lower()

    if not title:
        return False

    # Münzen / Gedenkmünzen z.B. "100 S - ..."
    if re.match(r"^\s*\d+\s*(s|schilling|€|eur)\b", tl):
        return False

    # Verordnungen/Kundmachungen
    if any(k in tl for k in ["verordnung", "kundmachung"]):
        return False

    # Novellen / Änderungsgesetze
    if any(k in tl for k in ["novelle", "änderung", "abänderung", "geändert"]):
        return False

    if tl.startswith("abänderung"):
        return False

    # Tarife, Preise, Gebühren
    if any(k in tl for k in ["tarif", "gebühr", "preis", "pauschal", "verkaufspreis"]):
        return False

    # Durchführungs-/Umsetzungsgesetze entfernen
    if "durchführungsgesetz" in tl:
        return False

    # Führende Zahl + Punkt (z.B. "2. Staatsvertragsdurchführungsgesetz")
    if re.match(r"^\d+\.\s", tl):
        return False

    # Abschluss eines Übereinkommens
    if tl.startswith("abschluss eines übereinkommens"):
        return False

    # Festlegungen nach anderen Gesetzen
    if " nach dem " in tl or " nach der " in tl:
        return False

    # Positive Kriterien – „echte“ Gesetze:
    if "gesetzbuch" in tl:
        return True

    if re.search(r"gesetz($| )", tl):
        return True

    return False


# --------------------------
# 3) Gültigkeit prüfen
# --------------------------

def is_current(entry: dict) -> bool:
    """
    Gültig = kein Ausserkrafttretedatum oder >= heute.
    """
    ak = entry.get("ausserkraft")
    if not ak:
        return True

    try:
        year, month, day = map(int, ak.split("-"))
        ak_date = date(year, month, day)
    except Exception:
        return True

    return ak_date >= date.today()


# --------------------------
# 4) Hauptlogik (inkrementell)
# --------------------------

def main():
    # 4.1 Eingabedatei prüfen / laden
    if not INPUT_FILE.exists():
        print(f"[FATAL] {INPUT_FILE} nicht gefunden.")
        return

    with INPUT_FILE.open(encoding="utf-8") as f:
        laws = json.load(f)

    print(f"[INFO] Eingelesen: {len(laws)} Einträge aus {INPUT_FILE}.")

    # 4.2 Bisherige gefilterte Gesetze laden (falls vorhanden)
    existing_by_gnr = {}
    if OUTPUT_FILE.exists():
        with OUTPUT_FILE.open(encoding="utf-8") as f:
            existing = json.load(f)
        for e in existing:
            gnr = e.get("gesetzesnummer")
            if gnr:
                existing_by_gnr[gnr] = e
        print(f"[INFO] Bereits vorhandene gefilterte Gesetze: {len(existing_by_gnr)}")
    else:
        print("[INFO] Noch keine bestehende Ausgabedatei – starte neu.")

    # 4.3 Neue Filterung der aktuellen INPUT_FILE
    newly_filtered = [
        e for e in laws
        if is_law_type(e)
        and is_relevant_title(e)
        and is_current(e)
    ]

    print(f"[INFO] Neu gefundene passende Gesetze in diesem Lauf: {len(newly_filtered)}")

    # 4.4 Merge: neue Einträge in bestehendes Dict einfügen / überschreiben
    for e in newly_filtered:
        gnr = e.get("gesetzesnummer")
        if not gnr:
            continue
        existing_by_gnr[gnr] = e  # überschreibt ggf. ältere Version

    merged = list(existing_by_gnr.values())
    print(f"[INFO] Gesamtanzahl gefilterter Gesetze nach Merge: {len(merged)}")

    # 4.5 Zurückschreiben
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"[OK] Gefilterter Gesetzesindex in {OUTPUT_FILE} gespeichert.")


if __name__ == "__main__":
    main()
