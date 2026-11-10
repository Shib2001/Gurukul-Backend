import smtplib
import ssl
from email.message import EmailMessage

from gurukul_be.core.config import Settings, get_settings


class EmailNotConfiguredError(RuntimeError):
    pass


def validate_email_configuration(settings: Settings | None = None) -> None:
    config = settings or get_settings()
    if not config.SMTP_HOST or not config.SMTP_FROM_EMAIL:
        raise EmailNotConfiguredError("Password reset email is not configured")
    if bool(config.SMTP_USERNAME) != bool(config.SMTP_PASSWORD):
        raise EmailNotConfiguredError(
            "SMTP_USERNAME and SMTP_PASSWORD must be configured together"
        )
    if config.SMTP_USE_SSL and config.SMTP_STARTTLS:
        raise EmailNotConfiguredError("Choose SMTP_USE_SSL or SMTP_STARTTLS, not both")
    if not config.SMTP_USE_SSL and not config.SMTP_STARTTLS:
        raise EmailNotConfiguredError("SMTP must use SSL or STARTTLS")


def send_password_reset_code(
    recipient: str, code: str, settings: Settings | None = None
) -> None:
    config = settings or get_settings()
    validate_email_configuration(config)

    message = EmailMessage()
    message["Subject"] = "Your Gurukul password reset code"
    message["From"] = config.SMTP_FROM_EMAIL
    message["To"] = recipient
    message.set_content(
        "Use this code to reset your Gurukul password:\n\n"
        f"{code}\n\n"
        "This code expires in 10 minutes and can only be used once. "
        "If you did not request a password reset, you can ignore this email."
    )

    smtp_context = ssl.create_default_context()
    if config.SMTP_USE_SSL:
        with smtplib.SMTP_SSL(
            config.SMTP_HOST,
            config.SMTP_PORT,
            timeout=config.SMTP_TIMEOUT_SECONDS,
            context=smtp_context,
        ) as server:
            if config.SMTP_USERNAME:
                server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.send_message(message)
        return

    with smtplib.SMTP(
        config.SMTP_HOST,
        config.SMTP_PORT,
        timeout=config.SMTP_TIMEOUT_SECONDS,
    ) as server:
        if config.SMTP_STARTTLS:
            server.starttls(context=smtp_context)
        if config.SMTP_USERNAME:
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        server.send_message(message)
