import os
import smtplib
import html
from email.message import EmailMessage
from email.utils import formatdate

from dotenv import load_dotenv

from app.database.db import (
    get_unnotified_news,
    get_unnotified_monitoring_news,
    mark_as_notified,
    mark_as_monitoring_notified,
)


EVENT_LABELS = {
    "previsto": "Concurso previsto",
    "solicitado": "Concurso solicitado",
    "autorizado": "Concurso autorizado",
    "comissao_formada": "Comissão organizadora formada",
    "banca_definida": "Banca organizadora definida",
}

RELEVANCE_LABELS = {
    "confirmed_dourados": "Vaga com lotação confirmada em Dourados/MS",
    "confirmed_ms": "Vaga com lotação confirmada em Mato Grosso do Sul",
    "national_unknown": "Concurso nacional/federal; lotação ainda indefinida",
}


def _item_fields(item):
    return {
        "title": item["title"] or "Sem título",
        "link": item["link"] or "",
        "location": item["location"] or "Localidade não identificada",
        "event_type": item["event_type"] or "Etapa não identificada",
        "reason": item["classification_reason"] or "",
    }


def _append_text_item(lines, item, monitoring=False):
    fields = _item_fields(item)
    lines.extend([
        fields["title"],
        f"Localidade: {fields['location']}",
        f"Etapa: {EVENT_LABELS.get(fields['event_type'], fields['event_type'])}",
    ])
    if monitoring:
        lines.append(
            "Status: acompanhamento pré-edital; cargo de TI ainda não confirmado."
        )
    else:
        lines.append(
            f"Classificação: {RELEVANCE_LABELS.get(item['relevance'], item['relevance'])}"
        )
    if fields["reason"]:
        lines.append(f"Motivo: {fields['reason']}")
    lines.extend([f"Link: {fields['link']}", "", "-" * 60, ""])


def _html_item(item, monitoring=False):
    fields = _item_fields(item)
    status = (
        "<strong>Acompanhamento pré-edital:</strong> cargo de TI ainda não confirmado."
        if monitoring
        else (
            "<strong>Classificação:</strong> "
            + html.escape(RELEVANCE_LABELS.get(item["relevance"], item["relevance"] or ""))
        )
    )
    link_html = (
        f"<a href='{html.escape(fields['link'], quote=True)}'>Acessar publicação</a>"
        if fields["link"]
        else "Link não informado"
    )
    return (
        "<li style='margin-bottom:22px'>"
        f"<strong>{html.escape(fields['title'])}</strong><br>"
        f"Localidade: {html.escape(fields['location'])}<br>"
        f"Etapa: {html.escape(EVENT_LABELS.get(fields['event_type'], fields['event_type']))}<br>"
        f"{status}<br>"
        f"Motivo: {html.escape(fields['reason'])}<br>"
        f"{link_html}"
        "</li>"
    )


def build_email(opportunity_items, monitoring_items=None):
    """Monta um único e-mail com seções claramente separadas."""
    monitoring_items = monitoring_items or []
    total = len(opportunity_items) + len(monitoring_items)

    message = EmailMessage()
    message["Subject"] = (
        f"[Concursos TI] {len(opportunity_items)} vaga(s) identificada(s) "
        f"e {len(monitoring_items)} aviso(s) de acompanhamento"
    )
    message["Date"] = formatdate(localtime=True)

    text_lines = [
        "Relatório do agente de monitoramento de concursos públicos de TI",
        "",
        "IMPORTANTE: avisos de acompanhamento não representam vagas de TI confirmadas.",
        "Confira sempre a publicação e o edital oficial antes de tomar qualquer decisão.",
        "",
    ]
    html_sections = [
        "<html><body>"
        "<h2>Monitoramento de concursos públicos - TI</h2>"
        "<p><strong>Importante:</strong> avisos de acompanhamento não representam "
        "vagas de TI confirmadas. Confira sempre a publicação e o edital oficial.</p>"
    ]

    if opportunity_items:
        text_lines.extend([
            "1. OPORTUNIDADES COM CARGOS DE TI IDENTIFICADOS",
            "=" * 60,
            "",
        ])
        html_sections.append("<h3>1. Oportunidades com cargos de TI identificados</h3>")
        html_sections.append("<ul>")
        for item in opportunity_items:
            _append_text_item(text_lines, item, monitoring=False)
            html_sections.append(_html_item(item, monitoring=False))
        html_sections.append("</ul>")

    if monitoring_items:
        text_lines.extend([
            "2. CONCURSOS EM ACOMPANHAMENTO (PRÉ-EDITAL)",
            "=" * 60,
            "Os itens abaixo ainda não possuem cargo de TI confirmado.",
            "",
        ])
        html_sections.append(
            "<h3>2. Concursos em acompanhamento (pré-edital)</h3>"
            "<p>Os itens abaixo ainda não possuem cargo de TI confirmado.</p><ul>"
        )
        for item in monitoring_items:
            _append_text_item(text_lines, item, monitoring=True)
            html_sections.append(_html_item(item, monitoring=True))
        html_sections.append("</ul>")

    if total == 0:
        text_lines.append("Nenhuma publicação nova elegível para notificação.")
        html_sections.append("<p>Nenhuma publicação nova elegível para notificação.</p>")

    html_sections.append("</body></html>")
    message.set_content("\n".join(text_lines))
    message.add_alternative("".join(html_sections), subtype="html")
    return message


def send_pending_notifications():
    """
    Envia um e-mail consolidado.
    Só marca cada tipo de aviso depois que o Gmail confirma o envio.
    """
    load_dotenv()

    sender = os.getenv("GMAIL_ADDRESS", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
    recipient = os.getenv("NOTIFICATION_EMAIL", "").strip() or sender

    if not sender or not app_password or not recipient:
        print(
            "Notificações não configuradas. Defina GMAIL_ADDRESS, "
            "GMAIL_APP_PASSWORD e NOTIFICATION_EMAIL no arquivo .env."
        )
        return {
            "sent": 0,
            "notified": 0,
            "opportunities_notified": 0,
            "monitoring_notified": 0,
            "reason": "not_configured",
        }

    opportunity_items = get_unnotified_news()
    monitoring_items = get_unnotified_monitoring_news()

    if not opportunity_items and not monitoring_items:
        print("Nenhuma publicação nova elegível para notificação.")
        return {
            "sent": 0,
            "notified": 0,
            "opportunities_notified": 0,
            "monitoring_notified": 0,
            "reason": "no_news",
        }

    message = build_email(opportunity_items, monitoring_items)
    message["From"] = sender
    message["To"] = recipient

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(sender, app_password)
            server.send_message(message)

        for item in opportunity_items:
            mark_as_notified(item["id"])

        for item in monitoring_items:
            mark_as_monitoring_notified(item["id"])

        total_notified = len(opportunity_items) + len(monitoring_items)
        print(f"E-mail enviado para {recipient}.")
        print(f"Oportunidades de TI: {len(opportunity_items)}")
        print(f"Avisos de acompanhamento: {len(monitoring_items)}")

        return {
            "sent": 1,
            "notified": total_notified,
            "opportunities_notified": len(opportunity_items),
            "monitoring_notified": len(monitoring_items),
            "reason": "success",
        }

    except (smtplib.SMTPException, OSError) as error:
        print(f"Falha ao enviar e-mail: {error}")
        return {
            "sent": 0,
            "notified": 0,
            "opportunities_notified": 0,
            "monitoring_notified": 0,
            "reason": str(error),
        }
