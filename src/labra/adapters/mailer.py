import smtplib
import ssl
from email.message import EmailMessage
from typing import Self
from urllib.parse import unquote, urlsplit

import structlog

from labra.core.config import Settings
from labra.core.errors import ConfigError
from labra.core.ports import Mail

log = structlog.stdlib.get_logger("labra.mail")


def build_message(mail: Mail, sender: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(mail.to)
    msg["Subject"] = mail.subject
    msg.set_content(mail.body)
    for filename, data, mime in mail.attachments:
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return msg


class ConsoleMailer:
    """Development mailer: logs that a mail was sent, without addresses or content."""

    def __init__(self) -> None:
        self.sent: list[Mail] = []

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls()

    def send(self, mail: Mail) -> None:
        self.sent.append(mail)
        log.info(
            "mail_not_sent_console", recipients=len(mail.to), attachments=len(mail.attachments)
        )


class SmtpMailer:
    """Any SMTP relay. `LABRA_SMTP_URL=smtps://user:pass@host:465` or
    `smtp://user:pass@host:587` (STARTTLS is required on plain smtp)."""

    def __init__(self, url: str, sender: str, timeout: float = 30) -> None:
        parts = urlsplit(url)
        if parts.scheme not in {"smtp", "smtps"} or not parts.hostname:
            raise ConfigError("LABRA_SMTP_URL must look like smtps://user:pass@host:465.")
        self.parts = parts
        self.sender = sender
        self.timeout = timeout

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        if settings.smtp_url is None:
            raise ConfigError("LABRA_MAILER=smtp needs LABRA_SMTP_URL.")
        return cls(settings.smtp_url.get_secret_value(), settings.mail_from)

    def send(self, mail: Mail) -> None:
        p = self.parts
        host = p.hostname or ""
        context = ssl.create_default_context()
        if p.scheme == "smtps":
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                host, p.port or 465, timeout=self.timeout, context=context
            )
        else:
            client = smtplib.SMTP(host, p.port or 587, timeout=self.timeout)
        with client:
            if p.scheme == "smtp":
                client.starttls(context=context)
            if p.username:
                client.login(unquote(p.username), unquote(p.password or ""))
            client.send_message(build_message(mail, self.sender))
        log.info("mail_sent", recipients=len(mail.to), attachments=len(mail.attachments))
