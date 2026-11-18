
from app.collectors.rss_collector import RSSCollector


def main():
    collector = RSSCollector()

    results = collector.search()

    print(f"\nResultados encontrados: {len(results)}\n")

    for item in results:
        print("-" * 60)
        print(f"Título: {item['title']}")
        print(f"Data: {item['published']}")
        print(f"Link: {item['link']}")


if __name__ == "__main__":
    main()
