"""Email scholarship results through Resend."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from html import escape
from typing import Any


RESEND_API_URL = "https://api.resend.com/emails"


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
    """
    Only email scholarships that have a meaningful match.

    Good matches are always included.
    Needs-manual-check is included when the score is at least 30.
    """
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

    link = (
        f'<a href="{escape(url)}" '
        f'style="font-size:16px;font-weight:700;">{title}</a>'
        if url
        else f"<strong>{title}</strong>"
    )

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
            <div style="max-width:760px;margin:auto;background:white;padding:24px;
                        border-radius:12px;">
                <h1>Master Scholarship Hunter</h1>
                <p>No scholarships met the current matching threshold today.</p>
                <p>
                    The Actor completed successfully and checked the available
                    scholarship records.
                </p>
            </div>
        </body>
        </html>
        """

    cards = "\n".join(_scholarship_card(item) for item in relevant)

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

            <hr style="border:none;border-top:1px solid #ddd;margin:24px 0;">

            <p style="font-size:13px;color:#666;">
                This email was generated automatically by Master Scholarship Hunter.
            </p>
        </div>
    </body>
    </html>
    """


async def send_scholarship_email(
    items: list[dict[str, Any]],
) -> None:
    api_key = _get_required_env("RESEND_API_KEY")
    to_address = _get_required_env("EMAIL_TO")
    from_address = _get_required_env("EMAIL_FROM")

    relevant = [item for item in items if _is_relevant(item)]

    subject = (
        f"🎓 Scholarship Hunter — {len(relevant)} "
        f"matching scholarship(s)"
    )

    payload = {
        "from": from_address,
        "to": [to_address],
        "subject": subject,
        "html": build_email_html(items),
    }

    request = urllib.request.Request(
        RESEND_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8")

        response_data = json.loads(response_body)

        email_id = response_data.get("id", "unknown")

        print(
            f"Scholarship email sent successfully. "
            f"Resend email ID: {email_id}"
        )

    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")

        raise RuntimeError(
            f"Resend API returned HTTP {error.code}: {error_body}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Could not connect to Resend: {error}"
        ) from error
