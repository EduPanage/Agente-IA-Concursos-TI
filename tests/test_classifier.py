
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

    def test_professor_de_informatica_nao_e_oportunidade(self):
        news = {
            "title": "Processo seletivo para Professor de Informática",
            "summary": "Vaga para Professor de Informática.",
            "content": "Cargo: Professor de Informática.",
            "extraction_status": "success",
        }

        result = self.classifier._apply_rules(
            self.result_base(), news
        )

        self.assertFalse(result["has_it_opportunity"])
        self.assertEqual(result["relevance"], "irrelevant")

    def test_professor_de_ciencia_da_computacao_nao_e_ti(self):
        news = {
            "title": "Concurso para Professor de Ciência da Computação",
            "summary": "Vagas para docentes.",
            "content": "Cargo: Professor de Ciência da Computação.",
            "extraction_status": "success",
        }

        result = self.classifier._apply_rules(
            self.result_base(), news
        )

        self.assertFalse(result["has_it_opportunity"])
        self.assertEqual(result["relevance"], "irrelevant")

    def test_analista_de_sistemas_continua_sendo_ti(self):
        news = {
            "title": "Concurso para Analista de Sistemas",
            "summary": "Vaga na área de Tecnologia da Informação.",
            "content": "Cargo: Analista de Sistemas.",
            "extraction_status": "success",
        }

        result = self.classifier._apply_rules(
            self.result_base(), news
        )

        self.assertTrue(result["has_it_opportunity"])

    def test_concurso_pre_edital_para_professores_e_irrelevante(self):
        news = {
            "title": "Concurso com 2 mil vagas para professores em MS",
            "summary": (
                "Concurso estadual para professores segue em preparação."
            ),
            "content": "Seleção para contratação de professores.",
            "extraction_status": "success",
        }

        result = self.classifier._apply_rules(
            self.result_base(), news
        )

        self.assertFalse(result["has_it_opportunity"])
        self.assertEqual(result["relevance"], "irrelevant")

    def test_concurso_docente_nao_gera_oportunidade_de_ti(self):
        news = {
            "title": "Processo seletivo para Professor de Informática",
            "summary": "Vaga para professor.",
            "content": "Cargo: Professor de Informática.",
            "extraction_status": "success",
        }

        result = self.classifier._apply_rules(
            self.result_base(), news
        )

        self.assertFalse(result["has_it_opportunity"])
        self.assertEqual(result["relevance"], "irrelevant")



    def test_cargo_em_historico_de_nomeacoes_nao_e_vaga_atual(self):
        news = {
            "title": "Concurso TJ-MS: comissão formada para novo edital",
            "summary": "Novo concurso em preparação.",
            "content": (
                "Confira o histórico dos últimos certames: "
                "Nomeações do TJ MS em 2024. "
                "Técnico de Nível Superior - Analista de Sistemas "
                "Computacionais - Analista de Sistemas - 17."
            ),
            "extraction_status": "success",
        }
        result = self.classifier._apply_rules(self.result_base(), news)
        self.assertFalse(result["has_it_opportunity"])
        self.assertEqual(result["relevance"], "needs_review")

    def test_tecnico_em_informatica_em_lista_de_vagas_e_ti(self):
        news = {
            "title": "Concursos em MS: vagas em prefeituras",
            "summary": "A Câmara oferece quatro vagas efetivas.",
            "content": (
                "A Câmara Municipal oferece quatro vagas efetivas e cadastro "
                "de reserva para controlador interno, técnico em informática, "
                "técnico legislativo e recepcionista."
            ),
            "extraction_status": "success",
        }
        result = self.classifier._apply_rules(self.result_base(), news)
        self.assertTrue(result["has_it_opportunity"])
        self.assertIn("técnico em informática", result["evidence"].lower())

    def test_seguranca_da_informacao_em_atribuicoes_nao_confirma_cargo(self):
        news = {
            "title": "Concurso ANPD: banca definida",
            "summary": "Edital previsto para dezembro.",
            "content": (
                "Entre as atribuições estão contribuir na formulação de "
                "políticas públicas de privacidade e segurança da informação, "
                "além de conduzir inspeções e auditorias."
            ),
            "extraction_status": "success",
        }
        result = self.classifier._apply_rules(self.result_base(), news)
        self.assertFalse(result["has_it_opportunity"])

    def test_evidencia_e_substituida_pelo_trecho_que_confirma_o_cargo(self):
        news = {
            "title": "Concurso para Analista de Tecnologia da Informação",
            "summary": "Vagas abertas.",
            "content": "Cargo: Analista de Tecnologia da Informação.",
            "extraction_status": "success",
        }
        result = self.classifier._apply_rules(self.result_base(), news)
        self.assertTrue(result["has_it_opportunity"])
        self.assertIn("Analista de Tecnologia da Informação", result["evidence"])
        self.assertNotEqual(result["evidence"], "O edital menciona cargo técnico.")

    def test_analista_de_sistemas_em_quadro_de_vagas_e_ti(self):
        news = {
            "title": "Concurso para cargos de nível superior",
            "summary": "Edital publicado.",
            "content": (
                "Quadro de vagas: 2 vagas para Analista de Sistemas e Métodos. "
                "Requisito: curso superior em Análise de Sistemas."
            ),
            "extraction_status": "success",
        }
        result = self.classifier._apply_rules(self.result_base(), news)
        self.assertTrue(result["has_it_opportunity"])


    def test_concurso_ifg_e_reconhecido_sem_publico(self):
        news = {
            "title": "Concurso IFG: vagas para Técnico de Tecnologia da Informação",
            "summary": "Seleção para cargos efetivos.",
            "content": "Cargo: Técnico de Tecnologia da Informação.",
            "extraction_status": "success",
        }
        result = self.classifier._apply_rules(self.result_base(), news)
        self.assertTrue(result["is_public_competition"])
        self.assertTrue(result["has_it_opportunity"])
        self.assertEqual(result["relevance"], "other_state")
        self.assertEqual(result["location"], "Goiás (GO)")

    def test_inb_nacional_nao_vira_rio_de_janeiro(self):
        news = {
            "title": "Concurso INB 2026: oportunidades para Analista de Sistemas",
            "summary": "Seleção de abrangência nacional.",
            "content": "Cargo: Analista de Sistemas. Unidade no Rio de Janeiro.",
            "extraction_status": "success",
        }
        result = self.classifier._apply_rules(self.result_base(), news)
        self.assertTrue(result["is_public_competition"])
        self.assertTrue(result["has_it_opportunity"])
        self.assertEqual(result["relevance"], "national_unknown")
        self.assertIn("Nacional", result["location"])

    def test_anpd_banca_definida_sem_cargo_ti_fica_em_revisao(self):
        news = {
            "title": "Concurso ANPD: banca Cebraspe será banca",
            "summary": "Edital previsto para dezembro.",
            "content": "Atuação com privacidade e segurança da informação.",
            "extraction_status": "success",
        }
        result = self.classifier._apply_rules(self.result_base(), news)
        self.assertTrue(result["is_public_competition"])
        self.assertFalse(result["has_it_opportunity"])
        self.assertEqual(result["event_type"], "banca_definida")
        self.assertEqual(result["relevance"], "needs_review")

    def test_mencao_a_rio_no_corpo_nao_define_estado(self):
        news = {
            "title": "Concurso nacional para Analista de Sistemas",
            "summary": "Seleção federal.",
            "content": "Cargo: Analista de Sistemas. Sede no Rio de Janeiro.",
            "extraction_status": "success",
        }
        result = self.classifier._apply_rules(self.result_base(), news)
        self.assertTrue(result["has_it_opportunity"])
        self.assertNotEqual(result["relevance"], "other_state")

    def test_mencao_a_professor_no_corpo_nao_anula_vaga_de_ti(self):
        news = {
            "title": "Concurso para Analista de Tecnologia da Informação",
            "summary": "Edital com cargos de diferentes áreas.",
            "content": "Cargo: Analista de Tecnologia da Informação. Também haverá professores.",
            "extraction_status": "success",
        }
        result = self.classifier._apply_rules(self.result_base(), news)
        self.assertTrue(result["has_it_opportunity"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
