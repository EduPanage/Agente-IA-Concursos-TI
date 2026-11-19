import os
import smtplib
import html
from email.message import EmailMessage
from email.utils import formatdate

from dotenv import load_dotenv

from app.database.db import get_unnotified_news, mark_as_notified


def build_email(news_items):
    message = EmailMessage()
    message["Subject"] = (
        f"[Concursos TI] {len(news_items)} oportunidade(s) para acompanhar"
    )
    message["Date"] = formatdate(localtime=True)

    text_lines = [
        "Oportunidades de concursos públicos na área de TI",
        "",
        "As publicações abaixo passaram pelos critérios automáticos do agente.",
        "Confira o edital e a página oficial antes de tomar qualquer decisão.",
        "",
    ]
    html_items = []

    for item in news_items:
        title = item["title"] or "Sem título"
        link = item["link"] or ""
        location = item["location"] or "Localidade não identificada"
        relevance = item["relevance"] or "Não classificada"
        event_type = item["event_type"] or "Etapa não identificada"
        reason = item["classification_reason"] or ""

        text_lines.extend([
            title,
            f"Localidade: {location}",
            f"Etapa: {event_type}",
            f"Relevância: {relevance}",
            f"Motivo: {reason}",
            f"Link: {link}",
            "",
            "-" * 60,
            "",
        ])

        html_items.append(
            "<li style='margin-bottom:22px'>"
            f"<strong>{html.escape(title)}</strong><br>"
            f"Localidade: {html.escape(location)}<br>"
            f"Etapa: {html.escape(event_type)}<br>"
            f"Relevância: {html.escape(relevance)}<br>"
            f"Motivo: {html.escape(reason)}<br>"
            f"<a href='{html.escape(link, quote=True)}'>Acessar publicação</a>"
            "</li>"
        )

    message.set_content("\\n".join(text_lines))
    message.add_alternative(
        "<html><body><h2>Oportunidades de concursos públicos - TI</h2>"
        "<p>Confira sempre o edital e a página oficial da instituição.</p>"
        f"<ul>{''.join(html_items)}</ul></body></html>",
        subtype="html",
    )
    return message


def send_pending_notifications():
    """Envia um e-mail consolidado e marca os itens após envio confirmado."""
    load_dotenv()

    sender = os.getenv("GMAIL_ADDRESS", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
    recipient = os.getenv("NOTIFICATION_EMAIL", "").strip() or sender

    if not sender or not app_password or not recipient:
        print(
            "Notificações não configuradas. Defina GMAIL_ADDRESS, "
            "GMAIL_APP_PASSWORD e NOTIFICATION_EMAIL no arquivo .env."
        )
        return {"sent": 0, "notified": 0, "reason": "not_configured"}

    news_items = get_unnotified_news()
    if not news_items:
        print("Nenhuma oportunidade nova elegível para notificação.")
        return {"sent": 0, "notified": 0, "reason": "no_news"}

    message = build_email(news_items)
    message["From"] = sender
    message["To"] = recipient

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(sender, app_password)
            server.send_message(message)

        for item in news_items:
            mark_as_notified(item["id"])

        print(f"E-mail enviado para {recipient}.")
        print(f"Notícias incluídas: {len(news_items)}")
        return {"sent": 1, "notified": len(news_items), "reason": "success"}

    except (smtplib.SMTPException, OSError) as error:
        print(f"Falha ao enviar e-mail: {error}")
        return {"sent": 0, "notified": 0, "reason": str(error)}
