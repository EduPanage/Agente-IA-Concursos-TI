
from app.ai.classifier import NewsClassifier

from app.collectors.page_reader import PageReader

from app.database.db import (
    initialize_database,
    get_pending_analysis,
    update_classification
)


def main():

    initialize_database()

    classifier = NewsClassifier()
    reader = PageReader()

    pending = get_pending_analysis(limit=20)

    print(f"\nNotícias pendentes: {len(pending)}")

    analyzed = 0
    failed = 0

    for news in pending:

        print("\n" + "=" * 60)
        print(f"Analisando: {news['title']}")

        # Consultar publicação original
        page = reader.read(news["link"])

        print(f"Leitura da publicação: {page['status']}")

        if page["pdf_links"]:
            print(f"Editais encontrados: {len(page['pdf_links'])}")

        
        news_data = {
            "title": news["title"],
            "summary": news["summary"],
            "location": news["location"],
            "source": news["source"],
            "content": page["content"],
            "pdf_content": page["pdf_content"],
            "extraction_status": page["status"],
            "source_url": page["source_url"]
        }

        print(f"Status da extração: {page['status']}")
        print(f"Origem identificada: {page['source_url']}")


        result = classifier.classify(news_data)

        if not result:
            failed += 1
            continue

        required_fields = [
            "is_public_competition",
            "has_it_opportunity",
            "location",
            "relevance",
            "event_type",
            "reason",
            "evidence"
        ]

        if not all(field in result for field in required_fields):
            failed += 1
            continue

        if not isinstance(result["is_public_competition"], bool):
            failed += 1
            continue

        if not isinstance(result["has_it_opportunity"], bool):
            failed += 1
            continue

        update_classification(news["id"], result)

        analyzed += 1

        print(f"Relevância: {result['relevance']}")
        print(f"Localidade: {result['location']}")
        print(f"Motivo: {result['reason']}")

    print("\n" + "=" * 60)
    print("RESUMO DA ANÁLISE")
    print(f"Analisadas: {analyzed}")
    print(f"Falhas: {failed}")
    print(f"Pendentes nesta execução: {len(pending) - analyzed - failed}")


if __name__ == "__main__":
    main()
