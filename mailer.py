"""guac email delivery — sends magic-link sign-in emails over SMTP.

Required when ADGATE_DEV_MODE=0 (production). If SMTP_HOST is not configured,
send() returns False so callers can surface a clear "email not configured"
error instead of silently failing to deliver a login link.
"""
import logging
import smtplib
from email.mime.text import MIMEText

import config

log = logging.getLogger("guac.email")


def send_magic_link(to_email: str, link: str) -> bool:
    """Email a magic sign-in link to the user. Returns True on success.

    No-op / failure when SMTP isn't configured — the caller should tell the
    user the portal isn't open yet, never pretend the email went out.
    """
    if not config.SMTP_HOST:
        log.warning("email not configured (ADGATE_SMTP_HOST unset) — cannot send "
                    "magic link to %s", to_email)
        return False
    if not config.EMAIL_FROM:
        log.warning("ADGATE_EMAIL_FROM unset — cannot send magic link to %s", to_email)
        return False

    msg = MIMEText(f"Your guac sign-in link (valid 15 minutes):\n\n{link}\n")
    msg["Subject"] = "guac — your sign-in link"
    msg["From"] = config.EMAIL_FROM
    msg["To"] = to_email

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as s:
            s.starttls()
            if config.SMTP_USER:
                s.login(config.SMTP_USER, config.SMTP_PASS)
            s.sendmail(config.EMAIL_FROM, [to_email], msg.as_string())
        return True
    except Exception as e:  # smtplib errors, DNS, TLS, auth
        log.warning("failed to send magic link to %s: %s", to_email, e)
        return False
