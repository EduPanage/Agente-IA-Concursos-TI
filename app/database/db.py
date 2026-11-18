
import sqlite3

from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "concursos.db"


def get_connection():

    DATA_DIR.mkdir(exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    return connection


def initialize_database():

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

        # Migração para bancos já existentes
        existing_columns = {
            column["name"]
            for column in connection.execute(
                "PRAGMA table_info(noticias)"
            ).fetchall()
        }

        new_columns = {
            "is_public_competition": "INTEGER",
            "has_it_opportunity": "INTEGER",
            "relevance": "TEXT",
            "event_type": "TEXT",
            "classification_reason": "TEXT",
            "evidence": "TEXT",
            "analysis_status": "TEXT DEFAULT 'pending'"
        }

        for column, definition in new_columns.items():

            if column not in existing_columns:

                connection.execute(
                    f"ALTER TABLE noticias ADD COLUMN "
                    f"{column} {definition}"
                )

    print("Banco de dados inicializado com sucesso!")


def save_news(news_list):

    inserted = 0
    updated = 0
    new_news = []

    current_time = datetime.now(
        timezone.utc
    ).isoformat()

    with get_connection() as connection:

        for news in news_list:

            link = news.get("link")

            if not link:
                continue

            existing = connection.execute("""
                SELECT id FROM noticias
                WHERE link = ?
            """, (link,)).fetchone()

            if existing:

                connection.execute("""
                    UPDATE noticias
                    SET last_seen = ?,
                        title = ?,
                        summary = ?,
                        location = ?
                    WHERE link = ?
                """, (
                    current_time,
                    news.get("title", ""),
                    news.get("summary", ""),
                    news.get("location", ""),
                    link
                ))

                updated += 1

            else:

                connection.execute("""
                    INSERT INTO noticias (
                        title, link, published, summary,
                        source, location, search_query,
                        first_seen, last_seen,
                        analysis_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    news.get("title", ""),
                    link,
                    news.get("published", ""),
                    news.get("summary", ""),
                    news.get("source", ""),
                    news.get("location", ""),
                    news.get("search_query", ""),
                    current_time,
                    current_time,
                    "pending"
                ))

                inserted += 1
                new_news.append(news)

    return {
        "inserted": inserted,
        "updated": updated,
        "new_news": new_news
    }


def get_pending_analysis(limit=20):

    with get_connection() as connection:

        cursor = connection.execute("""
            SELECT *
            FROM noticias
            WHERE analysis_status = 'pending'
            ORDER BY published DESC
            LIMIT ?
        """, (limit,))

        return cursor.fetchall()



def update_classification(news_id, result):

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
            "completed",
            news_id
        ))



def get_all_news():

    with get_connection() as connection:

        return connection.execute("""
            SELECT *
            FROM noticias
            ORDER BY published DESC
        """).fetchall()


def get_unnotified_news():

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


def mark_as_notified(news_id):

    current_time = datetime.now(
        timezone.utc
    ).isoformat()

    with get_connection() as connection:

        connection.execute("""
            UPDATE noticias
            SET notified_at = ?
            WHERE id = ?
        """, (current_time, news_id))
