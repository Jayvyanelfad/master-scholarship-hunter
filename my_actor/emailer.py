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


REVIEW_LIMIT = 10

_HARD_EXCLUSION_KEYS = (
    "degree_match", "field_match", "funding_status", "nationality_match",
    "destination_match", "application_from_abroad", "residence_match",
)


def _is_hard_excluded(item: dict[str, Any]) -> bool:
    if str(item.get("match_status", "")).strip().lower() == "rejected":
        return True
    if str(item.get("deadline_state", "")).strip().lower() == "expired":
        return True
    if str(item.get("cgpa_match", "")).strip().lower() == "excluded":
        return True
    return any(
        str(item.get(key, "")).strip().lower() == "excluded"
        for key in _HARD_EXCLUSION_KEYS
    )


def _positive_signals(item: dict[str, Any]) -> int:
    """Count confirmed positive gates (ranking signal for review section)."""
    signals = 0
    if str(item.get("degree_match", "")).strip().lower() == "eligible":
        signals += 1
    if str(item.get("field_match", "")).strip().lower() in {"eligible", "possible"}:
        signals += 1
    if str(item.get("funding_status", "")).strip().lower() == "verified_full":
        signals += 1
    if str(item.get("nationality_match", "")).strip().lower() == "eligible":
        signals += 1
    if str(item.get("destination_match", "")).strip().lower() == "eligible":
        signals += 1
    if str(item.get("application_from_abroad", "")).strip().lower() == "eligible":
        signals += 1
    if str(item.get("verification_status", "")).strip().lower() == "verified":
        signals += 1
    return signals


def missing_evidence(item: dict[str, Any]) -> list[str]:
    """Explain exactly which evidence keeps a record out of strict matches.

    Only describes the record's own evaluated fields; never invents facts.
    """
    missing: list[str] = []
    if str(item.get("verification_status", "")).strip().lower() != "verified":
        missing.append("Official verification page not fetched")
    if str(item.get("degree_match", "")).strip().lower() == "unknown":
        missing.append("Master's eligibility not stated on the official page")
    field_match = str(item.get("field_match", "")).strip().lower()
    if field_match == "unknown":
        missing.append("Computing field not confirmed")
    elif field_match == "possible":
        missing.append("Computing field needs programme-level confirmation")
    if str(item.get("funding_status", "")).strip().lower() == "unknown":
        missing.append("Full funding not verified — tuition AND living evidence missing")
    nationality_match = str(item.get("nationality_match", "")).strip().lower()
    if nationality_match == "unknown":
        missing.append("Eligibility for Benin not stated")
    elif (
        nationality_match == "eligible"
        and str(item.get("nationality_confidence", "")).strip().lower() != "high"
    ):
        missing.append("Eligibility stated broadly but not confirmed for Benin")
    if str(item.get("destination_match", "")).strip().lower() == "unknown":
        missing.append("Study country not verified")
    if str(item.get("application_from_abroad", "")).strip().lower() == "unknown":
        missing.append("Applying from abroad not confirmed")
    if str(item.get("deadline_state", "")).strip().lower() == "unknown":
        missing.append("Application deadline not found")
    for gap in item.get("profile_requirements_missing", []) or []:
        missing.append(f"Unverified applicant requirement: {gap}")
    return missing


def _review_key(item: dict[str, Any]) -> str:
    for key in ("canonical_url", "official_url", "url"):
        value = str(item.get(key, "")).strip().lower().rstrip("/")
        if value:
            return value
    return str(item.get("title", "")).strip().lower()


