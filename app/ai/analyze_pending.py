from app.ai.classifier import NewsClassifier
from app.collectors.page_reader import PageReader
from app.database.db import (
    initialize_database,
    get_pending_analysis,
    update_classification,
)


REQUIRED_FIELDS = (
    "is_public_competition",
    "has_it_opportunity",
    "location",
    "relevance",
    "event_type",
    "reason",
    "evidence",
)

ALLOWED_RELEVANCE = {
    "confirmed_dourados",
    "confirmed_ms",
    "national_unknown",
    "other_state",
    "needs_review",
    "irrelevant",
}


def validate_classification(result):
    """Confere a estrutura da resposta antes de gravá-la no banco."""
    if not isinstance(result, dict):
        return False

    if not all(field in result for field in REQUIRED_FIELDS):
        return False

    if not isinstance(result["is_public_competition"], bool):
        return False

    if not isinstance(result["has_it_opportunity"], bool):
        return False

    if result["relevance"] not in ALLOWED_RELEVANCE:
        return False

    return all(
        isinstance(result[field], str)
        for field in ("location", "event_type", "reason", "evidence")
    )


def analyze_pending(limit=20):
    """
    Analisa notícias pendentes usando o conteúdo da página original e PDFs.
    Retorna um resumo da execução para que main.py possa reutilizá-lo.
    """
    initialize_database()

    classifier = NewsClassifier()
    reader = PageReader()

    pending = get_pending_analysis(limit=limit)

    print(f"\nNotícias pendentes: {len(pending)}")

    analyzed = 0
    failed = 0
    extraction_errors = 0

    for news in pending:
        print("\n" + "=" * 60)
        print(f"Analisando: {news['title']}")

        # Uma falha de leitura não impede a análise do título e do resumo.
        try:
            page = reader.read(news["link"])
        except Exception as error:
            extraction_errors += 1
            print(f"Falha inesperada na leitura da publicação: {error}")
            page = {
                "content": "",
                "pdf_content": "",
                "pdf_links": [],
                "status": "failed",
                "source_url": None,
            }

        print(f"Leitura da publicação: {page.get('status', 'unknown')}")

        if page.get("pdf_links"):
            print(f"Editais encontrados: {len(page['pdf_links'])}")

        news_data = {
            "title": news["title"],
            "summary": news["summary"] or "",
            "location": news["location"] or "",
            "source": news["source"] or "",
            "content": page.get("content", ""),
            "pdf_content": page.get("pdf_content", ""),
            "extraction_status": page.get("status", "unknown"),
            "source_url": page.get("source_url"),
        }

        print(f"Origem identificada: {news_data['source_url'] or 'Não identificada'}")

        result = classifier.classify(news_data)

        if not validate_classification(result):
            failed += 1
            print("Classificação inválida ou incompleta. Registro mantido pendente.")
            continue

        update_classification(news["id"], result)
        analyzed += 1

        print(f"Relevância: {result['relevance']}")
        print(f"Localidade: {result['location']}")
        print(f"Motivo: {result['reason']}")

    summary = {
        "pending": len(pending),
        "analyzed": analyzed,
        "failed": failed,
        "extraction_errors": extraction_errors,
        "remaining_in_batch": len(pending) - analyzed - failed,
    }

    print("\n" + "=" * 60)
    print("RESUMO DA ANÁLISE")
    print(f"Analisadas: {summary['analyzed']}")
    print(f"Falhas de classificação: {summary['failed']}")
    print(f"Falhas de extração: {summary['extraction_errors']}")
    print(f"Pendentes nesta execução: {summary['remaining_in_batch']}")

    return summary


if __name__ == "__main__":
    analyze_pending()
