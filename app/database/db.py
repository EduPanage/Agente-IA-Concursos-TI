
import sqlite3

from pathlib import Path
from datetime import datetime, timezone


# Caminho do banco de dados
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "concursos.db"


def get_connection():
    """Cria e retorna uma conexão com o SQLite."""

    DATA_DIR.mkdir(exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    return connection


def initialize_database():
    """Cria as tabelas necessárias para o agente."""

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
                notified_at TEXT
            )
        """)

    print("Banco de dados inicializado com sucesso!")


def save_news(news_list):
    """Armazena notícias e atualiza aquelas já existentes."""

    inserted = 0
    updated = 0

    current_time = datetime.now(
        timezone.utc
    ).isoformat()

    with get_connection() as connection:

        for news in news_list:

            link = news.get("link")

            if not link:
                continue

            cursor = connection.execute("""
                SELECT id FROM noticias
                WHERE link = ?
            """, (link,))

            existing = cursor.fetchone()

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
                        title,
                        link,
                        published,
                        summary,
                        source,
                        location,
                        search_query,
                        first_seen,
                        last_seen
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    news.get("title", ""),
                    link,
                    news.get("published", ""),
                    news.get("summary", ""),
                    news.get("source", ""),
                    news.get("location", ""),
                    news.get("search_query", ""),
                    current_time,
                    current_time
                ))

                inserted += 1

    return {
        "inserted": inserted,
        "updated": updated
    }


def get_all_news():
    """Retorna todas as notícias armazenadas."""

    with get_connection() as connection:

        cursor = connection.execute("""
            SELECT *
            FROM noticias
            ORDER BY published DESC
        """)

        return cursor.fetchall()


def get_unnotified_news():
    """Retorna notícias que ainda não foram notificadas."""

    with get_connection() as connection:

        cursor = connection.execute("""
            SELECT *
            FROM noticias
            WHERE notified_at IS NULL
            ORDER BY published DESC
        """)

        return cursor.fetchall()


def mark_as_notified(news_id):
    """Registra que uma notícia foi notificada."""

    current_time = datetime.now(
        timezone.utc
    ).isoformat()

    with get_connection() as connection:

        connection.execute("""
            UPDATE noticias
            SET notified_at = ?
            WHERE id = ?
        """, (current_time, news_id))
