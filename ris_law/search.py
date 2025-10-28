from typing import List, Dict
from lxml import etree
from .config import NS_SVC
from .soap_client import post_soap, soap_envelope, result_embedded_xml

def search_page(gesetzesnummer: str, page: int = 1, page_size: int = 20) -> str:
    """
    Eine Ergebnisseite suchen; Rückgabe: embedded XML (String).
    """
    query = (
        "<Suche>"
        "  <Bundesrecht>"
        "    <BrKons>"
        f"      <Gesetzesnummer>{gesetzesnummer}</Gesetzesnummer>"
        "    </BrKons>"
        "  </Bundesrecht>"
        "</Suche>"
    )
    body = (
        f'<SearchDocuments xmlns="{NS_SVC}">'
        f'  <query xmlns="{NS_SVC}">{query}</query>'
        f'  <pageNumber>{page}</pageNumber>'
        f'  <pageSize>{page_size}</pageSize>'
        f'</SearchDocuments>'
    )
    root = post_soap(f"{NS_SVC}/SearchDocuments", soap_envelope(body))
    try:
        with open("last_search_envelope.xml", "w", encoding="utf-8") as dbg:
            dbg.write(etree.tostring(root, encoding="unicode"))
    except Exception:
        pass
    res = root.find(f".//{{{NS_SVC}}}SearchDocumentsResult")
    embedded = result_embedded_xml(res)
    try:
        with open("last_search_embedded.xml", "w", encoding="utf-8") as f:
            f.write(embedded)
    except Exception:
        pass
    return embedded

def extract_docrefs(embedded_xml: str) -> List[Dict[str, str]]:
    """
    Liefert [{'id': 'NOR…', 'url': 'https://www.ris.bka.gv.at/Dokumente/Bundesnormen/NOR/NOR.html'}].
    Wir bauen IMMER die kanonische HTML-URL, nicht ELI.
    """
    if not embedded_xml:
        return []
    try:
        root = etree.fromstring(embedded_xml.encode("utf-8"))
    except Exception as e:
        print("[ERR] embedded_xml nicht parsebar:", e)
        return []

    refs: List[Dict[str, str]] = []
    for ref in root.xpath("//*[local-name()='OgdDocumentReference']"):
        el_id = ref.xpath(".//*[local-name()='Technisch']/*[local-name()='ID']")
        doc_id = (el_id[0].text or "").strip() if el_id and el_id[0].text else ""
        if not doc_id:
            any_id = ref.xpath(".//*[local-name()='ID']")
            doc_id = (any_id[0].text or "").strip() if any_id and any_id[0].text else ""
        if not doc_id or not doc_id.startswith("NOR"):
            continue
        url = f"https://www.ris.bka.gv.at/Dokumente/Bundesnormen/{doc_id}/{doc_id}.html"
        refs.append({"id": doc_id, "url": url})
    return refs