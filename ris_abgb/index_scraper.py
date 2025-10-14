# ris_abgb/index_scraper.py
import re
import time
import string
from typing import List, Dict, Set, Optional
import urllib.parse as urlparse

import requests
from .config import USER_AGENT

BASE = "https://www.ris.bka.gv.at"
GESETZESNUMMER = "10001622"  # ABGB

# NOR im HTML finden
RX_NOR = re.compile(r"\b(NOR\d{5,})\b", re.IGNORECASE)

def _get(url: str, timeout: int = 60) -> requests.Response:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r

def _par_url(par: str) -> str:
    return (
        f"{BASE}/NormDokument.wxe"
        f"?Abfrage=Bundesnormen&Gesetzesnummer={GESETZESNUMMER}&Paragraf={urlparse.quote(par)}"
    )

def _extract_nor(html: str) -> Optional[str]:
    m = RX_NOR.search(html)
    return m.group(1) if m else None

def fetch_abgb_index_docrefs(
    max_par: int = 1502,         # obere Grenze der §§
    start_par: int = 0,          # ab welchem § starten
    pause: float = 0.25,         # Pause pro Request (s)
    consecutive_miss_limit: int = 150,  # Abbruch, wenn so viele Nummern in Folge nichts liefern
    letters: str = string.ascii_lowercase,  # a..z
) -> List[Dict[str, str]]:
    """
    Brute-Force:
      - § start_par .. max_par
      - für jede Nummer zusätzlich a..z probieren, bis die erste letter-Variante 404 liefert
      - NOR aus jeder existierenden Seite extrahieren
    Gibt [{'id':'NOR…','url':'https://…/NOR…/NOR….html'}, ...] zurück.
    """
    print(f"[Index/Probe] starte Probe: {start_par}..{max_par}")
    all_nors: Set[str] = set()
    misses = 0
    last_hit_at = start_par - 1

    for n in range(start_par, max_par + 1):
        found_any_for_n = False

        # 1) Grundnummer (z. B. '17')
        try:
            url = _par_url(str(n))
            r = _get(url)
            nor = _extract_nor(r.text)
            if nor:
                all_nors.add(nor)
                found_any_for_n = True
        except requests.HTTPError:
            pass
        except Exception:
            time.sleep(pause / 2)

        # 2) Buchstabenvarianten '17a', '17b', … bis die erste nicht existiert
        for ch in letters:
            try:
                url = _par_url(f"{n}{ch}")
                r = _get(url)
                nor_ch = _extract_nor(r.text)
                if nor_ch:
                    all_nors.add(nor_ch)
                    found_any_for_n = True
                time.sleep(pause)
            except requests.HTTPError:
                # erste nicht existente Variant → Buchstaben-Schleife abbrechen
                break
            except Exception:
                time.sleep(pause / 2)
                continue

        if found_any_for_n:
            misses = 0
            last_hit_at = n
        else:
            misses += 1

        # Fortschritt
        if n % 25 == 0:
            print(f"[Index/Probe] n={n}, NORs={len(all_nors)}, letzte Treffer-Nr={last_hit_at}, misses={misses}")

        # Abbruchheuristik: lange Lücke → Ende
        if misses >= consecutive_miss_limit and n > last_hit_at + consecutive_miss_limit:
            print(f"[Index/Probe] {consecutive_miss_limit} aufeinanderfolgende Misses – Stop bei n={n}.")
            break

        time.sleep(pause)

    if not all_nors:
        raise RuntimeError("Probe fand keine NORs – bitte prüfen, ob RIS erreichbar ist.")

    refs = [
        {"id": nor, "url": f"{BASE}/Dokumente/Bundesnormen/{nor}/{nor}.html"}
        for nor in sorted(all_nors)
    ]
    print(f"[Index/Probe] fertig: {len(refs)} NORs.")
    return refs
