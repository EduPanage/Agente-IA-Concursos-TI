
import unittest

from app.ai.classifier import NewsClassifier


class TestNewsClassifierRules(unittest.TestCase):

    def setUp(self):
        self.classifier = NewsClassifier()

    def result_base(self):
        return {
            "is_public_competition": True,
            "has_it_opportunity": True,
            "location": "Dourados/MS",
            "relevance": "confirmed_dourados",
            "event_type": "edital_publicado",
            "reason": "Classificação inicial do modelo.",
            "evidence": "O edital menciona cargo técnico.",
        }

    def test_libras_nao_e_oportunidade_de_ti(self):
        news = {
            "title": "Edital para Técnicos Especializados em Libras",
            "summary": "Processo seletivo UFGD.",
            "content": "Vagas para Técnico Especializado em Libras.",
            "extraction_status": "success",
        }

        result = self.classifier._apply_rules(
            self.result_base(), news
        )

        self.assertFalse(result["has_it_opportunity"])
        self.assertEqual(result["relevance"], "irrelevant")

    def test_analista_de_ti_e_oportunidade_de_ti(self):
        news = {
            "title": "Concurso para Analista de Tecnologia da Informação",
            "summary": "Vagas para Analista de TI.",
            "content": "Cargo: Analista de Tecnologia da Informação.",
            "extraction_status": "success",
        }

        result = self.classifier._apply_rules(
            self.result_base(), news
        )

        self.assertTrue(result["has_it_opportunity"])

    def test_mencao_secundaria_a_informatica_nao_e_ti(self):
        news = {
            "title": "Concurso para cargos administrativos",
            "summary": "Edital com vagas para área administrativa.",
            "content": (
                "Os candidatos deverão possuir conhecimentos básicos "
                "de informática para utilizar os sistemas da instituição."
            ),
            "extraction_status": "success",
        }

        result = self.classifier._apply_rules(
            self.result_base(), news
        )

        self.assertFalse(result["has_it_opportunity"])
        self.assertEqual(result["relevance"], "irrelevant")

    def test_comissao_formada_sem_cargos_definidos_fica_em_revisao(self):
        news = {
            "title": "Concurso TJ-MS: comissão formada para novo edital",
            "summary": "Comissão organizadora formada.",
            "content": "O edital será publicado futuramente.",
            "extraction_status": "success",
        }

        result = self.classifier._apply_rules(
            self.result_base(), news
        )

        self.assertTrue(result["is_public_competition"])
        self.assertFalse(result["has_it_opportunity"])
        self.assertEqual(result["relevance"], "needs_review")
        self.assertEqual(result["event_type"], "comissao_formada")

    def test_edital_completo_sem_cargos_de_ti_e_irrelevante(self):
        news = {
            "title": "Edital de concurso para cargos administrativos",
            "summary": "Edital publicado com vagas administrativas.",
            "content": (
                "Cargos disponíveis: Assistente Administrativo, "
                "Auxiliar de Serviços Gerais e Contador."
            ),
            "extraction_status": "success",
        }

        result = self.classifier._apply_rules(
            self.result_base(), news
        )

        self.assertTrue(result["is_public_competition"])
        self.assertFalse(result["has_it_opportunity"])
        self.assertEqual(result["relevance"], "irrelevant")

    def test_vaga_de_ti_com_lotacao_em_dourados(self):
        news = {
            "title": "Concurso para Analista de Tecnologia da Informação",
            "summary": "Vaga com lotação em Dourados/MS.",
            "content": (
                "Cargo: Analista de Tecnologia da Informação. "
                "Local de exercício: Dourados/MS."
            ),
            "extraction_status": "success",
        }

        result = self.classifier._apply_rules(
            self.result_base(), news
        )

        self.assertTrue(result["has_it_opportunity"])
        self.assertEqual(result["relevance"], "confirmed_dourados")

    def test_instituicao_de_dourados_nao_comprova_lotacao(self):
        news = {
            "title": "Concurso UFGD para Analista de Tecnologia da Informação",
            "summary": "Concurso da Universidade Federal da Grande Dourados.",
            "content": (
                "Cargo: Analista de Tecnologia da Informação. "
                "A lotação será definida posteriormente."
            ),
            "extraction_status": "success",
        }

        result = self.classifier._apply_rules(
            self.result_base(), news
        )

        self.assertTrue(result["has_it_opportunity"])
        self.assertNotEqual(
            result["relevance"], "confirmed_dourados"
        )


    def test_vaga_de_ti_com_lotacao_em_ms_comprovada(self):
        news = {
            "title": "Concurso UFMS para Analista de Tecnologia da Informação",
            "summary": "Edital da Universidade Federal de Mato Grosso do Sul.",
            "content": (
                "Cargo: Analista de Tecnologia da Informação. "
                "Local de exercício: Campo Grande/MS."
            ),
            "extraction_status": "success",
        }
        result = self.result_base()
        result["location"] = "Mato Grosso do Sul"
        result["relevance"] = "confirmed_ms"

        result = self.classifier._apply_rules(result, news)

        self.assertTrue(result["has_it_opportunity"])
        self.assertEqual(result["relevance"], "confirmed_ms")

    def test_instituicao_de_ms_nao_comprova_lotacao_no_estado(self):
        news = {
            "title": "Concurso UFMS para Analista de Tecnologia da Informação",
            "summary": "Universidade Federal de Mato Grosso do Sul.",
            "content": (
                "Cargo: Analista de Tecnologia da Informação. "
                "A lotação será definida posteriormente."
            ),
            "extraction_status": "success",
        }
        result = self.result_base()
        result["location"] = "Mato Grosso do Sul"
        result["relevance"] = "confirmed_ms"

        result = self.classifier._apply_rules(result, news)

        self.assertTrue(result["has_it_opportunity"])
        self.assertEqual(result["relevance"], "needs_review")
        self.assertIn("lotação a confirmar", result["location"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
