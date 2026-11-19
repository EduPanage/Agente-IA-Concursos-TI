
from app.database.db import get_connection

with get_connection() as connection:
    rows = connection.execute("""
        SELECT
            id,
            title,
            analysis_status,
            relevance,
            has_it_opportunity,
            notified_at,
            analysis_attempts
        FROM noticias
        WHERE title LIKE '%CCS%'
        ORDER BY id DESC
    """).fetchall()

    print(f"\nRegistros encontrados: {len(rows)}")

    for row in rows:
        print("\n" + "-" * 65)
        for key in row.keys():
            print(f"{key}: {row[key]}")
