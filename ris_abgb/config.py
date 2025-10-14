# Zentrale Settings/Konstanten

BASE_URL = "https://data.bka.gv.at/ris/ogd/v2.6/ogdrisservice.asmx"
NS_SOAP  = "http://schemas.xmlsoap.org/soap/envelope/"
NS_SVC   = "http://ris.bka.gv.at/ogd/V2_6"

HEADERS_SOAP = {"Content-Type": "text/xml; charset=utf-8"}
USER_AGENT   = "RIS-ABGB-Scraper/1.0 (+github:example)"

# ABGB (kann via CLI überschrieben werden, hier nur Default)
GESETZESNUMMER_ABGB = "10001622"
