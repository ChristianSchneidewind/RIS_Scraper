from __future__ import annotations

import logging
import time
from typing import Optional

import requests

from .config import REQUEST_TIMEOUT, USER_AGENT
from .exceptions import RisFetchError

logger = logging.getLogger(__name__)


class HttpClient:
    def __init__(
        self,
        *,
        user_agent: str = USER_AGENT,
        timeout: int = REQUEST_TIMEOUT,
        retries: int = 3,
        backoff: float = 1.5,
    ) -> None:
        self.session = requests.Session()
        self.headers = {"User-Agent": user_agent}
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    def get(
        self,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict] = None,
        timeout: Optional[int] = None,
        allow_redirects: bool = True,
        min_content_length: Optional[int] = None,
    ) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                merged_headers = dict(self.headers)
                if headers:
                    merged_headers.update(headers)
                response = self.session.get(
                    url,
                    headers=merged_headers,
                    params=params,
                    timeout=timeout or self.timeout,
                    allow_redirects=allow_redirects,
                )
                response.raise_for_status()
                if min_content_length is not None:
                    if not response.text or len(response.text) < min_content_length:
                        raise ValueError("Response body too short")
                return response
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "HTTP GET failed (%s/%s) for %s: %s",
                    attempt,
                    self.retries,
                    url,
                    exc,
                )
                if attempt < self.retries:
                    time.sleep(self.backoff * attempt)
        if last_error:
            raise RisFetchError(str(last_error)) from last_error
        raise RisFetchError("HTTP request failed without an exception")

    def post(
        self,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        data: Optional[bytes] = None,
        timeout: Optional[int] = None,
    ) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                merged_headers = dict(self.headers)
                if headers:
                    merged_headers.update(headers)
                response = self.session.post(
                    url,
                    headers=merged_headers,
                    data=data,
                    timeout=timeout or self.timeout,
                )
                response.raise_for_status()
                return response
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "HTTP POST failed (%s/%s) for %s: %s",
                    attempt,
                    self.retries,
                    url,
                    exc,
                )
                if attempt < self.retries:
                    time.sleep(self.backoff * attempt)
        if last_error:
            raise RisFetchError(str(last_error)) from last_error
        raise RisFetchError("HTTP request failed without an exception")


_default_client = HttpClient()


def get_default_http_client() -> HttpClient:
    return _default_client
