"""Send only strictly matched scholarship results through Gmail SMTP."""

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


def _score(item: dict[str, Any]) -> float:
    try:
        return float(item.get("match_score", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _is_relevant(item: dict[str, Any]) -> bool:
    """
    Strict email filter.

    A scholarship reaches the daily email only when the strict matcher
    has explicitly marked it for inclusion and verified full funding.
    """
    return (
        str(item.get("recommendation", "")).strip().lower() == "include"
        and str(item.get("match_status", "")).strip().lower() == "strong_match"
        and str(item.get("funding_status", "")).strip().lower() == "verified_full"
    )


def _clean(value: Any, default: str = "Not specified") -> str:
    if value is None:
        return default

    if isinstance(value, list):
        values = [str(v).strip() for v in value if str(v).strip()]
        return ", ".join(values) if values else default

    if isinstance(value, dict):
        if "raw" in value:
            return _clean(value.get("raw"), default)
        return ", ".join(
            f"{k}: {v}" for k, v in value.items()
            if str(v).strip()
        ) or default

    text = str(value).strip()
    return text or default


def _reasons(item: dict[str, Any]) -> str:
    values = item.get("reasons", [])
    if not isinstance(values, list):
        return _clean(values)

    good = [
        str(v).strip()
        for v in values
        if str(v).strip()
    ]

    return "<br>".join(
        f"✓ {escape(value)}"
        for value in good[:8]
    ) or "Strict profile checks passed."


def _scholarship_card(item: dict[str, Any]) -> str:
    title = escape(_clean(item.get("title"), "Scholarship"))
    url = str(item.get("url", "")).strip()

    destination = escape(_clean(item.get("destination")))
    degree = escape(_clean(item.get("degree_requirements")))
    field = escape(_clean(item.get("field_requirements")))
    deadline = escape(_clean(item.get("deadlines")))
    funding = escape(_clean(item.get("funding")))
    reasons = _reasons(item)

    if url:
        link = (
            f'<a href="{escape(url)}" '
            f'style="font-size:17px;font-weight:700;color:#176b5f;">'
            f"{title}</a>"
        )
    else:
        link = f"<strong>{title}</strong>"

    return f"""
    <div style="
        border:1px solid #d9e2df;
        border-radius:12px;
        padding:18px;
        margin:0 0 18px 0;
        background:#ffffff;
    ">
        {link}

        <p style="margin:10px 0 6px;">
            <strong>Match:</strong> 100/100
            &nbsp; | &nbsp;
            <strong>Verified:</strong> Fully funded
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
            <strong>Funding:</strong> {funding}
        </p>

        <p style="margin:6px 0;">
            <strong>Deadline:</strong> {deadline}
        </p>

        <div style="
            margin-top:12px;
            padding:12px;
            background:#f4f8f7;
            border-radius:8px;
            line-height:1.6;
        ">
            <strong>Why it matched:</strong><br>
            {reasons}
        </div>
    </div>
    """


def build_email_html(items: list[dict[str, Any]]) -> str:
    relevant = [
        item for item in items
        if _is_relevant(item)
    ]
    relevant.sort(key=_score, reverse=True)

    if not relevant:
        return """
        <html>
        <body style="
            font-family:Arial,sans-serif;
            background:#f6f7f9;
            padding:24px;
            color:#222;
        ">
            <div style="
                max-width:760px;
                margin:auto;
                background:white;
                padding:24px;
                border-radius:12px;
            ">
                <h1>🎓 Master Scholarship Hunter</h1>

                <h2>No fully funded Master's matches today.</h2>

                <p>
                    Today's hunt completed successfully, but no scholarship
                    passed all strict profile requirements.
                </p>

                <p>
                    Required profile:
                    <strong>Beninese applicant · Master's only ·
                    fully funded · Computer Science / IT / AI-related ·
                    target country · eligible to apply from abroad.</strong>
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

            <p style="font-size:16px;">
                Today's hunt found
                <strong>{len(relevant)}</strong>
                <strong>fully funded Master's scholarship(s)</strong>
                that passed all strict profile checks.
            </p>

            <p style="
                background:#eef7f4;
                padding:12px;
                border-radius:8px;
            ">
                <strong>Your target:</strong>
                Benin → Master's → Computer Science / IT / AI →
                fully funded → target countries → application from abroad.
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
                Scholarships are filtered using the strict-v2 profile rules.
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

    app_password = "".join(app_password.split())

    relevant = [
        item for item in items
        if _is_relevant(item)
    ]

    subject = (
        f"🎓 Scholarship Hunter — "
        f"{len(relevant)} fully funded Master's match"
        f"{'' if len(relevant) == 1 else 'es'}"
    )

    message = EmailMessage()
    message["From"] = gmail_address
    message["To"] = to_address
    message["Subject"] = subject

    html = build_email_html(items)

    message.set_content(
        "Your strict scholarship results are available in the HTML version "
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
            f"Strict fully funded matches: {len(relevant)}"
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
