"""
email_utils.py - Envoi d'emails pour FidesIA
Utilise smtplib (bibliothèque standard).
"""

import html as html_mod
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM

logger = logging.getLogger(__name__)


def send_reset_email(to_email: str, display_name: str, reset_url: str) -> bool:
    """Envoie un email de réinitialisation de mot de passe. Retourne True si envoyé."""
    if not SMTP_HOST or not SMTP_USER:
        logger.warning("SMTP non configuré — email de réinitialisation non envoyé")
        return False

    subject = "FidesIA — Réinitialisation de votre mot de passe"
    safe_name = html_mod.escape(display_name)
    safe_url = html_mod.escape(reset_url)

    html = f"""\
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #2c1810; max-width: 600px; margin: 0 auto; padding: 20px;">
  <div style="text-align: center; margin-bottom: 24px;">
    <span style="color: #8b1a2b; font-size: 32px;">&#10013;</span>
    <h1 style="font-size: 24px; margin: 8px 0 0;">FidesIA</h1>
  </div>
  <p>Bonjour {safe_name},</p>
  <p>Vous avez demandé la réinitialisation de votre mot de passe. Cliquez sur le bouton ci-dessous pour choisir un nouveau mot de passe :</p>
  <div style="text-align: center; margin: 32px 0;">
    <a href="{safe_url}" style="background: #8b1a2b; color: white; text-decoration: none; padding: 12px 32px; border-radius: 10px; font-weight: 500; font-size: 16px;">Réinitialiser mon mot de passe</a>
  </div>
  <p style="font-size: 13px; color: #5a4a3e;">Ce lien expire dans <strong>1 heure</strong>. Si vous n'avez pas fait cette demande, ignorez simplement cet email.</p>
  <hr style="border: none; border-top: 1px solid #e0d5c8; margin: 24px 0;">
  <p style="font-size: 12px; color: #8a7a6e; text-align: center;">FidesIA — Assistant en théologie catholique</p>
</body>
</html>"""

    text = f"Bonjour {display_name},\n\nCliquez sur ce lien pour réinitialiser votre mot de passe :\n{reset_url}\n\nCe lien expire dans 1 heure.\n\nFidesIA"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, to_email, msg.as_string())
        logger.info(f"Email de réinitialisation envoyé à {to_email}")
        return True
    except Exception as e:
        logger.error(f"Échec envoi email à {to_email}: {e}")
        return False
