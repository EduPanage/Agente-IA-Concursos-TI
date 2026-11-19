import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.database import db


class TestDatabase(unittest.TestCase):
    """Testes isolados: nenhum registro é gravado no banco real do projeto."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "test_concursos.db"
        self.data_dir_patch = patch.object(db, "DATA_DIR", self.temp_path)
        self.db_path_patch = patch.object(db, "DB_PATH", self.db_path)
        self.data_dir_patch.start()
        self.db_path_patch.start()
        db.initialize_database()

    def tearDown(self):
        self.db_path_patch.stop()
        self.data_dir_patch.stop()
        self.temp_dir.cleanup()

    def criar_noticia(self, link="https://exemplo.com/concurso-ti", **extra):
        noticia = {
            "title": "Concurso de TI - Teste",
            "link": link,
            "published": "2026-11-18T10:00:00+00:00",
            "summary": "Oportunidade fictícia para teste.",
            "source": "Teste",
            "location": "Dourados/MS",
            "search_query": "concurso TI Dourados",
        }
        noticia.update(extra)
        return noticia

    def classificar_como_vaga_ti(self, news_id):
        db.update_classification(news_id, {
            "is_public_competition": True,
            "has_it_opportunity": True,
            "location": "Dourados/MS",
            "relevance": "confirmed_dourados",
            "event_type": "edital_publicado",
            "reason": "Vaga de TI confirmada.",
            "evidence": "Analista de TI",
        })

    def test_inicializa_banco_e_cria_todas_as_colunas(self):
        with db.get_connection() as connection:
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(noticias)")
            }
        expected = {
            "id", "title", "link", "published", "summary", "source",
            "location", "search_query", "first_seen", "last_seen",
            "notified_at", "is_public_competition", "has_it_opportunity",
            "relevance", "event_type", "classification_reason", "evidence",
            "analysis_status", "extraction_status", "extraction_reason",
            "analysis_attempts", "last_analysis_at", "monitoring_notified_at",
        }
        self.assertTrue(expected.issubset(columns))

    def test_salva_noticia_e_impede_duplicidade_por_link(self):
        first = db.save_news([self.criar_noticia()])
        second = db.save_news([self.criar_noticia(
            title="Título atualizado", summary="Resumo atualizado"
        )])
        self.assertEqual(first["inserted"], 1)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(second["updated"], 1)
        news = db.get_all_news()
        self.assertEqual(len(news), 1)
        self.assertEqual(news[0]["title"], "Título atualizado")
        self.assertEqual(news[0]["analysis_status"], "pending")

    def test_noticia_nova_entra_na_fila_de_analise(self):
        db.save_news([self.criar_noticia()])
        pending = db.get_pending_analysis()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["analysis_status"], "pending")

    def test_classificacao_confirmada_aparece_na_fila_de_notificacao(self):
        db.save_news([self.criar_noticia()])
        news_id = db.get_all_news()[0]["id"]
        self.classificar_como_vaga_ti(news_id)
        pending = db.get_unnotified_news()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], news_id)
        self.assertEqual(pending[0]["analysis_status"], "completed")

    def test_item_em_revisao_nao_e_vaga_confirmada(self):
        db.save_news([self.criar_noticia()])
        news_id = db.get_all_news()[0]["id"]
        db.update_classification(news_id, {
            "is_public_competition": True,
            "has_it_opportunity": False,
            "location": "Mato Grosso do Sul",
            "relevance": "needs_review",
            "event_type": "previsto",
            "reason": "Concurso previsto, sem cargos definidos.",
            "evidence": "Comissão formada",
        })
        self.assertEqual(db.get_unnotified_news(), [])
        self.assertEqual(len(db.get_unnotified_monitoring_news()), 1)

    def test_falha_e_reprocessamento_preservam_historico(self):
        db.save_news([self.criar_noticia()])
        news_id = db.get_all_news()[0]["id"]
        db.mark_analysis_failure(news_id, "Falha simulada.")
        item = db.get_review_news()[0]
        self.assertEqual(item["analysis_status"], "needs_review")
        self.assertEqual(item["analysis_attempts"], 1)
        affected = db.requeue_news([news_id, news_id])
        item = db.get_pending_analysis()[0]
        self.assertEqual(affected, 1)
        self.assertEqual(item["analysis_status"], "pending")
        self.assertEqual(item["analysis_attempts"], 1)

    def test_nao_reprocessa_id_que_nao_esta_em_revisao(self):
        db.save_news([self.criar_noticia()])
        news_id = db.get_all_news()[0]["id"]
        self.assertEqual(db.requeue_news([news_id]), 0)

    def test_marca_notificacao_e_remove_item_da_fila(self):
        db.save_news([self.criar_noticia()])
        news_id = db.get_all_news()[0]["id"]
        self.classificar_como_vaga_ti(news_id)
        db.mark_as_notified(news_id)
        self.assertEqual(db.get_unnotified_news(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
