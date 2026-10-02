"""Send scholarship results through Gmail SMTP."""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from html import escape
from typing import Any


def _get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _status(item: dict[str, Any]) -> str:
    return str(item.get("match_status", "")).strip().lower()


def _score(item: dict[str, Any]) -> float:
    try:
        return float(item.get("match_score", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _is_relevant(item: dict[str, Any]) -> bool:
    status = _status(item)
    score = _score(item)

    if status == "good_match":
        return True

    if status == "needs_manual_check" and score >= 30:
        return True

    return False


def _clean(value: Any, default: str = "Not specified") -> str:
    if value is None:
        return default

    if isinstance(value, list):
        values = [str(v).strip() for v in value if str(v).strip()]
        return ", ".join(values) if values else default

    text = str(value).strip()
    return text or default


def _scholarship_card(item: dict[str, Any]) -> str:
    title = escape(_clean(item.get("title"), "Scholarship"))
    url = str(item.get("url", "")).strip()
    destination = escape(_clean(item.get("destination")))
    degree = escape(_clean(item.get("degree_requirements")))
    field = escape(_clean(item.get("field_requirements")))
    deadline = escape(_clean(item.get("deadlines")))
    score = _score(item)
    status = escape(_clean(item.get("match_status")))

    if url:
        link = (
            f'<a href="{escape(url)}" '
            f'style="font-size:16px;font-weight:700;">'
            f"{title}</a>"
        )
    else:
        link = f"<strong>{title}</strong>"

    return f"""
    <div style="
        border:1px solid #ddd;
        border-radius:10px;
        padding:16px;
        margin:0 0 16px 0;
        background:#ffffff;
    ">
        {link}

        <p style="margin:10px 0 6px;">
            <strong>Match score:</strong> {score:g}/100
            &nbsp; | &nbsp;
            <strong>Status:</strong> {status}
        </p>

        <p style="margin:6px 0;">
            <strong>Destination:</strong> {destination}
        </p>

        <p style="margin:6px 0;">
            <strong>Degree:</strong> {degree}
        </p>

        <p style="margin:6px 0;">
            <strong>Field:</strong> {field}
        </p>

        <p style="margin:6px 0;">
            <strong>Deadline:</strong> {deadline}
        </p>
    </div>
    """


def build_email_html(items: list[dict[str, Any]]) -> str:
    relevant = [item for item in items if _is_relevant(item)]
    relevant.sort(key=_score, reverse=True)

    if not relevant:
        return """
        <html>
        <body style="font-family:Arial,sans-serif;background:#f6f7f9;padding:24px;">
            <div style="
                max-width:760px;
                margin:auto;
                background:white;
                padding:24px;
                border-radius:12px;
            ">
                <h1>🎓 Master Scholarship Hunter</h1>
                <p>No scholarships met the current matching threshold today.</p>
                <p>
                    The Actor completed successfully and checked the available
                    scholarship records.
                </p>
            </div>
        </body>
        </html>
        """

    cards = "\n".join(
        _scholarship_card(item)
        for item in relevant
    )

    return f"""
    <html>
    <body style="
        font-family:Arial,Helvetica,sans-serif;
        background:#f6f7f9;
        padding:24px;
        color:#222;
    ">
        <div style="
            max-width:760px;
            margin:auto;
            background:#ffffff;
            padding:24px;
            border-radius:12px;
        ">
            <h1 style="margin-top:0;">
                🎓 Master Scholarship Hunter
            </h1>

            <p>
                Today's scholarship hunt found
                <strong>{len(relevant)}</strong>
                relevant scholarship(s).
            </p>

            {cards}

            <hr style="
                border:none;
                border-top:1px solid #ddd;
                margin:24px 0;
            ">

            <p style="font-size:13px;color:#666;">
                This email was generated automatically by
                Master Scholarship Hunter.
            </p>
        </div>
    </body>
    </html>
    """


async def send_scholarship_email(
    items: list[dict[str, Any]],
) -> None:
    gmail_address = _get_required_env("GMAIL_ADDRESS")
    app_password = _get_required_env("GMAIL_APP_PASSWORD")
    to_address = _get_required_env("EMAIL_TO")

    # Google may display the app password with spaces.
    # Remove them automatically.
    app_password = "".join(app_password.split())

    relevant = [
        item for item in items
        if _is_relevant(item)
    ]

    subject = (
        f"🎓 Scholarship Hunter — "
        f"{len(relevant)} matching scholarship(s)"
    )

    message = EmailMessage()
    message["From"] = gmail_address
    message["To"] = to_address
    message["Subject"] = subject

    html = build_email_html(items)

    message.set_content(
        "Your scholarship results are available in the HTML version "
        "of this email."
    )
    message.add_alternative(html, subtype="html")

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
            context=context,
            timeout=30,
        ) as server:
            server.login(
                gmail_address,
                app_password,
            )
            server.send_message(message)

        print(
            f"Scholarship email sent successfully to {to_address}. "
            f"Matching scholarships: {len(relevant)}"
        )

    except smtplib.SMTPAuthenticationError as error:
        raise RuntimeError(
            "Gmail authentication failed. Check GMAIL_ADDRESS "
            "and GMAIL_APP_PASSWORD."
        ) from error

    except smtplib.SMTPException as error:
        raise RuntimeError(
            f"Gmail SMTP error: {error}"
        ) from error
