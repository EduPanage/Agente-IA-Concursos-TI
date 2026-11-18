
from app.collectors.rss_collector import RSSCollector

from app.database.db import (
    initialize_database,
    save_news,
    get_pending_analysis,
    update_classification
)

from app.ai.classifier import NewsClassifier


def main():

    print("\n\n")
    print("=" * 55)
    print("AGENTE DE CONCURSOS TI - DOURADOS/MS")
    print("=" * 55)
    print("\n")

    # Inicializar banco
    initialize_database()

    # Executar pesquisas
    collector = RSSCollector()

    print("\nIniciando pesquisas...")

    results = collector.search()

    # Salvar notícias
    database_result = save_news(results)

    print(f"\nPublicações encontradas: {len(results)}")
    print(f"Novas notícias: {database_result['inserted']}")
    print(f"Notícias atualizadas: {database_result['updated']}")

    # Diagnóstico
    print("\nDIAGNÓSTICO DA PESQUISA")
    print("-" * 55)

    for key, value in collector.stats.items():
        print(f"{key}: {value}")

    # Inicializar IA
    classifier = NewsClassifier()

    # Buscar notícias pendentes
    pending_news = get_pending_analysis(limit=20)

    print("\nANÁLISE COM INTELIGÊNCIA ARTIFICIAL")
    print("-" * 55)

    print(f"Notícias pendentes: {len(pending_news)}")

    analyzed = 0
    failed = 0

    for news in pending_news:

        print(f"\nAnalisando: {news['title']}")

        news_data = {
            "title": news["title"],
            "summary": news["summary"],
            "location": news["location"],
            "source": news["source"]
        }

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
            print("Resposta incompleta da IA. Registro mantido pendente.")
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
        print(f"Motivo: {result['reason']}")

    print("\nRESUMO DA EXECUÇÃO")
    print("-" * 55)

    print(f"Notícias analisadas: {analyzed}")
    print(f"Falhas de análise: {failed}")
    print(f"Notícias ainda pendentes: {len(pending_news) - analyzed - failed}")

    print("\nExecução finalizada!")


if __name__ == "__main__":
    main()
