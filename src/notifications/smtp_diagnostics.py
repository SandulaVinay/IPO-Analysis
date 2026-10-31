"""Safe SMTP authentication probe that never submits an email message."""

from __future__ import annotations

import smtplib
import ssl
from typing import Any


def authenticate_smtp(
    host: str,
    preferred_port: int,
    username: str,
    password: str,
) -> dict[str, Any]:
    """Verify TLS, SMTP AUTH and NOOP; never call sendmail or submit content."""
    host = (host or "").strip()
    username = (username or "").strip()
    password = "".join((password or "").split())

    if not host or not username or not password:
        return {
            "success": False,
            "host": host or None,
            "port": None,
            "stage": "configuration",
            "error": "SMTP_HOST, SMTP_USER and SMTP_PASSWORD are required.",
        }

    ports = [int(preferred_port)]
    if host.lower() in {"smtp.gmail.com", "smtp.googlemail.com"}:
        alternate = 465 if int(preferred_port) != 465 else 587
        if alternate not in ports:
            ports.append(alternate)

    last_error: tuple[int, str, Exception] | None = None
    for port in ports:
        stage = "connect"
        try:
            if port == 465:
                with smtplib.SMTP_SSL(
                    host,
                    port,
                    timeout=30,
                    context=ssl.create_default_context(),
                ) as server:
                    stage = "ehlo"
                    server.ehlo()
                    stage = "login"
                    server.login(username, password)
                    stage = "noop"
                    code, _response = server.noop()
            else:
                with smtplib.SMTP(host, port, timeout=30) as server:
                    stage = "ehlo"
                    server.ehlo()
                    stage = "starttls"
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                    stage = "login"
                    server.login(username, password)
                    stage = "noop"
                    code, _response = server.noop()

            if code != 250:
                raise smtplib.SMTPResponseException(code, b"SMTP NOOP was not accepted.")

            return {
                "success": True,
                "host": host,
                "port": port,
                "stage": "authenticated",
                "error": None,
            }
        except Exception as exc:
            last_error = (port, stage, exc)

    if last_error is None:
        return {
            "success": False,
            "host": host,
            "port": None,
            "stage": "connect",
            "error": "No SMTP connection attempt was made.",
        }

    port, stage, exc = last_error
    smtp_code = getattr(exc, "smtp_code", None)
    detail = f"SMTP {type(exc).__name__} during {stage} on port {port}"
    if smtp_code is not None:
        detail += f" (server code {smtp_code})"
    return {
        "success": False,
        "host": host,
        "port": port,
        "stage": stage,
        "error": detail,
    }
