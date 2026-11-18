
from app.collectors.rss_collector import RSSCollector
from app.database.db import (
    initialize_database,
    save_news
)


def main():

    print("\n\n")
    print("=" * 55)
    print("AGENTE DE CONCURSOS TI - DOURADOS/MS")
    print("=" * 55)
    print("\n")

    # Inicializar banco de dados
    initialize_database()

    # Executar pesquisas
    print("\nIniciando pesquisas...")

    collector = RSSCollector()
    results = collector.search()

    print(f"Notícias relevantes encontradas: {len(results)}")

    # Armazenar resultados
    database_result = save_news(results)

    print("\nRESUMO DA EXECUÇÃO")
    print("-" * 55)

    print(f"Novas notícias: {database_result['inserted']}")
    print(f"Notícias atualizadas: {database_result['updated']}")

    # Exibir notícias inéditas
    if database_result["new_news"]:

        print("\nNOVAS PUBLICAÇÕES IDENTIFICADAS")

        for news in database_result["new_news"]:

            print("-" * 55)
            print(f"Título: {news['title']}")
            print(f"Localidade: {news['location']}")
            print(f"Data: {news['published']}")
            print(f"Link: {news['link']}")

    else:

        print("\nNenhuma publicação inédita identificada.")

    print("\nExecução finalizada!")


if __name__ == "__main__":
    main()
