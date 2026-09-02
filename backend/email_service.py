# SMTP if configured, otherwise write HTML/text to mail_outbox/

from __future__ import annotations

from datetime import datetime
from email.message import EmailMessage
from html import escape
from pathlib import Path
import logging
import smtplib
import ssl

from config import settings

logger = logging.getLogger("amalost.mail")

OUTBOX_DIR = Path(__file__).resolve().parent / "mail_outbox"
OUTBOX_DIR.mkdir(exist_ok=True)

ANTI_FRAUD_TIPS_TEXT = """\
Safety & anti-fraud tips
------------------------
• Complete the exchange through the campus lost-and-found desk — staff mediate custody.
• Contact each other only to coordinate turning the item in / claiming at the desk.
• Do not send money, gift cards, courier fees, or deposit payments.
• For phones/gadgets, verify serial numbers or distinctive marks with staff.
• Verify the item carefully before handover (photos, marks, contents, serials).
• Bring a campus ID. Prefer daylight hours.
• If anything feels wrong, stop the exchange and contact campus security.
• AMAlost never asks for your password by email.
"""

ANTI_FRAUD_TIPS_HTML = """
<div style="margin-top:20px;padding:16px 18px;border-radius:12px;background:#FFF7ED;border:1px solid #FED7AA;">
  <div style="font-size:13px;font-weight:700;color:#9A3412;margin-bottom:8px;">Safety &amp; anti-fraud tips</div>
  <ul style="margin:0;padding-left:18px;color:#9A3412;font-size:13px;line-height:1.55;">
    <li>Complete the exchange through the campus lost-and-found desk — staff mediate custody.</li>
    <li>Coordinate only to turn the item in / claim it at the desk.</li>
    <li>Never send money, gift cards, courier fees, or deposits.</li>
    <li>For phones/gadgets, verify serial numbers or distinctive marks with staff.</li>
    <li>Verify the item carefully (photos, marks, contents, serials).</li>
    <li>Bring campus ID. Prefer daylight hours.</li>
    <li>If anything feels wrong, stop and contact campus security.</li>
    <li>AMAlost will never ask for your password by email.</li>
  </ul>
</div>
"""


def smtp_configured() -> bool:
    return bool(getattr(settings, "smtp_host", None))


def _smtp_password() -> str:
    # Gmail app passwords are often stored with spaces; SMTP auth expects none.
    return (getattr(settings, "smtp_password", None) or "").replace(" ", "")


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
              <div style="font-size:22px;font-weight:800;margin-top:6px;">AMA<span style="opacity:0.85;">lost</span></div>
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
              This message was sent automatically by AMAlost.
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
    if not to:
        return {"sent": False, "reason": "missing_recipient", "to": None, "mode": mail_delivery_mode()}

    from_addr = getattr(settings, "smtp_from", None) or "AMAlost <noreply@ama.edu.ph>"
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
            password = _smtp_password()
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
            # SMTP configured: never fall back to outbox.
            logger.exception("SMTP send failed (no outbox fallback): %s", exc)
            meta["smtp_error"] = str(exc)
            meta["sent"] = False
            meta["mode"] = "smtp"
            return meta

    # Dev-only fallback when SMTP is not configured
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


def notify_email_verification(*, to_email: str, name: str | None, verify_url: str) -> dict:
    display_name = (name or "").strip() or "there"
    text_body = (
        f"Hi {display_name},\n\n"
        f"Welcome to AMAlost — AMA University's campus lost & found.\n\n"
        f"Please verify your email to activate your account:\n"
        f"{verify_url}\n\n"
        f"If you did not create this account, you can ignore this message.\n\n"
        f"— AMAlost Campus Lost & Found\n"
    )
    html_body = _wrap_html(
        title="Verify your AMAlost email",
        eyebrow="Account verification",
        body_html=(
            f"<p>Hi {escape(display_name)},</p>"
            f"<p>Welcome to AMAlost. Confirm your email to activate your account and start "
            f"reporting lost or found items.</p>"
            f"<p style='margin-top:14px;color:#64748B;font-size:13px;'>"
            f"If you did not create this account, you can ignore this message.</p>"
        ),
        cta_url=verify_url,
        cta_label="Verify email",
    )
    return send_email(
        to_email,
        "Verify your AMAlost account",
        text_body,
        html_body=html_body,
    )


