import requests
import math
import re
import json
import os
from collections import Counter
from typing import Dict, Any
from datetime import date

BASE_URL = "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht"

# Wie viele Seiten maximal? Zum Testen z.B. 200, für „alles“ auf None setzen.
MAX_PAGES = None  # oder z.B. 200

# Stichtag, für den die Geltung geprüft werden soll
AS_OF_DATE = date.today().isoformat()

OUTPUT_FILE = "ris_gesetze.json"

# Datei, in der der Fortschritt gespeichert wird
STATE_FILE = "ris_law_state.json"

# Flag, damit wir die Beispiel-Metadaten nur EINMAL ausgeben
PRINTED_EXAMPLE = False


# -------------------- State-Handling -------------------- #

def load_state() -> tuple[Dict[str, Any], int]:
    """
    State-Datei laden, falls vorhanden.

    Rückgabe:
      - laws: Dict[gesetzesnummer -> {kurz, titel, numbers, inkraft, ausserkraft, typ}]
      - last_page: zuletzt erfolgreich verarbeitete Seitennummer (0 = noch nichts)
    """
    if not os.path.exists(STATE_FILE):
        print("[INFO] Kein STATE_FILE gefunden – starte bei Seite 1.")
        return {}, 0

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        laws = data.get("laws", {})
        last_page = data.get("last_page", 0)
        print(f"[INFO] STATE_FILE gefunden – {len(laws)} Gesetze bis Seite {last_page} geladen.")
        return laws, last_page
    except Exception as e:
        print(f"[WARN] Konnte STATE_FILE nicht laden ({e}) – starte neu.")
        return {}, 0


def save_state(laws: Dict[str, Any], last_page: int) -> None:
    """
    Aktuellen Stand in STATE_FILE schreiben.
    """
    data = {
        "last_page": last_page,
        "laws": laws,
    }
    tmp_file = STATE_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp_file, STATE_FILE)
    print(f"[INFO] STATE_FILE aktualisiert (Seite {last_page}, {len(laws)} Gesetze).")


# -------------------- API-Zugriff -------------------- #

def fetch_page(page: int, page_size: int = 100) -> dict | None:
    """
    Holt eine Seite aus der OGD-RIS-API.

    Paging in v2.6:
      - Seitennummer
      - DokumenteProSeite: Twenty | Fifty | OneHundred
    """
    if page_size <= 20:
        dps = "Twenty"
        page_size = 20
    elif page_size <= 50:
        dps = "Fifty"
        page_size = 50
    else:
        dps = "OneHundred"
        page_size = 100

    params = {
        "Applikation": "BrKons",
        "Seitennummer": page,
        "DokumenteProSeite": dps,
        # Wichtig: nur Normen, die an diesem Tag in Kraft sind
        "Fassung.FassungVom": AS_OF_DATE,
    }

    print(f"[INFO] Request Seitennummer={page}, DokumenteProSeite={dps} -> {BASE_URL}")
    try:
        r = requests.get(BASE_URL, params=params, timeout=60)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] Request für Seitennummer {page} fehlgeschlagen: {e}")
        return None

    try:
        data = r.json()
    except ValueError as e:
        print(f"[ERROR] JSON-Fehler auf Seitennummer {page}: {e}")
        print(f"[DEBUG] Body (Anfang): {r.text[:300]}")
        return None

    if "OgdSearchResult" not in data:
        print(f"[ERROR] OgdSearchResult fehlt (Seite {page}): {list(data.keys())}")
        return None

    results = data["OgdSearchResult"].get("OgdDocumentResults")
    if results is None:
        print(f"[ERROR] OgdDocumentResults fehlt (Seite {page})")
        return None

    return results


# -------------------- Verarbeitung einer Seite -------------------- #

