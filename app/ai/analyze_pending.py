from app.ai.classifier import NewsClassifier
from app.collectors.page_reader import PageReader
from app.database.db import (
    initialize_database,
    get_pending_analysis,
    update_classification,
    mark_analysis_failure,
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
    initialize_database()

    classifier = NewsClassifier()
    reader = PageReader()
    pending = get_pending_analysis(limit=limit)

    print(f"\nNotícias pendentes: {len(pending)}")

    analyzed = 0
    needs_review = 0
    failed = 0
    extraction_errors = 0

    for news in pending:
        print("\n" + "=" * 60)
        print(f"Analisando: {news['title']}")

        try:
            page = reader.read(news["link"])
        except Exception as error:
            page = {
                "content": "",
                "pdf_content": "",
                "pdf_links": [],
                "status": "failed",
                "source_url": None,
                "reason": f"Erro inesperado na leitura: {error}",
            }

        extraction_status = page.get("status", "unknown")
        extraction_reason = page.get("reason", "") or ""
        content = page.get("content", "") or ""
        pdf_content = page.get("pdf_content", "") or ""
        has_source_text = bool(content.strip() or pdf_content.strip())

        print(f"Status da extração: {extraction_status}")
        print(f"Origem identificada: {page.get('source_url') or 'Não identificada'}")

        if page.get("pdf_links"):
            print(f"Editais encontrados: {len(page['pdf_links'])}")

        if not has_source_text:
            extraction_errors += 1
            print(
                "ATENÇÃO: sem conteúdo original. A classificação poderá "
                "usar somente título e resumo e ficará para revisão."
            )

        news_data = {
            "title": news["title"] or "",
            "summary": news["summary"] or "",
            "location": news["location"] or "",
            "source": news["source"] or "",
            "content": content,
            "pdf_content": pdf_content,
            "extraction_status": extraction_status,
            "source_url": page.get("source_url"),
        }

        try:
            result = classifier.classify(news_data)
        except Exception as error:
            result = None
            print(f"Erro inesperado no classificador: {error}")

        if not validate_classification(result):
            failed += 1
            mark_analysis_failure(
                news["id"],
                "Classificador indisponível ou resposta inválida. "
                + extraction_reason,
                extraction_status=(
                    extraction_status if extraction_status else "unknown"
                ),
            )
            print("Registro enviado para revisão; não será notificado.")
            continue

        # Uma extração sem texto nunca é considerada conclusão confiável,
        # mesmo que a IA tenha retornado 'irrelevant'.
        must_review = (
            not has_source_text
            or result["relevance"] == "needs_review"
        )

        final_status = "needs_review" if must_review else "completed"

        update_classification(
            news["id"],
            result,
            extraction_status=extraction_status,
            extraction_reason=extraction_reason,
            analysis_status=final_status,
        )

        if must_review:
            needs_review += 1
        else:
            analyzed += 1

        print(f"Relevância: {result['relevance']}")
        print(f"Localidade: {result['location']}")
        print(f"Motivo: {result['reason']}")
        print(f"Situação no banco: {final_status}")

    summary = {
        "pending": len(pending),
        "completed": analyzed,
        "needs_review": needs_review,
        "failed": failed,
        "extraction_errors": extraction_errors,
    }

    print("\n" + "=" * 60)
    print("RESUMO DA ANÁLISE")
    print(f"Concluídas: {analyzed}")
    print(f"Para revisão: {needs_review}")
    print(f"Falhas de classificação: {failed}")
    print(f"Falhas de extração: {extraction_errors}")

    return summary


def main():
    analyze_pending(limit=20)


if __name__ == "__main__":
    main()
