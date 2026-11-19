"""
Reanalisa somente os registros selecionados, sem disparar notificações.

Execute na raiz do projeto:
    python reanalyze_selected.py

O script pede confirmação antes de gravar cada resultado.
Não altera notified_at nem monitoring_notified_at.
"""

from app.ai.classifier import NewsClassifier
from app.collectors.page_reader import PageReader
from app.database.db import (
    initialize_database,
    get_connection,
    update_classification,
    mark_analysis_failure,
)

NEWS_IDS = (201, 125, 124, 121, 120, 109)


def get_selected_news():
    placeholders = ",".join("?" for _ in NEWS_IDS)
    with get_connection() as connection:
        return connection.execute(
            f"""
            SELECT *
            FROM noticias
            WHERE id IN ({placeholders})
            ORDER BY id
            """,
            NEWS_IDS,
        ).fetchall()


def main():
    initialize_database()

    news_items = get_selected_news()
    found_ids = {item["id"] for item in news_items}
    missing_ids = sorted(set(NEWS_IDS) - found_ids)

    print("\nREANÁLISE DIRECIONADA")
    print(f"Registros encontrados: {len(news_items)}")
    if missing_ids:
        print(f"IDs não encontrados: {missing_ids}")

    if not news_items:
        print("Nenhum registro encontrado. Encerrando.")
        return

    print("\nRegistros selecionados:")
    for item in news_items:
        print(f"  ID {item['id']}: {item['title']}")
        print(
            f"    Status atual: {item['analysis_status']} | "
            f"TI: {item['has_it_opportunity']} | "
            f"Relevância: {item['relevance']}"
        )

    confirmation = input(
        "\nConfirma reanalisar SOMENTE esses registros? Digite SIM: "
    ).strip()

    if confirmation != "SIM":
        print("Operação cancelada. Nenhum registro foi alterado.")
        return

    classifier = NewsClassifier()
    reader = PageReader()

    completed = 0
    needs_review = 0
    failed = 0

    for news in news_items:
        news_id = news["id"]
        print("\n" + "=" * 70)
        print(f"ID {news_id}: {news['title']}")

        try:
            page = reader.read(news["link"])
        except Exception as error:
            page = {
                "content": "",
                "pdf_content": "",
                "status": "failed",
                "source_url": None,
                "reason": f"Erro inesperado na leitura: {error}",
            }

        extraction_status = page.get("status", "unknown") or "unknown"
        extraction_reason = page.get("reason", "") or ""
        content = page.get("content", "") or ""
        pdf_content = page.get("pdf_content", "") or ""
        has_source_text = bool(content.strip() or pdf_content.strip())

        print(f"Extração: {extraction_status}")
        print(f"Origem: {page.get('source_url') or 'Não identificada'}")
        print(f"Texto extraído: {'sim' if has_source_text else 'não'}")

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

        required = (
            "is_public_competition",
            "has_it_opportunity",
            "location",
            "relevance",
            "event_type",
            "reason",
            "evidence",
        )

        valid = (
            isinstance(result, dict)
            and all(field in result for field in required)
            and isinstance(result["is_public_competition"], bool)
            and isinstance(result["has_it_opportunity"], bool)
            and isinstance(result["location"], str)
            and isinstance(result["event_type"], str)
            and isinstance(result["reason"], str)
            and isinstance(result["evidence"], str)
        )

        if not valid:
            failed += 1
            mark_analysis_failure(
                news_id,
                "Classificador indisponível ou resposta inválida. "
                + extraction_reason,
                extraction_status=extraction_status,
            )
            print("Resultado inválido. Registro enviado para revisão.")
            continue

        # Sem texto original ou com relevância inconclusiva, não conclui.
        final_status = (
            "needs_review"
            if not has_source_text or result["relevance"] == "needs_review"
            else "completed"
        )

        print("\nResultado proposto:")
        print(f"  Concurso público: {result['is_public_competition']}")
        print(f"  Oportunidade de TI: {result['has_it_opportunity']}")
        print(f"  Localidade: {result['location']}")
        print(f"  Relevância: {result['relevance']}")
        print(f"  Evento: {result['event_type']}")
        print(f"  Situação: {final_status}")
        print(f"  Motivo: {result['reason']}")
        print(f"  Evidência: {result['evidence']}")

        update = input(
            "\nGravar este resultado? Digite SIM para gravar; "
            "qualquer outra tecla para pular: "
        ).strip()

        if update != "SIM":
            print("Registro não alterado.")
            continue

        update_classification(
            news_id,
            result,
            extraction_status=extraction_status,
            extraction_reason=extraction_reason,
            analysis_status=final_status,
        )

        if final_status == "needs_review":
            needs_review += 1
        else:
            completed += 1

        print(
            "Resultado gravado. Os campos notified_at e "
            "monitoring_notified_at foram preservados."
        )

    print("\n" + "=" * 70)
    print("RESUMO DA REANÁLISE")
    print(f"Concluídas: {completed}")
    print(f"Para revisão: {needs_review}")
    print(f"Falhas: {failed}")
    print("Nenhum e-mail foi enviado por este script.")


if __name__ == "__main__":
    main()

