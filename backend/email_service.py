"""Email notifications for FindIt.

Uses SMTP when configured; otherwise writes messages to backend/mail_outbox/
so thesis demos can prove notifications without a live mail server.
"""

from __future__ import annotations

from datetime import datetime
from email.message import EmailMessage
from html import escape
from pathlib import Path
import logging
import smtplib
import ssl

from config import settings

logger = logging.getLogger("findit.mail")

OUTBOX_DIR = Path(__file__).resolve().parent / "mail_outbox"
OUTBOX_DIR.mkdir(exist_ok=True)

ANTI_FRAUD_TIPS_TEXT = """\
Safety & anti-fraud tips
------------------------
• Meet only at the Library Information Desk (or another staffed campus office).
• Do not send money, gift cards, courier fees, or deposit payments.
• Verify the item carefully before handing it over (photos, marks, contents, serials).
• Ask the claimant to describe a private detail that is not visible in the public listing.
• Bring a campus ID. Prefer daylight / staffed hours.
• If anything feels wrong, stop the exchange and contact campus security.
• FindIt never asks for your password by email.
"""

ANTI_FRAUD_TIPS_HTML = """
<div style="margin-top:20px;padding:16px 18px;border-radius:12px;background:#FFF7ED;border:1px solid #FED7AA;">
  <div style="font-size:13px;font-weight:700;color:#9A3412;margin-bottom:8px;">Safety &amp; anti-fraud tips</div>
  <ul style="margin:0;padding-left:18px;color:#9A3412;font-size:13px;line-height:1.55;">
    <li>Meet only at the Library Information Desk (or another staffed campus office).</li>
    <li>Never send money, gift cards, courier fees, or deposits.</li>
    <li>Verify the item carefully (photos, marks, contents, serials).</li>
    <li>Ask for a private detail not visible in the public listing.</li>
    <li>Bring campus ID. Prefer daylight / staffed hours.</li>
    <li>If anything feels wrong, stop and contact campus security.</li>
    <li>FindIt will never ask for your password by email.</li>
  </ul>
</div>
"""


def smtp_configured() -> bool:
    return bool(getattr(settings, "smtp_host", None))


def mail_delivery_mode() -> str:
    return "smtp" if smtp_configured() else "outbox"