def handle_results(results_obj: dict, laws: Dict[str, Any], page: int) -> None:
    """
    Verarbeitet eine Seite OgdDocumentResults und aggregiert nach gesetzesnummer.

    - Normtyp (BrKons.Typ) wird gespeichert.
    - Inkrafttretensdatum aus BrKons.Inkrafttretensdatum
    - Paragraph-/Artikelnummern gesammelt für fallback_end
    """
    global PRINTED_EXAMPLE

    docs = results_obj.get("OgdDocumentReference", [])
    if isinstance(docs, dict):
        docs = [docs]

    print(f"[DEBUG] Seite {page}: {len(docs)} Dokumente, bisher {len(laws)} Gesetze")

    # EINMAL Beispiel-Metadaten ausgeben, um Struktur zu inspizieren
    if not PRINTED_EXAMPLE and docs:
        try:
            example_meta = docs[0]["Data"]["Metadaten"]
            print("=== DEBUG: Beispiel-Metadaten ===")
            print(json.dumps(example_meta, indent=2, ensure_ascii=False))
            print("=== ENDE DEBUG ===")
        except Exception as e:
            print(f"[WARN] Konnte Beispiel-Metadaten nicht ausgeben: {e}")
        PRINTED_EXAMPLE = True

    first_gnr = None

    for i, ref in enumerate(docs):
        try:
            meta = ref["Data"]["Metadaten"]
            br = meta["Bundesrecht"]
            brk = br["BrKons"]

            gesetzesnummer = brk["Gesetzesnummer"]
            abk = brk.get("Abkuerzung")
            titel = br.get("Kurztitel") or br.get("Titel") or br.get("Langtitel") or ""

            doktyp = brk.get("Dokumenttyp")       # "Norm", etc.
            paragrafnr = brk.get("Paragraphnummer", "")
            artikelnr = brk.get("Artikelnummer", "")

            # Normtyp (z.B. "BG", "V", "Vertrag – Schweiz", ...)
            normtyp = brk.get("Typ", "")

            # Inkrafttretensdatum aus BrKons
            inkraft = brk.get("Inkrafttretensdatum")
            # Ausserkraft haben wir hier nicht, bleibt vorerst None
            ausserkraft = None

        except KeyError as e:
            print(f"[WARN] Unerwartete Struktur (fehlender Key {e}) – Eintrag übersprungen.")
            continue

        if i == 0:
            first_gnr = gesetzesnummer

        law = laws.setdefault(
            gesetzesnummer,
            {
                "kurz": abk,
                "titel": titel.strip(),
                "numbers": [],
                "inkraft": inkraft,
                "ausserkraft": ausserkraft,
                "typ": normtyp,
            },
        )

        # Abkürzung / Titel / Inkraftdatum / Typ nachziehen, falls vorher None
        if not law.get("kurz") and abk:
            law["kurz"] = abk
        if not law.get("titel") and titel:
            law["titel"] = titel.strip()
        if not law.get("inkraft") and inkraft:
            law["inkraft"] = inkraft
        if not law.get("typ") and normtyp:
            law["typ"] = normtyp

        # Paragraph/Artikel-Nummern sammeln
        if doktyp == "Paragraph":
            nr = paragrafnr
        elif doktyp == "Artikel":
            nr = artikelnr
        else:
            nr = None  # Anlagen etc. ignorieren für fallback_end

        if nr:
            law["numbers"].append({"typ": doktyp, "nr": nr})

    if first_gnr is not None:
        print(f"[DEBUG] Seite {page}: erste gesetzesnummer={first_gnr}, jetzt {len(laws)} Gesetze")


# -------------------- Hauptsammel-Logik mit Resume -------------------- #

