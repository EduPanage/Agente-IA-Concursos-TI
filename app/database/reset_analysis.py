
from app.database.db import get_connection


def main():

    with get_connection() as connection:

        cursor = connection.execute("""
            UPDATE noticias
            SET is_public_competition = NULL,
                has_it_opportunity = NULL,
                relevance = NULL,
                event_type = NULL,
                classification_reason = NULL,
                evidence = NULL,
                analysis_status = 'pending'
            WHERE analysis_status = 'completed'
        """)

        print(
            f"{cursor.rowcount} notícias "
            "voltaram para análise."
        )


if __name__ == "__main__":
    main()
