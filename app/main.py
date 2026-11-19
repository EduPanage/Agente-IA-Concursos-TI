from app.collectors.rss_collector import RSSCollector
from app.collectors.official_collector import OfficialCollector
from app.database.db import initialize_database, save_news
from app.ai.analyze_pending import analyze_pending
from app.notifications.gmail_notifier import send_pending_notifications


def collect_from_rss():
    print("\n[1/4] COLETA RSS")
    collector = RSSCollector()
    try:
        results = collector.search()
        print(f"Publicações RSS encontradas: {len(results)}")
        for key, value in collector.stats.items():
            print(f"{key}: {value}")
        return results
    except Exception as error:
        print(f"Falha na coleta RSS: {error}")
        return []


def collect_from_official_sources():
    print("\n[2/4] FONTES OFICIAIS")
    collector = OfficialCollector()
    try:
        results = collector.search()
        print(f"Publicações oficiais encontradas: {len(results)}")
        for key, value in collector.stats.items():
            print(f"{key}: {value}")
        return results
    except Exception as error:
        print(f"Falha na coleta de fontes oficiais: {error}")
        return []


def main():
    print("\n" + "=" * 65)
    print("AGENTE DE CONCURSOS DE TI - DOURADOS/MS")
    print("=" * 65)

    initialize_database()

    rss_results = collect_from_rss()
    official_results = collect_from_official_sources()

    print("\n[3/4] SALVANDO PUBLICAÇÕES")
    unique_news = {}
    for item in rss_results + official_results:
        link = item.get("link")
        if link:
            unique_news.setdefault(link, item)

    consolidated = list(unique_news.values())
    db_result = save_news(consolidated)
    print(f"Publicações consolidadas: {len(consolidated)}")
    print(f"Novas notícias: {db_result['inserted']}")
    print(f"Notícias atualizadas: {db_result['updated']}")

    print("\n[4/4] ANÁLISE DE NOTÍCIAS")
    analysis_result = analyze_pending(limit=20)

    print("\nNOTIFICAÇÕES")
    notification_result = send_pending_notifications()

    print("\n" + "=" * 65)
    print("RESUMO FINAL")
    print("=" * 65)
    print(f"Coleta RSS: {len(rss_results)}")
    print(f"Coleta oficial: {len(official_results)}")
    print(f"Novos registros: {db_result['inserted']}")
    print(f"Análise concluída: {analysis_result.get('completed', 0)}")
    print(f"Em revisão: {analysis_result.get('needs_review', 0)}")
    print(f"Falhas de classificação: {analysis_result.get('failed', 0)}")
    print(f"E-mails enviados: {notification_result.get('sent', 0)}")
    print(
        "Vagas de TI notificadas: "
        f"{notification_result.get('opportunities_notified', 0)}"
    )
    print(
        "Avisos pré-edital enviados: "
        f"{notification_result.get('monitoring_notified', 0)}"
    )
    print("\nExecução finalizada.")


if __name__ == "__main__":
    main()
