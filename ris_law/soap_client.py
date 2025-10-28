import requests
from lxml import etree
from .config import BASE_URL, NS_SOAP, NS_SVC, HEADERS_SOAP, USER_AGENT

def soap_envelope(inner_xml: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        f'xmlns:soap="{NS_SOAP}"><soap:Body>{inner_xml}</soap:Body></soap:Envelope>'
    )

def post_soap(action: str, body_xml: str, timeout: int = 120) -> etree._Element:
    h = dict(HEADERS_SOAP)
    h["SOAPAction"] = action
    h["User-Agent"] = USER_AGENT
    resp = requests.post(BASE_URL, data=body_xml.encode("utf-8"), headers=h, timeout=timeout)
    # Debug-Dump
    try:
        with open("last_envelope_raw.xml", "w", encoding="utf-8") as dbg:
            dbg.write(resp.text)
    except Exception:
        pass
    resp.raise_for_status()
    return etree.fromstring(resp.content)

def result_embedded_xml(res: etree._Element) -> str:
    if res is None:
        return ""
    if len(res):
        return "".join(etree.tostring(child, encoding="unicode") for child in res)
    return (res.text or "").strip()

def version_check() -> None:
    try:
        body = f'<Version xmlns="{NS_SVC}"/>'
        post_soap(f"{NS_SVC}/Version", soap_envelope(body))
        print("[OK] Version-Call")
    except Exception as e:
        print("[WARN] Version-Call:", e)