def notify_match_to_owner(*, owner_email: str, category: str, match_count: int, top_score: float | None) -> dict:
    score_text = f"{top_score:.0%}" if top_score is not None else "n/a"
    text_body = (
        f"Hi,\n\n"
        f"AMAlost found {match_count} possible match(es) for your lost {category}.\n"
        f"Top confidence: {score_text}.\n\n"
        f"Open AMAlost → My items → Search again on that report to review matches and claim.\n\n"
        f"— AMAlost Campus Lost & Found\n"
    )
    html_body = _wrap_html(
        title=f"Possible match for your {category}",
        eyebrow="Match alert",
        body_html=(
            f"<p>Hi,</p>"
            f"<p>AMAlost found <strong>{match_count}</strong> possible match(es) for your lost "
            f"<strong>{escape(category)}</strong>.</p>"
            f"<p>Top confidence: <strong>{escape(score_text)}</strong>.</p>"
            f"<p>Open <strong>AMAlost → My items → Search again</strong> on that report to review and claim.</p>"
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
        f"Open AMAlost → My items → Search again on that found report to review and accept.\n\n"
        f"— AMAlost Campus Lost & Found\n"
    )
    html_body = _wrap_html(
        title=f"A lost report may match your found {category}",
        eyebrow="Finder update",
        body_html=(
            f"<p>Hi,</p>"
            f"<p>Someone reported a lost <strong>{escape(category)}</strong> that may match the item you found"
            f"{f' at <strong>{escape(location)}</strong>' if location else ''}.</p>"
            f"<p>Open <strong>AMAlost → My items → Search again</strong> on that found report to review and accept.</p>"
            f"<p>If you accept a match, we’ll email both parties and route the handover through the campus lost-and-found desk.</p>"
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
    confirm_url: str,
) -> dict:
    text_body = (
        f"Hi,\n\n"
        f"Good news — your AMAlost match for the {category} was accepted.\n"
        f"Status is now: IN PROCESS.\n\n"
        f"Finder name: {finder_name or 'Anonymous'}\n"
        f"Finder email: {finder_email}\n"
        f"Found location: {found_location or 'n/a'}\n"
        f"Lost location: {lost_location or 'n/a'}\n\n"
        f"Bring/claim the item at the campus lost-and-found desk. Staff mediate custody before the case is closed.\n\n"
        f"After desk release, you may confirm here:\n{confirm_url}\n\n"
        f"{ANTI_FRAUD_TIPS_TEXT}\n"
        f"— AMAlost Campus Lost & Found\n"
    )
    html_body = _wrap_html(
        title=f"Match accepted for your {category}",
        eyebrow="Status: In process",
        body_html=(
            f"<p>Hi,</p>"
            f"<p>Your AMAlost match was accepted. Complete handover at the campus lost-and-found desk; staff must receive and release the item.</p>"
            f"{_detail_rows([
                ('Finder name', finder_name or 'Anonymous'),
                ('Finder email', finder_email),
                ('Found location', found_location or 'n/a'),
                ('Lost location', lost_location or 'n/a'),
            ])}"
            f"<p style='margin-top:16px;color:#334155;'>Both parties must confirm before the item is marked <strong>processed</strong>.</p>"
        ),
        cta_url=confirm_url,
        cta_label="Confirm my successful exchange",
    )
    return send_email(
        owner_email,
        f"AMAlost match accepted — contact finder for your {category}",
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
    confirm_url: str,
) -> dict:
    greeting = f"Hi {finder_name}," if finder_name else "Hi,"
    text_body = (
        f"{greeting}\n\n"
        f"An owner accepted a match for the {category} you reported found.\n"
        f"Status is now: IN PROCESS.\n\n"
        f"Owner email: {owner_email}\n"
        f"Found location: {found_location or 'n/a'}\n"
        f"Lost location: {lost_location or 'n/a'}\n\n"
        f"Bring/claim the item at the campus lost-and-found desk. Staff mediate custody before the case is closed.\n\n"
        f"After desk release, you may confirm here:\n{confirm_url}\n\n"
        f"{ANTI_FRAUD_TIPS_TEXT}\n"
        f"— AMAlost Campus Lost & Found\n"
    )
    html_body = _wrap_html(
        title=f"Owner claimed your found {category}",
        eyebrow="Status: In process",
        body_html=(
            f"<p>{escape(greeting.rstrip(','))},</p>"
            f"<p>Please verify they are the rightful owner at the campus desk. Staff mediate custody before the listing is closed.</p>"
            f"{_detail_rows([
                ('Owner email', owner_email),
                ('Found location', found_location or 'n/a'),
                ('Lost location', lost_location or 'n/a'),
            ])}"
            f"<p style='margin-top:16px;color:#334155;'>Both parties must confirm before the listing is marked <strong>processed</strong>.</p>"
        ),
        cta_url=confirm_url,
        cta_label="Confirm my successful exchange",
    )
    return send_email(
        finder_email,
        f"AMAlost match accepted — contact owner for your found {category}",
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
        f"If this was a mistake, you can restart the match from AMAlost.\n\n"
        f"— AMAlost Campus Lost & Found\n"
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
            f"<p style='margin-top:14px;'>If this was a mistake, restart the match from AMAlost.</p>"
        ),
    )
    return send_email(
        to_email,
        f"AMAlost exchange cancelled — {category}",
        text_body,
        html_body=html_body,
    )
