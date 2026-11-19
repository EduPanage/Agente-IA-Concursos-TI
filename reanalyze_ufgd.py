
from app.database.db import (
    initialize_database,
    get_connection,
    update_classification,
)
from app.collectors.page_reader import PageReader
from app.ai.classifier import NewsClassifier


NEWS_IDS = [185, 186]


def main():
    initialize_database()

    reader = PageReader()
    classifier = NewsClassifier()

    analyzed = 0
    failed = 0

    with get_connection() as connection:
        news_items = []

        for news_id in NEWS_IDS:
            news = connection.execute(
                "SELECT * FROM noticias WHERE id = ?",
                (news_id,),
            ).fetchone()

            if news is None:
                print(f"Registro {news_id} não encontrado.")
                continue

            news_items.append(dict(news))

    for news in news_items:
        print("\n" + "=" * 65)
        print(f"ID: {news['id']}")
        print(f"Publicação: {news['title']}")

        try:
            page = reader.read(news["link"])

            print(f"Extração: {page['status']}")
            print(f"Origem: {page['source_url']}")

            news_data = {
                "title": news["title"],
                "summary": news["summary"],
                "location": news["location"],
                "source": news["source"],
                "content": page["content"],
                "pdf_content": page["pdf_content"],
                "extraction_status": page["status"],
                "source_url": page["source_url"],
            }

            result = classifier.classify(news_data)

            if not result:
                print("Falha na classificação. Registro não alterado.")
                failed += 1
                continue

            required = [
                "is_public_competition",
                "has_it_opportunity",
                "location",
                "relevance",
                "event_type",
                "reason",
                "evidence",
            ]

            if not all(field in result for field in required):
                print("Classificação incompleta. Registro não alterado.")
                failed += 1
                continue

            update_classification(
                news["id"],
                result,
                extraction_status=page["status"],
                extraction_reason=page.get("reason", ""),
            )

            analyzed += 1

            print(f"Oportunidade de TI: {result['has_it_opportunity']}")
            print(f"Relevância: {result['relevance']}")
            print(f"Etapa: {result['event_type']}")
            print(f"Motivo: {result['reason']}")

        except Exception as error:
            print(f"Erro ao reanalisar ID {news['id']}: {error}")
            failed += 1

    print("\n" + "=" * 65)
    print("RESUMO DA REANÁLISE")
    print(f"Analisadas: {analyzed}")
    print(f"Falhas: {failed}")
    print("Notificações anteriores preservadas.")


if __name__ == "__main__":
    main()
