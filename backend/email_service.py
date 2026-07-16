"""Email notifications for FindIt.

Uses SMTP when configured; otherwise writes messages to backend/mail_outbox/
so thesis demos can prove notifications without a live mail server.
"""

from __future__ import annotations

from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
import logging
import smtplib
import ssl

from config import settings

logger = logging.getLogger("findit.mail")

OUTBOX_DIR = Path(__file__).resolve().parent / "mail_outbox"
OUTBOX_DIR.mkdir(exist_ok=True)


def _smtp_configured() -> bool:
    return bool(getattr(settings, "smtp_host", None))


def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email. Returns delivery metadata for claim/notify logging."""
    if not to:
        return {"sent": False, "reason": "missing_recipient", "to": None}

    from_addr = getattr(settings, "smtp_from", None) or "FindIt <noreply@findit.local>"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_addr
    message["To"] = to
    message.set_content(body)

    meta = {
        "sent": False,
        "to": to,
        "subject": subject,
        "mode": "smtp" if _smtp_configured() else "outbox",
        "at": datetime.now().isoformat(timespec="seconds"),
    }

    if _smtp_configured():
        try:
            host = settings.smtp_host
            port = int(getattr(settings, "smtp_port", 587) or 587)
            user = getattr(settings, "smtp_user", None) or ""
            password = getattr(settings, "smtp_password", None) or ""
            use_tls = str(getattr(settings, "smtp_tls", "true")).lower() in {"1", "true", "yes"}

            if use_tls:
                context = ssl.create_default_context()
                with smtplib.SMTP(host, port, timeout=20) as server:
                    server.starttls(context=context)
                    if user:
                        server.login(user, password)
                    server.send_message(message)
            else:
                with smtplib.SMTP(host, port, timeout=20) as server:
                    if user:
                        server.login(user, password)
                    server.send_message(message)

            meta["sent"] = True
            logger.info("SMTP mail sent to %s (%s)", to, subject)
            return meta
        except Exception as exc:
            logger.exception("SMTP send failed; falling back to outbox: %s", exc)
            meta["smtp_error"] = str(exc)
            meta["mode"] = "outbox"

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    safe_to = to.replace("@", "_at_").replace("/", "_")
    path = OUTBOX_DIR / f"{stamp}_{safe_to}.txt"
    path.write_text(
        f"From: {from_addr}\nTo: {to}\nSubject: {subject}\nSent-At: {meta['at']}\n\n{body}\n",
        encoding="utf-8",
    )
    meta["sent"] = True
    meta["outbox_path"] = str(path)
    logger.info("Outbox mail written for %s -> %s", to, path)
    return meta


def notify_match_to_owner(*, owner_email: str, category: str, match_count: int, top_score: float | None) -> dict:
    score_text = f"{top_score:.0%}" if top_score is not None else "n/a"
    body = (
        f"Hi,\n\n"
        f"FindIt found {match_count} possible match(es) for your lost {category}.\n"
        f"Top confidence: {score_text}.\n\n"
        f"Open FindIt to review the matches and claim your item at the Library Information Desk.\n\n"
        f"— FindIt Campus Lost & Found\n"
    )
    return send_email(
        owner_email,
        f"Possible match found for your lost {category}",
        body,
    )


def notify_match_to_finder(*, finder_email: str, category: str, location: str | None) -> dict:
    body = (
        f"Hi,\n\n"
        f"Someone reported a lost {category} that may match the item you found"
        f"{f' at {location}' if location else ''}.\n\n"
        f"If they claim it, we'll email you again with pickup details.\n\n"
        f"— FindIt Campus Lost & Found\n"
    )
    return send_email(
        finder_email,
        f"A lost report may match your found {category}",
        body,
    )


def notify_claim_to_owner(*, owner_email: str, category: str, finder_email: str | None) -> dict:
    body = (
        f"Hi,\n\n"
        f"Your claim for the found {category} was recorded.\n"
        f"Please arrange pickup at the Library Information Desk.\n"
        f"Finder contact on file: {finder_email or 'not provided'}.\n\n"
        f"— FindIt Campus Lost & Found\n"
    )
    return send_email(owner_email, f"Claim confirmed for your {category}", body)


def notify_claim_to_finder(*, finder_email: str, category: str, owner_email: str | None) -> dict:
    body = (
        f"Hi,\n\n"
        f"The owner has claimed the {category} you reported found.\n"
        f"Please bring it to the Library Information Desk for return.\n"
        f"Owner contact on file: {owner_email or 'not provided'}.\n\n"
        f"— FindIt Campus Lost & Found\n"
    )
    return send_email(finder_email, f"Owner claimed your found {category}", body)
