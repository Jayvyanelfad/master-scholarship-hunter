"""Send strict scholarship results through Gmail SMTP."""

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
        raise RuntimeError(
            f"Missing required environment variable: {name}"
        )

    return value


def _is_included(item: dict[str, Any]) -> bool:
    """
    Only send scholarships that passed the strict profile matcher.
    """

    recommendation = str(
        item.get("recommendation", "")
    ).strip().lower()

    status = str(
        item.get("match_status", "")
    ).strip().lower()

    return (
        recommendation == "include"
        and status == "strong_match"
    )


def _clean(
    value: Any,
    default: str = "Not specified",
) -> str:

    if value is None:
        return default

    if isinstance(value, list):
        values = [
            str(v).strip()
            for v in value
            if str(v).strip()
        ]

        return ", ".join(values) if values else default

    text = str(value).strip()

    return text or default


def _scholarship_card(
    item: dict[str, Any],
) -> str:

    title = escape(
        _clean(
            item.get("title"),
            "Scholarship",
        )
    )

    url = str(
        item.get("url", "")
    ).strip()

    destination = escape(
        _clean(item.get("destination"))
    )

    degree = escape(
        _clean(item.get("degree_requirements"))
    )

    field = escape(
        _clean(item.get("field_requirements"))
    )

    nationality = escape(
        _clean(item.get("nationality_requirements"))
    )

    funding = escape(
        _clean(item.get("funding"))
    )

    deadline = escape(
        _clean(item.get("deadlines"))
    )

    reasons = item.get("reasons", [])

    if isinstance(reasons, list):
        reason_items = [
            str(reason).strip()
            for reason in reasons
            if str(reason).strip()
        ]
    else:
        reason_items = [str(reasons).strip()]

    reason_html = "".join(
        f"<li>{escape(reason)}</li>"
        for reason in reason_items
    )

    if not reason_html:
        reason_html = (
            "<li>Passed all strict profile requirements.</li>"
        )

    if url:
        link = (
            f'<a href="{escape(url)}" '
            f'style="font-size:17px;'
            f'font-weight:700;">'
            f"{title}</a>"
        )
    else:
        link = f"<strong>{title}</strong>"

    return f"""
    <div style="
        border:1px solid #d9dee5;
        border-radius:12px;
        padding:18px;
        margin:0 0 18px 0;
        background:#ffffff;
    ">

        {link}

        <p style="margin:12px 0 6px;">
            <strong>Destination:</strong>
            {destination}
        </p>

        <p style="margin:6px 0;">
            <strong>Degree:</strong>
            {degree}
        </p>

        <p style="margin:6px 0;">
            <strong>Field:</strong>
            {field}
        </p>

        <p style="margin:6px 0;">
            <strong>Nationality:</strong>
            {nationality}
        </p>

        <p style="margin:6px 0;">
            <strong>Funding:</strong>
            {funding}
        </p>

        <p style="margin:6px 0;">
            <strong>Deadline:</strong>
            {deadline}
        </p>

        <div style="
            margin-top:14px;
            padding:12px;
            background:#f6f8fa;
            border-radius:8px;
        ">
            <strong>Why it matched:</strong>
            <ul style="margin:8px 0 0 20px;">
                {reason_html}
            </ul>
        </div>

        <p style="
            margin:14px 0 0;
            font-size:12px;
            color:#777;
        ">
            Strict profile rule:
            Master's only + full funding only +
            CS/IT/AI + Benin eligible +
            target country + apply from abroad
        </p>

    </div>
    """


