import time
from urllib import parse as urlparse
import requests
from bs4 import BeautifulSoup
from config import BASE


def _par_url(gesetzesnummer: str, par: str) -> str:
    return (
        f"{BASE}/NormDokument.wxe"
        f"?Abfrage=Bundesnormen&Gesetzesnummer={gesetzesnummer}&Paragraf={urlparse.quote(par)}"
    )


def fetch_abgb_index_docrefs(
    gesetzesnummer: str = "10001622",
    start_par: int = 1,
    max_par: int = 1502,
    pause: float = 0.25,
    consecutive_miss_limit: int = 150,
):
    """
    Holt Dokument-Referenzen über direkte Paragraph-Abfrage (Fallback-Modus).
    """
    docrefs = []
    consecutive_misses = 0

    for n in range(start_par, max_par + 1):
        url = _par_url(gesetzesnummer, str(n))
        print(f"Prüfe § {n} …")

        resp = requests.get(url)
        if resp.status_code != 200 or "RIS" not in resp.text:
            consecutive_misses += 1
            if consecutive_misses > consecutive_miss_limit:
                print("Abbruch wegen zu vieler fehlender Treffer.")
                break
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        heading = soup.find("h1")
        heading_text = heading.text.strip() if heading else None

        docrefs.append(
            type("DocRef", (), {
                "url": url,
                "heading": heading_text,
                "paragraph_id": f"§ {n}",
                "nor": None,
            })()
        )

        consecutive_misses = 0
        time.sleep(pause)

    return docrefs