def review_items(items: list[dict[str, Any]], limit: int = REVIEW_LIMIT) -> list[dict[str, Any]]:
    """Possible matches worth a human look: no hard exclusion, some signal.

    Excludes records with any rejection marker and records with zero
    positive signals. Deduplicates, ranks by confirmed signals, caps output.
    """
    seen: set[str] = set()
    ranked: list[tuple[int, dict[str, Any]]] = []
    for item in items:
        if str(item.get("match_status", "")).strip().lower() != "possible_match":
            continue
        if _is_hard_excluded(item):
            continue
        signals = _positive_signals(item)
        if signals < 2:
            continue
        key = _review_key(item)
        if key in seen:
            continue
        seen.add(key)
        ranked.append((signals, item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in ranked[: max(0, limit)]]


def _review_card(
    item: dict[str, Any],
    missing: list[str],
) -> str:

    title = escape(
        _clean(
            item.get("title"),
            "Scholarship",
        )
    )

    url = str(
        item.get("official_url", "")
        or item.get("url", "")
    ).strip()

    source = escape(
        _clean(item.get("source_name"))
    )

    destination = escape(
        _clean(item.get("destination"))
    )

    missing_html = "".join(
        f"<li>{escape(point)}</li>"
        for point in missing
    ) or "<li>Evidence incomplete.</li>"

    if url:
        link = (
            f'<a href="{escape(url)}" '
            f'style="font-size:16px;'
            f'font-weight:700;">'
            f"{title}</a>"
        )
    else:
        link = f"<strong>{title}</strong>"

    return f"""
    <div style="
        border:1px solid #e3c878;
        border-radius:12px;
        padding:18px;
        margin:0 0 18px 0;
        background:#fffdf4;
    ">

        {link}

        <p style="margin:12px 0 6px; font-size:13px; color:#666;">
            Source: {source} &nbsp;|&nbsp;
            Destination: {destination}
        </p>

        <div style="
            margin-top:10px;
            padding:12px;
            background:#f6f8fa;
            border-radius:8px;
        ">
            <strong>Missing evidence (why this is not a verified match):</strong>
            <ul style="margin:8px 0 0 20px;">
                {missing_html}
            </ul>
        </div>

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

    review = review_items(items)
    review_cards = "\n".join(
        _review_card(item, missing_evidence(item))
        for item in review
    )
    if review_cards:
        review_section = f"""
            <h2 style="margin-top:28px;">
                🔍 Promising, needs verification ({len(review)})
            </h2>

            <p style="
                padding:12px;
                background:#fff4d6;
                border-radius:8px;
                font-size:14px;
            ">
                These are <strong>NOT verified matches</strong>.
                Do not treat them as eligible or fully funded.
                Each card states exactly which evidence is still missing.
            </p>

            {review_cards}
        """
    else:
        review_section = """
            <h2 style="margin-top:28px;">
                🔍 Promising, needs verification
            </h2>

            <p style="color:#666;">
                None this run — no possible match had enough
                positive evidence to review.
            </p>
        """

    diagnostics = diagnostics or {}
    summary_rows = "".join(
        f"<li>{escape(label)}: {diagnostics.get(key, 0)}</li>"
        for key, label in (
            ("scholarships_discovered", "Candidates Discovered"),
            ("official_pages_checked", "Official Pages Checked"),
            ("possible_matches", "Possible Matches"),
            ("strong_matches", "Strong Matches"),
        )
        if key in diagnostics
    )
    if summary_rows:
        summary_rows = "<ul>" + summary_rows + "</ul>"
    diagnostic_rows = "".join(
        f"<li>{escape(key.replace('_', ' ').title())}: {value}</li>"
        for key, value in diagnostics.items()
        if not str(key).startswith("reason_")
        and key not in {"scholarships_discovered", "official_pages_checked", "possible_matches", "strong_matches"}
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
            "<h3>Rejected summary</h3>"
            "<ul>" + reason_rows + "</ul>"
        )
    source_rows = ""
    if source_health:
        entries = "".join(
            f"<li>{escape(str(entry.get('display_name', source_id)))}: "
            f"{entry.get('discovered', 0)} candidates, "
            f"{entry.get('official_fetched', 0)} official checked, "
            f"{entry.get('strong_matches', entry.get('verified', 0))} strong, "
            f"{entry.get('junk_skipped', 0)} skipped, "
            f"{entry.get('errors', 0)} errors</li>"
            for source_id, entry in source_health.items()
            if isinstance(entry, dict)
        )
        if entries:
            source_rows = (
                "<h3>Sources checked</h3>"
                "<ul>" + entries + "</ul>"
            )
    diagnostics_section = (
        summary_rows + source_rows + reason_rows
        + "<ul>" + diagnostic_rows + "</ul>"
        if (summary_rows or source_rows or reason_rows or diagnostic_rows)
        else ""
    )

    if not included:
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

                """ + review_section + diagnostics_section + """

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

            <h2>
                ✅ Verified strict matches ({len(included)})
            </h2>

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

            {review_section}

            {diagnostics_section}

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