def build_email_html(
    items: list[dict[str, Any]],
    diagnostics: dict[str, int] | None = None,
    source_health: dict[str, Any] | None = None,
) -> str:

    included = [
        item
        for item in items
        if _is_included(item)
    ]

    if not included:
        diagnostics = diagnostics or {}
        diagnostic_rows = "".join(
            f"<li>{escape(key.replace('_', ' ').title())}: {value}</li>"
            for key, value in diagnostics.items()
            if not str(key).startswith("reason_")
        )
        reason_labels = {
            "reason_non_masters": "Non-Master's level",
            "reason_not_fully_funded": "Not fully funded",
            "reason_field_mismatch": "Field mismatch",
            "reason_nationality_mismatch": "Nationality mismatch",
            "reason_destination_mismatch": "Destination mismatch",
            "reason_abroad_restriction": "Abroad/residence restriction",
            "reason_expired": "Expired",
            "reason_insufficient_evidence": "Insufficient evidence",
            "reason_possible_matches": "Possible (needs more evidence)",
        }
        reason_rows = "".join(
            f"<li>{escape(label)}: {diagnostics.get(key, 0)}</li>"
            for key, label in reason_labels.items()
            if diagnostics.get(key, 0)
        )
        if reason_rows:
            reason_rows = (
                "<h3>Rejection reasons</h3>"
                "<ul>" + reason_rows + "</ul>"
            )
        source_rows = ""
        if source_health:
            entries = "".join(
                f"<li>{escape(str(entry.get('display_name', source_id)))}: "
                f"{entry.get('discovered', 0)} discovered, "
                f"{entry.get('official_fetched', 0)} official checked, "
                f"{entry.get('verified', 0)} verified strong, "
                f"{entry.get('errors', 0)} errors</li>"
                for source_id, entry in source_health.items()
                if isinstance(entry, dict)
            )
            if entries:
                source_rows = (
                    "<h3>Sources checked</h3>"
                    "<ul>" + entries + "</ul>"
                )
        return """
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
                background:white;
                padding:24px;
                border-radius:12px;
            ">

                <h1 style="margin-top:0;">
                    🎓 Master Scholarship Hunter
                </h1>

                <p>
                    No verified strong matches this run.
                </p>

                <p style="color:#666;">
                    These diagnostics distinguish a lack of matches
                    from incomplete source evidence.
                </p>

                <ul>""" + diagnostic_rows + """</ul>

                """ + source_rows + reason_rows + """

            </div>

        </body>
        </html>
        """

    cards = "\n".join(
        _scholarship_card(item)
        for item in included
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
                Today's hunt found
                <strong>{len(included)}</strong>
                scholarship(s) that passed your
                <strong>strict profile requirements</strong>.
            </p>

            <p style="
                padding:12px;
                background:#f6f8fa;
                border-radius:8px;
                font-size:14px;
            ">
                <strong>Your profile:</strong><br>
                🇧🇯 Benin &nbsp;|&nbsp;
                🎓 Master's only &nbsp;|&nbsp;
                💰 Full funding only &nbsp;|&nbsp;
                💻 CS / IT / AI &nbsp;|&nbsp;
                🌍 Target countries only
            </p>

            {cards}

            <hr style="
                border:none;
                border-top:1px solid #ddd;
                margin:24px 0;
            ">

            <p style="
                font-size:13px;
                color:#666;
            ">
                This email was generated automatically by
                Master Scholarship Hunter.
            </p>

        </div>

    </body>

    </html>
    """


async def send_scholarship_email(
    items: list[dict[str, Any]],
    diagnostics: dict[str, int] | None = None,
    source_health: dict[str, Any] | None = None,
) -> None:
    # Keep the rendering helpers usable in isolated unit tests; importing the
    # SDK here still ensures runtime logs are censored by Actor.log.
    from apify import Actor


    gmail_address = _get_required_env(
        "GMAIL_ADDRESS"
    )

    app_password = _get_required_env(
        "GMAIL_APP_PASSWORD"
    )

    to_address = _get_required_env(
        "EMAIL_TO"
    )

    app_password = "".join(
        app_password.split()
    )

    included = [
        item
        for item in items
        if _is_included(item)
    ]

    subject = (
        "🎓 Scholarship Hunter — "
        f"{len(included)} strict match"
        f"{'es' if len(included) != 1 else ''}"
    )

    message = EmailMessage()

    message["From"] = gmail_address
    message["To"] = to_address
    message["Subject"] = subject

    html = build_email_html(items, diagnostics, source_health)

    message.set_content(
        "Your strict scholarship results are "
        "available in the HTML version of this email."
    )

    message.add_alternative(
        html,
        subtype="html",
    )

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

            server.send_message(
                message
            )

        Actor.log.info(
            "Scholarship email sent successfully. "
            f"Strict matches: {len(included)}"
        )

    except smtplib.SMTPAuthenticationError as error:

        raise RuntimeError(
            "Gmail authentication failed. "
            "Check GMAIL_ADDRESS and "
            "GMAIL_APP_PASSWORD."
        ) from error

    except smtplib.SMTPException as error:

        raise RuntimeError(
            f"Gmail SMTP error: {error}"
        ) from error
