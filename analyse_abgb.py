import json
import re
from collections import Counter

PATH = "./abgb.jsonl"   # liegt laut Screenshot im Projektstamm

# Felder, die potentiell die Paragraph-ID enthalten könnten (Reihenfolge = Priorität)
PID_CANDIDATE_FIELDS = [
    "paragraph_id", "paragraph", "para", "section", "heading", "title", "rubrum"
]

total_lines = 0
parsed_lines = 0
json_errors = 0
pid_missing = 0

numeric_set = set()      # {1, 2, 3, ...}
letter_ids = set()       # {"1a", "17b", ...}
raw_pids = []            # z.B. "§ 1", "§ 17a", "Anlage 1"
attachments = []         # Anlagen/Anhang heuristisch
pid_source_stats = Counter()

def extract_pid(entry):
    """Suche die Paragraph-ID in verschiedenen Feldern."""
    for f in PID_CANDIDATE_FIELDS:
        v = entry.get(f)
        if isinstance(v, str) and v.strip():
            pid_source_stats[f] += 1
            return v.strip()
    return ""

def normalize_pid(pid: str):
    """Gibt (numeric:int|None, letter:str|None, pid_clean:str) zurück."""
    # Anlage/Anhang früh filtern
    if re.search(r"\b(anhang|anlage|verzeichnis|schlußformel|schlussformel)\b", pid, re.IGNORECASE):
        return (None, None, pid)

    # Häufige Formen: "§ 1", "§1a", "1", "1a", "Paragraph 1", "Artikel 2"
    # alles Kleinbuchstaben + § entfernen
    p = pid.replace("§", "").strip()
    p = re.sub(r"(?i)\b(paragraph|artikel|art\.?)\b", "", p).strip()

    # nur die erste Nummer+optional Buchstabe nehmen
    m = re.match(r"^0*(\d+)([a-zA-Z]?)$", p)
    if m:
        n = int(m.group(1))
        letter = m.group(2) or None
        return (n, letter, p)
    return (None, None, pid)

with open(PATH, "r", encoding="utf-8") as f:
    for line in f:
        total_lines += 1
        try:
            obj = json.loads(line)
            parsed_lines += 1
        except json.JSONDecodeError:
            json_errors += 1
            continue

        pid = extract_pid(obj)
        if not pid:
            pid_missing += 1
            continue

        raw_pids.append(pid)
        n, letter, cleaned = normalize_pid(pid)
        if n is not None:
            numeric_set.add(n)
            if letter:
                letter_ids.add(f"{n}{letter}")
        else:
            # kein numerischer § → prüfen, ob Anlage
            if re.search(r"\b(anhang|anlage|verzeichnis)\b", pid, re.IGNORECASE):
                attachments.append(pid)

# Lücken berechnen (nur numerische §§ zwischen min…max)
if numeric_set:
    min_n = min(numeric_set)
    max_n = max(numeric_set)
    expected = set(range(min_n, max_n + 1))
    missing = sorted(expected - numeric_set)
else:
    min_n = max_n = None
    missing = []

print("\n📊 Analyse ABGB.jsonl")
print("========================================")
print(f"Gesamtzeilen:            {total_lines}")
print(f"→ davon parsebar:        {parsed_lines}")
print(f"→ JSON-Fehler:           {json_errors}")
print(f"→ ohne ermittelbare ID:  {pid_missing}")
print()
print(f"Numerische Paragraphen:  {len(numeric_set)} (Bereich: §{min_n} – §{max_n})")
print(f"Buchstaben-Paragraphen:  {len(letter_ids)}  (Beispiel: {sorted(list(letter_ids))[:10]})")
print(f"Anhänge/Anlagen:         {len(attachments)}  (Beispiel: {attachments[:5]})")
print()
print(f"Fehlende Paragraphen ({len(missing)}): {missing[:100]}")  # erste 100 anzeigen
print()
print("Feld, aus dem die ID kam (Top 5):")
for k, v in pid_source_stats.most_common(5):
    print(f"  {k}: {v}")
