import json
import re
from pathlib import Path
from typing import List, Dict

# Paragraph-Marker: "§ 1", "§ 1a", "§ 22", ...
PARA_PATTERN = re.compile(r"(§\s*\d+[a-zA-Z]?)")


def split_article_row_into_paragraphs(row: Dict) -> List[Dict]:
    """
    Nimmt eine Zeile (Artikel-Einheit) und erzeugt 0..N neue Zeilen
    auf Paragraph-Ebene.

    - Paragraphen werden über '§ <Nummer>'-Marker erkannt.
    - Es werden nur Paragraphnummern im Bereich 0–70 zugelassen (DSG).
    - unit_type wird auf "paragraf" gesetzt.
    - parent_unit enthält den ursprünglichen Artikel.
    """
    text = (row.get("text") or "").strip()
    if not text:
        return [row]

    parent_unit = row.get("unit") or row.get("heading") or ""

    parts = PARA_PATTERN.split(text)
    if len(parts) < 3:
        # Keine §-Marker → unverändert zurückgeben
        return [row]

    new_rows: List[Dict] = []

    # parts: [prefix, marker1, content1, marker2, content2, ...]
    prefix = parts[0].strip()  # ignorieren wir erstmal

    for i in range(1, len(parts), 2):
        marker = parts[i].strip()          # z.B. "§ 22"
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""

        # Paragraph-Nummer extrahieren
        m_num = re.search(r"(\d+[a-zA-Z]?)", marker)
        if not m_num:
            continue
        para_number = m_num.group(1)

        # Nur DSG-Bereich zulassen (0–70)
        try:
            base_int = int(re.match(r"\d+", para_number).group(0))
        except Exception:
            continue

        if not (0 <= base_int <= 70):
            # Vermutlich Verweis auf andere Gesetze
            continue

        # Neue Zeile auf Basis der Originalzeile
        new_row = dict(row)  # flache Kopie

        new_row["unit_type"] = "paragraf"
        new_row["unit"] = marker
        new_row["unit_number"] = para_number
        new_row["parent_unit"] = parent_unit
        new_row["text"] = content

        new_rows.append(new_row)

    # Wenn nichts übrig bleibt, Original zurückgeben
    return new_rows or [row]


def split_file(input_path: str | Path, output_path: str | Path) -> int:
    """
    Liest eine JSONL-Datei (full-Schema mit Artikel-Einheiten),
    splittet soweit möglich in Paragraph-Einheiten und schreibt
    eine neue JSONL nach output_path.

    Dedupliziert pro (unit_number, parent_unit) und behält jeweils
    die Zeile mit dem längsten Text.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Eingabedatei nicht gefunden: {input_path}")

    count_in = 0

    # key -> beste Zeile (längster Text)
    best_rows: Dict[tuple, Dict] = {}

    with input_path.open("r", encoding="utf-8") as fin:
        for line in fin:
            line = line.strip()
            if not line:
                continue

            count_in += 1
            row = json.loads(line)

            # Nur Artikel wirklich splitten – andere Zeilen ggf. unverändert übernehmen
            if row.get("unit_type") != "artikel":
                # Optional: hier entscheiden, ob man die behalten will.
                # Wir ignorieren sie erstmal.
                continue

            new_rows = split_article_row_into_paragraphs(row)

            for nr in new_rows:
                # Nur echte Paragraph-Zeilen berücksichtigen
                if nr.get("unit_type") != "paragraf":
                    continue

                key = (nr.get("unit_number"), nr.get("parent_unit"))
                text_len = len((nr.get("text") or "").strip())

                if key not in best_rows:
                    best_rows[key] = nr
                else:
                    # die Zeile mit dem längeren Text bevorzugen
                    prev = best_rows[key]
                    prev_len = len((prev.get("text") or "").strip())
                    if text_len > prev_len:
                        best_rows[key] = nr

    # Ergebnis schreiben
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fout:
        for row in best_rows.values():
            fout.write(json.dumps(row, ensure_ascii=False))
            fout.write("\n")

    count_out = len(best_rows)
    print(f"[INFO] Fertig: {count_in} Eingabezeilen → {count_out} Paragraph-Zeilen.")
    print(f"[INFO] Neue Datei: {output_path}")
    return count_out


if __name__ == "__main__":
    # Skript-Ordner (= ris_law/tools)
    BASE = Path(__file__).parent

    in_file = BASE / "dsg.jsonl"
    out_file = BASE / "dsg_paragraphs.jsonl"

    split_file(in_file, out_file)