def _wrap_html(*, title: str, eyebrow: str, body_html: str, cta_url: str | None = None, cta_label: str | None = None) -> str:
    button = ""
    if cta_url and cta_label:
        button = f"""
        <div style="margin:24px 0 8px;text-align:center;">
          <a href="{escape(cta_url)}"
             style="display:inline-block;background:#4F46E5;color:#ffffff;text-decoration:none;
                    font-weight:700;font-size:14px;padding:12px 22px;border-radius:999px;">
            {escape(cta_label)}
          </a>
        </div>
        <div style="font-size:12px;color:#64748B;text-align:center;word-break:break-all;margin-bottom:8px;">
          Or open: <a href="{escape(cta_url)}" style="color:#4F46E5;">{escape(cta_url)}</a>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/></head>
<body style="margin:0;padding:0;background:#0F172A;font-family:Inter,Segoe UI,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0F172A;padding:28px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
               style="max-width:560px;background:#FFFFFF;border-radius:18px;overflow:hidden;">
          <tr>
            <td style="background:linear-gradient(135deg,#4F46E5,#6366F1);padding:22px 24px;color:#fff;">
              <div style="font-size:12px;letter-spacing:0.08em;text-transform:uppercase;opacity:0.9;">{escape(eyebrow)}</div>
              <div style="font-size:22px;font-weight:800;margin-top:6px;">Find<span style="opacity:0.85;">It</span></div>
              <div style="font-size:16px;font-weight:700;margin-top:10px;">{escape(title)}</div>
            </td>
          </tr>
          <tr>
            <td style="padding:24px;color:#0F172A;font-size:14px;line-height:1.6;">
              {body_html}
              {button}
              {ANTI_FRAUD_TIPS_HTML if cta_url else ""}
            </td>
          </tr>
          <tr>
            <td style="padding:14px 24px 20px;background:#F8FAFC;color:#64748B;font-size:12px;line-height:1.5;">
              Campus Lost &amp; Found · Library Information Desk<br/>
              This message was sent automatically by FindIt.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _detail_rows(rows: list[tuple[str, str]]) -> str:
    items = "".join(
        f"""
        <tr>
          <td style="padding:8px 0;color:#64748B;width:140px;vertical-align:top;">{escape(label)}</td>
          <td style="padding:8px 0;color:#0F172A;font-weight:600;">{escape(value)}</td>
        </tr>
        """
        for label, value in rows
    )
    return f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:14px;">{items}</table>'


def send_email(
    to: str,
    subject: str,
    text_body: str,
    *,
    html_body: str | None = None,
    reply_to: str | None = None,
) -> dict:
    """Send an email. Returns delivery metadata for claim/notify logging."""
    if not to:
        return {"sent": False, "reason": "missing_recipient", "to": None, "mode": mail_delivery_mode()}

    from_addr = getattr(settings, "smtp_from", None) or "FindIt <noreply@findit.local>"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_addr
    message["To"] = to
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    meta = {
        "sent": False,
        "to": to,
        "subject": subject,
        "mode": "smtp" if smtp_configured() else "outbox",
        "at": datetime.now().isoformat(timespec="seconds"),
    }

    if smtp_configured():
        try:
            host = settings.smtp_host
            port = int(getattr(settings, "smtp_port", 587) or 587)
            user = getattr(settings, "smtp_user", None) or ""
            password = getattr(settings, "smtp_password", None) or ""
            use_tls = bool(getattr(settings, "smtp_tls", True))

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
        f"From: {from_addr}\nTo: {to}\n"
        f"Reply-To: {reply_to or ''}\n"
        f"Subject: {subject}\nSent-At: {meta['at']}\n\n{text_body}\n",
        encoding="utf-8",
    )
    if html_body:
        html_path = OUTBOX_DIR / f"{stamp}_{safe_to}.html"
        html_path.write_text(html_body, encoding="utf-8")
        meta["outbox_html_path"] = str(html_path)
    meta["sent"] = True
    meta["outbox_path"] = str(path)
    logger.info("Outbox mail written for %s -> %s", to, path)
    return meta


def notify_match_to_owner(*, owner_email: str, category: str, match_count: int, top_score: float | None) -> dict:
    score_text = f"{top_score:.0%}" if top_score is not None else "n/a"
    text_body = (
        f"Hi,\n\n"
        f"FindIt found {match_count} possible match(es) for your lost {category}.\n"
        f"Top confidence: {score_text}.\n\n"
        f"Open FindIt to review the matches and claim your item at the Library Information Desk.\n\n"
        f"— FindIt Campus Lost & Found\n"
    )
    html_body = _wrap_html(
        title=f"Possible match for your {category}",
        eyebrow="Match alert",
        body_html=(
            f"<p>Hi,</p>"
            f"<p>FindIt found <strong>{match_count}</strong> possible match(es) for your lost "
            f"<strong>{escape(category)}</strong>.</p>"
            f"<p>Top confidence: <strong>{escape(score_text)}</strong>.</p>"
            f"<p>Open FindIt to review and claim at the Library Information Desk.</p>"
        ),
    )
    return send_email(
        owner_email,
        f"Possible match found for your lost {category}",
        text_body,
        html_body=html_body,
    )


def notify_match_to_finder(*, finder_email: str, category: str, location: str | None) -> dict:
    text_body = (
        f"Hi,\n\n"
        f"Someone reported a lost {category} that may match the item you found"
        f"{f' at {location}' if location else ''}.\n\n"
        f"If they claim it, we'll email you again with pickup details.\n\n"
        f"— FindIt Campus Lost & Found\n"
    )
    html_body = _wrap_html(
        title=f"A lost report may match your found {category}",
        eyebrow="Finder update",
        body_html=(
            f"<p>Hi,</p>"
            f"<p>Someone reported a lost <strong>{escape(category)}</strong> that may match the item you found"
            f"{f' at <strong>{escape(location)}</strong>' if location else ''}.</p>"
            f"<p>If they claim it, we’ll email you again with pickup details.</p>"
        ),
    )
    return send_email(
        finder_email,
        f"A lost report may match your found {category}",
        text_body,
        html_body=html_body,
    )


def notify_match_accepted_to_owner(
    *,
    owner_email: str,
    finder_email: str,
    finder_name: str | None,
    category: str,
    found_location: str | None,
    lost_location: str | None,
    pickup_point: str,
    confirm_url: str,
) -> dict:
    text_body = (
        f"Hi,\n\n"
        f"Good news — your FindIt match for the {category} was accepted.\n"
        f"Status is now: IN PROCESS.\n\n"
        f"Finder name: {finder_name or 'Anonymous'}\n"
        f"Finder email: {finder_email}\n"
        f"Found location: {found_location or 'n/a'}\n"
        f"Lost location: {lost_location or 'n/a'}\n"
        f"Suggested meetup: {pickup_point}\n\n"
        f"After a successful exchange, confirm here:\n{confirm_url}\n\n"
        f"{ANTI_FRAUD_TIPS_TEXT}\n"
        f"— FindIt Campus Lost & Found\n"
    )
    html_body = _wrap_html(
        title=f"Match accepted for your {category}",
        eyebrow="Status: In process",
        body_html=(
            f"<p>Hi,</p>"
            f"<p>Your FindIt match was accepted. Coordinate with the finder, then confirm when the exchange is done.</p>"
            f"{_detail_rows([
                ('Finder name', finder_name or 'Anonymous'),
                ('Finder email', finder_email),
                ('Found location', found_location or 'n/a'),
                ('Lost location', lost_location or 'n/a'),
                ('Meetup', pickup_point),
            ])}"
            f"<p style='margin-top:16px;color:#334155;'>Both parties must confirm before the item is marked <strong>processed</strong>.</p>"
        ),
        cta_url=confirm_url,
        cta_label="Confirm my successful exchange",
    )
    return send_email(
        owner_email,
        f"FindIt match accepted — contact finder for your {category}",
        text_body,
        html_body=html_body,
        reply_to=finder_email if finder_email != "not provided" else None,
    )


def notify_match_accepted_to_finder(
    *,
    finder_email: str,
    finder_name: str | None,
    owner_email: str,
    category: str,
    found_location: str | None,
    lost_location: str | None,
    pickup_point: str,
    confirm_url: str,
) -> dict:
    greeting = f"Hi {finder_name}," if finder_name else "Hi,"
    text_body = (
        f"{greeting}\n\n"
        f"An owner accepted a match for the {category} you reported found.\n"
        f"Status is now: IN PROCESS.\n\n"
        f"Owner email: {owner_email}\n"
        f"Found location: {found_location or 'n/a'}\n"
        f"Lost location: {lost_location or 'n/a'}\n"
        f"Suggested meetup: {pickup_point}\n\n"
        f"After a successful exchange, confirm here:\n{confirm_url}\n\n"
        f"{ANTI_FRAUD_TIPS_TEXT}\n"
        f"— FindIt Campus Lost & Found\n"
    )
    html_body = _wrap_html(
        title=f"Owner claimed your found {category}",
        eyebrow="Status: In process",
        body_html=(
            f"<p>{escape(greeting.rstrip(','))},</p>"
            f"<p>Please verify they are the rightful owner, coordinate pickup, then confirm when the exchange is done.</p>"
            f"{_detail_rows([
                ('Owner email', owner_email),
                ('Found location', found_location or 'n/a'),
                ('Lost location', lost_location or 'n/a'),
                ('Meetup', pickup_point),
            ])}"
            f"<p style='margin-top:16px;color:#334155;'>Both parties must confirm before the listing is marked <strong>processed</strong>.</p>"
        ),
        cta_url=confirm_url,
        cta_label="Confirm my successful exchange",
    )
    return send_email(
        finder_email,
        f"FindIt match accepted — contact owner for your found {category}",
        text_body,
        html_body=html_body,
        reply_to=owner_email,
    )


def notify_exchange_cancelled(
    *,
    to_email: str,
    category: str,
    cancelled_by: str | None,
    other_party_email: str | None,
) -> dict:
    text_body = (
        f"Hi,\n\n"
        f"The in-process exchange for the {category} was cancelled"
        f"{f' by {cancelled_by}' if cancelled_by else ''}.\n\n"
        f"Both items are open again for matching, so the listing may be re-matched or re-claimed.\n"
        f"Other party on file: {other_party_email or 'n/a'}\n\n"
        f"If this was a mistake, you can restart the match from FindIt.\n\n"
        f"— FindIt Campus Lost & Found\n"
    )
    html_body = _wrap_html(
        title=f"Exchange cancelled for {category}",
        eyebrow="Status: Cancelled",
        body_html=(
            f"<p>Hi,</p>"
            f"<p>The in-process exchange was cancelled"
            f"{f' by <strong>{escape(cancelled_by)}</strong>' if cancelled_by else ''}. "
            f"Both items are open again for matching.</p>"
            f"{_detail_rows([
                ('Item', category),
                ('Other party', other_party_email or 'n/a'),
            ])}"
            f"<p style='margin-top:14px;'>If this was a mistake, restart the match from FindIt.</p>"
        ),
    )
    return send_email(
        to_email,
        f"FindIt exchange cancelled — {category}",
        text_body,
        html_body=html_body,
    )


def notify_exchange_processed(
    *,
    to_email: str,
    category: str,
    other_party_email: str | None,
) -> dict:
    text_body = (
        f"Hi,\n\n"
        f"Both parties confirmed the exchange for the {category}.\n"
        f"Status is now: PROCESSED.\n\n"
        f"This item will no longer appear in open lost/found matching lists.\n"
        f"Other party on file: {other_party_email or 'n/a'}\n\n"
        f"Thank you for using FindIt.\n\n"
        f"— FindIt Campus Lost & Found\n"
    )
    html_body = _wrap_html(
        title=f"{category} marked processed",
        eyebrow="Exchange complete",
        body_html=(
            f"<p>Hi,</p>"
            f"<p>Both parties confirmed the exchange. Status is now <strong>processed</strong>.</p>"
            f"{_detail_rows([
                ('Item', category),
                ('Other party', other_party_email or 'n/a'),
            ])}"
            f"<p style='margin-top:14px;'>This item will no longer appear in open lost/found matching lists. Thank you for using FindIt.</p>"
        ),
    )
    return send_email(
        to_email,
        f"FindIt exchange complete — {category} marked processed",
        text_body,
        html_body=html_body,
    )
