
from app.database.db import (
    initialize_database,
    save_news,
    get_all_news,
    get_unnotified_news
)


def main():

    # Inicializar banco
    initialize_database()

    # Notícia fictícia para teste
    sample_news = [
        {
            "title": "Concurso de TI - Teste",
            "link": "https://exemplo.com/concurso-ti",
            "published": "2026-11-18T10:00:00+00:00",
            "summary": "Oportunidade fictícia para teste.",
            "source": "Teste",
            "location": "Dourados/MS",
            "search_query": "concurso TI Dourados"
        }
    ]

    # Salvar notícias
    result = save_news(sample_news)

    print("\nResultado da gravação:")
    print(result)

    # Consultar notícias
    news = get_all_news()

    print(f"\nTotal de notícias: {len(news)}")

    for item in news:
        print(f"{item['id']} - {item['title']}")

    # Consultar notificações pendentes
    pending = get_unnotified_news()

    print(f"\nNotícias não notificadas: {len(pending)}")


if __name__ == "__main__":
    main()
