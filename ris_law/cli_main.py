# ris_law/cli_main.py
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .exceptions import RisLawError, RisParseError
from .ris_api import ENDPOINTS, RisApiClient

logger = logging.getLogger(__name__)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(args)

    try:
        params = _parse_key_value(args.param)
    except ValueError as exc:
        logger.error(str(exc))
        return 2

    body = None
    form = None

    if getattr(args, "body", None) and getattr(args, "body_file", None):
        logger.error("--body und --body-file können nicht kombiniert werden")
        return 2

    if getattr(args, "form", None) and (getattr(args, "body", None) or getattr(args, "body_file", None)):
        logger.error("--form kann nicht mit JSON-Body kombiniert werden")
        return 2

    if getattr(args, "body", None):
        try:
            body = json.loads(args.body)
        except json.JSONDecodeError as exc:
            logger.error("Ungültiges JSON in --body: %s", exc)
            return 2

    if getattr(args, "body_file", None):
        try:
            body_text = _read_body_file(args.body_file)
            body = json.loads(body_text)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Konnte --body-file nicht lesen/parse: %s", exc)
            return 2

    if getattr(args, "form", None):
        try:
            form = _parse_key_value(args.form)
        except ValueError as exc:
            logger.error(str(exc))
            return 2

    client = RisApiClient(base_url=args.base_url, timeout=args.timeout)

    try:
        if args.method == "get":
            result = client.get(args.endpoint_path, params=params or None, raw=args.raw)
        else:
            result = client.post(
                args.endpoint_path,
                params=params or None,
                body=body,
                form=form,
                raw=args.raw,
            )
    except RisParseError as exc:
        logger.error("Antwort konnte nicht als JSON gelesen werden: %s", exc)
        return 1
    except RisLawError as exc:
        logger.error("API-Fehler: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.error("Unerwarteter Fehler: %s", exc)
        return 1

    _write_output(result, json_output=args.json or args.plain, raw=args.raw)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RIS API CLI (v2.6)")
    parser.add_argument(
        "--base-url",
        default=os.getenv("RIS_API_BASE_URL", "https://data.bka.gv.at/ris/api/v2.6"),
        help="Basis-URL der RIS API (ENV: RIS_API_BASE_URL)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.getenv("RIS_API_TIMEOUT", "30")),
        help="HTTP-Timeout in Sekunden (ENV: RIS_API_TIMEOUT)",
    )
    parser.add_argument("--json", action="store_true", help="kompaktes JSON ausgeben")
    parser.add_argument("--plain", action="store_true", help="stabile (nicht eingerückte) Ausgabe")
    parser.add_argument("--raw", action="store_true", help="Antwort als Rohtext ausgeben")

    log_group = parser.add_mutually_exclusive_group()
    log_group.add_argument("-v", "--verbose", action="store_true", help="mehr Logausgaben")
    log_group.add_argument("-q", "--quiet", action="store_true", help="weniger Logausgaben")

    _add_version_flag(parser)

    subparsers = parser.add_subparsers(dest="endpoint", required=True)
    for endpoint, config in ENDPOINTS.items():
        ep_parser = subparsers.add_parser(endpoint, help=f"{endpoint} Endpoint")
        ep_parser.set_defaults(endpoint_path=config["path"])
        method_parsers = ep_parser.add_subparsers(dest="method", required=True)
        methods = config["methods"]

        if "GET" in methods:
            get_parser = method_parsers.add_parser("get", help=f"GET {endpoint}")
            _add_param_flags(get_parser)

        if "POST" in methods:
            post_parser = method_parsers.add_parser("post", help=f"POST {endpoint}")
            _add_param_flags(post_parser)
            post_parser.add_argument("--body", help="JSON-Body als String")
            post_parser.add_argument("--body-file", help="JSON-Body aus Datei (oder '-' für stdin)")
            post_parser.add_argument("--form", action="append", default=[], help="Form-Parameter KEY=VALUE")

    return parser


def _add_param_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--param", action="append", default=[], help="Query-Parameter KEY=VALUE")


def _add_version_flag(parser: argparse.ArgumentParser) -> None:
    try:
        from importlib.metadata import version

        parser.add_argument("--version", action="version", version=version("ris-law"))
    except Exception:  # noqa: BLE001
        parser.add_argument("--version", action="version", version="unknown")


def _configure_logging(args: argparse.Namespace) -> None:
    if args.verbose:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.WARNING
    else:
        level = logging.INFO
    logging.basicConfig(level=level)


def _parse_key_value(items: list[str]) -> dict[str, str | list[str]]:
    params: dict[str, str | list[str]] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Ungültiges KEY=VALUE Paar: {item}")
        key, value = item.split("=", 1)
        if key in params:
            existing = params[key]
            if isinstance(existing, list):
                existing.append(value)
            else:
                params[key] = [existing, value]
        else:
            params[key] = value
    return params


def _read_body_file(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _write_output(data: object, *, json_output: bool, raw: bool) -> None:
    if raw:
        if isinstance(data, str):
            sys.stdout.write(data)
        else:
            sys.stdout.write(str(data))
        if not data or str(data).endswith("\n"):
            return
        sys.stdout.write("\n")
        return

    if json_output or not sys.stdout.isatty():
        output = json.dumps(data, ensure_ascii=False)
    else:
        output = json.dumps(data, ensure_ascii=False, indent=2)
    print(output)
