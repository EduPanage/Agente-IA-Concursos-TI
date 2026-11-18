
from app.collectors.official_collector import OfficialCollector


def main():

    collector = OfficialCollector()

    print("=" * 55)
    print("TESTE DE FONTES OFICIAIS")
    print("=" * 55)

    results = collector.search()

    print("\nDIAGNÓSTICO")
    print("-" * 55)

    for key, value in collector.stats.items():
        print(f"{key}: {value}")

    print("\nPUBLICAÇÕES ENCONTRADAS")
    print("-" * 55)

    for news in results:

        print(f"\nTítulo: {news['title']}")
        print(f"Fonte: {news['source']}")
        print(f"Localidade: {news['location']}")
        print(f"Data: {news['published']}")
        print(f"Link: {news['link']}")

    print("\nTotal de publicações:", len(results))


if __name__ == "__main__":
    main()