def collect_laws(max_pages: int | None = None) -> Dict[str, Any]:
    """
    Holt alle Seiten (bis max_pages) und aggregiert nach gesetzesnummer.

    Mit Resume:
      - falls STATE_FILE existiert, ab last_page+1 weitermachen
      - nach jeder verarbeiteten Seite aktuellen Stand speichern
    """
    # Bisherigen Stand laden (falls vorhanden)
    laws, last_page = load_state()
    page_size = 100

    # Seite 1 holen, um total_hits/total_pages zu bestimmen
    first_results = fetch_page(1, page_size)
    if first_results is None:
        print("[FATAL] Seite 1 konnte nicht geladen werden – breche ab.")
        return laws

    hits = first_results.get("Hits")
    if not hits:
        print("[ERROR] Keine 'Hits' in erster Seite – total_pages=1 angenommen.")
        total_pages = 1
    else:
        try:
            total_hits = int(hits["#text"])
            page_size_real = int(hits["@pageSize"])
            total_pages = math.ceil(total_hits / page_size_real)
            print(f"[INFO] total_hits={total_hits}, page_size={page_size_real}, total_pages={total_pages}")
        except Exception as e:
            print(f"[ERROR] Konnte Paging-Infos aus 'Hits' nicht lesen: {e}")
            total_pages = 1

    # Max_Pages berücksichtigen
    if max_pages is not None:
        effective_pages = min(total_pages, max_pages)
        print(f"[INFO] Begrenze auf max_pages={max_pages} -> effective_pages={effective_pages}.")
    else:
        effective_pages = total_pages
        print(f"[INFO] Kein max_pages-Limit – effective_pages={effective_pages}.")

    # Wenn wir noch gar nichts verarbeitet haben, Seite 1 jetzt verarbeiten
    if last_page == 0:
        print("[INFO] Verarbeite Seite 1 (erstmaliger Lauf).")
        handle_results(first_results, laws, page=1)
        last_page = 1
        save_state(laws, last_page)
    else:
        print(f"[INFO] Überspringe bereits verarbeitete Seiten bis {last_page}.")

    # Startseite für die Schleife
    start_page = max(2, last_page + 1)

    # restliche Seiten
    for page in range(start_page, effective_pages + 1):
        print(f"[INFO] Lade Seite {page}/{effective_pages}")
        results = fetch_page(page, page_size)
        if results is None:
            print(f"[WARN] Seite {page} konnte nicht geladen werden – breche hier ab.")
            break
        handle_results(results, laws, page)
        last_page = page
        save_state(laws, last_page)

    print(f"[INFO] collect_laws: {len(laws)} verschiedene gesetzesnummern aggregiert.")
    return laws


# -------------------- Summary bauen -------------------- #

def build_summary(laws: Dict[str, Any]):
    """
    Baut die kompakten Records für ris_gesetze.json:

    {
        "kurz": ...,
        "titel": ...,
        "gesetzesnummer": ...,
        "fallback_end": <int|None>,
        "unit_type": "paragraf"|"artikel"|None,
        "inkraft": "...",
        "ausserkraft": null,
        "typ": "BG" | "V" | ...
    }
    """
    out = []
    for gesetzesnummer, law in laws.items():
        numbers = law.get("numbers") or []

        if not numbers:
            fallback_end = None
            unit_type = None
        else:
            counts = Counter(n["typ"] for n in numbers)
            if counts.get("Paragraph", 0) >= counts.get("Artikel", 0):
                unit_type = "paragraf"
                raw_numbers = [n["nr"] for n in numbers if n["typ"] == "Paragraph"]
            else:
                unit_type = "artikel"
                raw_numbers = [n["nr"] for n in numbers if n["typ"] == "Artikel"]

            nums = []
            for s in raw_numbers:
                m = re.match(r"(\d+)", s)
                if m:
                    nums.append(int(m.group(1)))
            fallback_end = max(nums) if nums else None

        out.append(
            {
                "kurz": law.get("kurz"),
                "titel": law.get("titel"),
                "gesetzesnummer": gesetzesnummer,
                "fallback_end": fallback_end,
                "unit_type": unit_type,
                "inkraft": law.get("inkraft"),
                "ausserkraft": law.get("ausserkraft"),
                "typ": law.get("typ"),
            }
        )

    print(f"[INFO] build_summary: {len(out)} Records erzeugt.")
    return out


# -------------------- Main -------------------- #

if __name__ == "__main__":
    laws = collect_laws(max_pages=MAX_PAGES)
    if not laws:
        print("[FATAL] Keine Gesetze gesammelt – keine Ausgabe geschrieben.")
    else:
        summary = build_summary(laws)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"[OK] {OUTPUT_FILE} mit {len(summary)} Einträgen geschrieben.")
        print("[INFO] Wenn du mit dem Ergebnis zufrieden bist, kannst du STATE_FILE löschen,")
        print("       um beim nächsten Mal wieder von vorne zu beginnen.")
