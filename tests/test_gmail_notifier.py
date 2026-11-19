import unittest
from email.message import EmailMessage

from app.notifications.gmail_notifier import build_email


class TestBuildEmail(unittest.TestCase):

    def setUp(self):
        self.opportunity = {
            "id": 1,
            "title": "Concurso - Analista de Tecnologia da Informação",
            "link": "https://example.org/edital-ti",
            "location": "Dourados/MS",
            "relevance": "confirmed_dourados",
            "event_type": "edital_publicado",
            "classification_reason": "Lotação em Dourados expressamente indicada.",
        }
        self.monitoring = {
            "id": 2,
            "title": "Comissão organizadora formada",
            "link": "https://example.org/comissao",
            "location": "Mato Grosso do Sul (MS); lotação a confirmar",
            "relevance": "needs_review",
            "event_type": "comissao_formada",
            "classification_reason": "Ainda não há cargos definidos.",
        }

    def test_email_separa_vaga_confirmada_de_pre_edital(self):
        message = build_email([self.opportunity], [self.monitoring])

        self.assertIsInstance(message, EmailMessage)
        self.assertIn("1 vaga(s) identificada(s)", message["Subject"])
        self.assertIn("1 aviso(s) de acompanhamento", message["Subject"])

        body = message.get_body(preferencelist=("plain",)).get_content()
        self.assertIn("OPORTUNIDADES COM CARGOS DE TI IDENTIFICADOS", body)
        self.assertIn("CONCURSOS EM ACOMPANHAMENTO (PRÉ-EDITAL)", body)
        self.assertIn("cargo de TI ainda não confirmado", body)
        self.assertIn("Analista de Tecnologia da Informação", body)

    def test_email_com_apenas_acompanhamento(self):
        message = build_email([], [self.monitoring])
        body = message.get_body(preferencelist=("plain",)).get_content()

        self.assertIn("1 aviso(s) de acompanhamento", message["Subject"])
        self.assertNotIn("Analista de Tecnologia da Informação", body)
        self.assertIn("Comissão organizadora formada", body)

    def test_email_com_apenas_vaga_confirmada(self):
        message = build_email([self.opportunity], [])
        body = message.get_body(preferencelist=("plain",)).get_content()

        self.assertIn("1 vaga(s) identificada(s)", message["Subject"])
        self.assertIn("Dourados/MS", body)
        self.assertNotIn("pré-edital", body.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
