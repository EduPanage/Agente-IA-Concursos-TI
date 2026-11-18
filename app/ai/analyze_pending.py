
from app.ai.classifier import NewsClassifier

from app.database.db import (
    initialize_database,
    get_pending_analysis,
    update_classification
)


def main():

    initialize_database()

    classifier = NewsClassifier()

    pending = get_pending_analysis(limit=20)

    print(f"Notícias pendentes: {len(pending)}")

    analyzed = 0
    failed = 0

    for news in pending:

        print(f"\nAnalisando: {news['title']}")

        result = classifier.classify({
            "title": news["title"],
            "summary": news["summary"],
            "location": news["location"],
            "source": news["source"]
        })

        if not result:
            failed += 1
            continue

        update_classification(news["id"], result)

        analyzed += 1

        print(f"Relevância: {result['relevance']}")
        print(f"Localidade: {result['location']}")
        print(f"Motivo: {result['reason']}")

    print("\nRESUMO")
    print(f"Analisadas: {analyzed}")
    print(f"Falhas: {failed}")
    print(f"Pendentes: {len(pending) - analyzed - failed}")


if __name__ == "__main__":
    main()
