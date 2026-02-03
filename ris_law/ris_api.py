from __future__ import annotations

import json
from typing import Any, Iterable
from urllib.parse import urlencode

from .exceptions import RisParseError
from .http_client import HttpClient, get_default_http_client


ENDPOINTS = {
    "bundesrecht": {"path": "Bundesrecht", "methods": {"GET", "POST"}},
    "sonstige": {"path": "Sonstige", "methods": {"GET", "POST"}},
    "landesrecht": {"path": "Landesrecht", "methods": {"GET", "POST"}},
    "bezirke": {"path": "Bezirke", "methods": {"GET", "POST"}},
    "gemeinden": {"path": "Gemeinden", "methods": {"GET", "POST"}},
    "judikatur": {"path": "Judikatur", "methods": {"GET", "POST"}},
    "history": {"path": "History", "methods": {"GET", "POST"}},
    "version": {"path": "Version", "methods": {"GET"}},
}


class RisApiClient:
    def __init__(
        self,
        *,
        base_url: str = "https://data.bka.gv.at/ris/api/v2.6",
        timeout: int = 30,
        http_client: HttpClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.http_client = http_client or get_default_http_client()

    def get(self, endpoint: str, *, params: dict[str, Any] | None = None, raw: bool = False) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.http_client.get(url, params=params, timeout=self.timeout)
        return _decode_response(response.text, raw=raw)

    def post(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any | None = None,
        form: dict[str, Any] | None = None,
        raw: bool = False,
    ) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers: dict[str, str] | None = None
        data: bytes | None = None
        if form is not None:
            data = _encode_form(form)
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
        elif body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers = {"Content-Type": "application/json"}

        response = self.http_client.post(url, headers=headers, data=data, timeout=self.timeout)
        return _decode_response(response.text, raw=raw)


def _decode_response(text: str, *, raw: bool = False) -> Any:
    if raw:
        return text
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RisParseError("Response is not valid JSON") from exc


def _encode_form(form: dict[str, Any]) -> bytes:
    return urlencode(form, doseq=True).encode("utf-8")
