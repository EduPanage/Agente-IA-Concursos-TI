import sqlite3
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "concursos.db"

PRE_EDICTAL_EVENTS = (
    "previsto",
    "solicitado",
    "autorizado",
    "comissao_formada",
    "banca_definida",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    """Cria a tabela e aplica migrações aditivas, sem apagar registros."""
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS noticias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                link TEXT UNIQUE NOT NULL,
                published TEXT,
                summary TEXT,
                source TEXT,
                location TEXT,
                search_query TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                notified_at TEXT,
                is_public_competition INTEGER,
                has_it_opportunity INTEGER,
                relevance TEXT,
                event_type TEXT,
                classification_reason TEXT,
                evidence TEXT,
                analysis_status TEXT DEFAULT 'pending'
            )
        """)

        existing_columns = {
            column["name"]
            for column in connection.execute(
                "PRAGMA table_info(noticias)"
            ).fetchall()
        }

        migrations = {
            "is_public_competition": "INTEGER",
            "has_it_opportunity": "INTEGER",
            "relevance": "TEXT",
            "event_type": "TEXT",
            "classification_reason": "TEXT",
            "evidence": "TEXT",
            "analysis_status": "TEXT DEFAULT 'pending'",
            "extraction_status": "TEXT",
            "extraction_reason": "TEXT",
            "analysis_attempts": "INTEGER NOT NULL DEFAULT 0",
            "last_analysis_at": "TEXT",
            # Controle separado para avisos de acompanhamento pré-edital.
            "monitoring_notified_at": "TEXT",
        }

        for column, definition in migrations.items():
            if column not in existing_columns:
                connection.execute(
                    f"ALTER TABLE noticias ADD COLUMN {column} {definition}"
                )

        connection.execute("""
            UPDATE noticias
            SET analysis_status = 'pending'
            WHERE analysis_status IS NULL OR TRIM(analysis_status) = ''
        """)

    print("\nBanco de dados inicializado com sucesso!")


def save_news(news_list):
    inserted = 0
    updated = 0
    new_news = []
    current_time = utc_now()

    with get_connection() as connection:
        for news in news_list:
            link = news.get("link")
            if not link:
                continue

            existing = connection.execute(
                "SELECT id FROM noticias WHERE link = ?",
                (link,),
            ).fetchone()

            if existing:
                # Não sobrescreve a classificação nem dados de origem
                # com campos vazios vindos de uma nova coleta.
                connection.execute("""
                    UPDATE noticias
                    SET last_seen = ?,
                        title = CASE WHEN ? <> '' THEN ? ELSE title END,
                        summary = CASE WHEN ? <> '' THEN ? ELSE summary END,
                        location = CASE WHEN ? <> '' THEN ? ELSE location END,
                        published = CASE WHEN ? <> '' THEN ? ELSE published END,
                        source = CASE WHEN ? <> '' THEN ? ELSE source END,
                        search_query = CASE WHEN ? <> '' THEN ? ELSE search_query END
                    WHERE link = ?
                """, (
                    current_time,
                    news.get("title") or "", news.get("title") or "",
                    news.get("summary") or "", news.get("summary") or "",
                    news.get("location") or "", news.get("location") or "",
                    news.get("published") or "", news.get("published") or "",
                    news.get("source") or "", news.get("source") or "",
                    news.get("search_query") or "", news.get("search_query") or "",
                    link,
                ))
                updated += 1
            else:
                connection.execute("""
                    INSERT INTO noticias (
                        title, link, published, summary, source, location,
                        search_query, first_seen, last_seen, analysis_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """, (
                    news.get("title") or "",
                    link,
                    news.get("published") or "",
                    news.get("summary") or "",
                    news.get("source") or "",
                    news.get("location") or "",
                    news.get("search_query") or "",
                    current_time,
                    current_time,
                ))
                inserted += 1
                new_news.append(news)

    return {
        "inserted": inserted,
        "updated": updated,
        "new_news": new_news,
    }


def get_pending_analysis(limit=20):
    with get_connection() as connection:
        return connection.execute("""
            SELECT *
            FROM noticias
            WHERE analysis_status = 'pending'
            ORDER BY
                CASE WHEN published IS NULL OR published = '' THEN 1 ELSE 0 END,
                published DESC,
                id DESC
            LIMIT ?
        """, (max(1, int(limit)),)).fetchall()


def get_review_news(limit=100):
    """Retorna registros que exigem revisão humana."""
    with get_connection() as connection:
        return connection.execute("""
            SELECT *
            FROM noticias
            WHERE analysis_status = 'needs_review'
            ORDER BY last_seen DESC
            LIMIT ?
        """, (max(1, int(limit)),)).fetchall()


def update_classification(news_id, result, extraction_status=None,
                          extraction_reason="", analysis_status=None):
    """
    Salva a classificação e o estado real da análise.
    analysis_status aceito: completed ou needs_review.
    """
    status = analysis_status or (
        "needs_review"
        if result.get("relevance") == "needs_review"
        else "completed"
    )
    if status not in {"completed", "needs_review"}:
        raise ValueError("analysis_status deve ser completed ou needs_review.")

    with get_connection() as connection:
        connection.execute("""
            UPDATE noticias
            SET is_public_competition = ?,
                has_it_opportunity = ?,
                location = ?,
                relevance = ?,
                event_type = ?,
                classification_reason = ?,
                evidence = ?,
                extraction_status = COALESCE(?, extraction_status),
                extraction_reason = ?,
                analysis_attempts = COALESCE(analysis_attempts, 0) + 1,
                last_analysis_at = ?,
                analysis_status = ?
            WHERE id = ?
        """, (
            int(result["is_public_competition"]),
            int(result["has_it_opportunity"]),
            result["location"],
            result["relevance"],
            result["event_type"],
            result["reason"],
            result["evidence"],
            extraction_status,
            extraction_reason or "",
            utc_now(),
            status,
            news_id,
        ))


def mark_analysis_failure(news_id, reason, extraction_status="failed"):
    """Evita loop infinito de falhas; mantém o item visível para revisão."""
    with get_connection() as connection:
        connection.execute("""
            UPDATE noticias
            SET extraction_status = ?,
                extraction_reason = ?,
                analysis_attempts = COALESCE(analysis_attempts, 0) + 1,
                last_analysis_at = ?,
                analysis_status = 'needs_review'
            WHERE id = ?
        """, (
            extraction_status,
            reason or "Falha não especificada.",
            utc_now(),
            news_id,
        ))


def requeue_news(news_ids):
    """Recoloca IDs selecionados na fila, preservando o histórico de tentativas."""
    ids = list(dict.fromkeys(int(item) for item in news_ids))
    if not ids:
        return 0

    placeholders = ",".join("?" for _ in ids)
    with get_connection() as connection:
        cursor = connection.execute(
            f"""
            UPDATE noticias
            SET analysis_status = 'pending'
            WHERE id IN ({placeholders})
              AND analysis_status = 'needs_review'
            """,
            ids,
        )
        return cursor.rowcount


def get_all_news():
    with get_connection() as connection:
        return connection.execute("""
            SELECT *
            FROM noticias
            ORDER BY published DESC
        """).fetchall()


def get_unnotified_news():
    """Vagas de TI já identificadas; mantém notified_at por compatibilidade."""
    with get_connection() as connection:
        return connection.execute("""
            SELECT *
            FROM noticias
            WHERE notified_at IS NULL
              AND analysis_status = 'completed'
              AND is_public_competition = 1
              AND has_it_opportunity = 1
              AND relevance IN (
                  'confirmed_dourados',
                  'confirmed_ms',
                  'national_unknown'
              )
            ORDER BY published DESC
        """).fetchall()


def get_unnotified_monitoring_news():
    """
    Concursos em fase pré-edital sem cargo de TI confirmado.
    São avisos de acompanhamento, não oportunidades confirmadas.
    """
    placeholders = ",".join("?" for _ in PRE_EDICTAL_EVENTS)
    with get_connection() as connection:
        return connection.execute(f"""
            SELECT *
            FROM noticias
            WHERE monitoring_notified_at IS NULL
              AND is_public_competition = 1
              AND COALESCE(has_it_opportunity, 0) = 0
              AND relevance = 'needs_review'
              AND (
                    location IS NULL OR TRIM(location) = ''
                    OR location IN ('Não identificada', 'Nao identificada', 'Localidade a verificar')
                    OR location LIKE '%Mato Grosso do Sul%'
                    OR location LIKE '%(MS)%'
                    OR location LIKE '%/MS%'
              )
              AND event_type IN ({placeholders})
              AND analysis_status IN ('completed', 'needs_review')
            ORDER BY published DESC
        """, PRE_EDICTAL_EVENTS).fetchall()


def mark_as_notified(news_id):
    """Marca o envio de uma oportunidade de TI confirmada."""
    with get_connection() as connection:
        connection.execute("""
            UPDATE noticias
            SET notified_at = ?
            WHERE id = ?
              AND notified_at IS NULL
        """, (utc_now(), news_id))


def mark_as_monitoring_notified(news_id):
    """Marca separadamente o envio de um aviso de acompanhamento."""
    with get_connection() as connection:
        connection.execute("""
            UPDATE noticias
            SET monitoring_notified_at = ?
            WHERE id = ?
              AND monitoring_notified_at IS NULL
        """, (utc_now(), news_id))
