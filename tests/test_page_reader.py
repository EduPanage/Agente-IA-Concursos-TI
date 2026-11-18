
from app.collectors.page_reader import PageReader


def main():

    reader = PageReader()

    url = input("Informe o link de uma notícia: ").strip()

    result = reader.read(url)

    print("\nRESULTADO")
    print("-" * 50)

    print(f"Status: {result['status']}")
    print(f"Motivo: {result.get('reason', 'Não informado')}")
    print(f"Resolução: {result['resolution_status']}")
    print(f"URL original: {result['source_url']}")
    print(f"Editais encontrados: {len(result['pdf_links'])}")

    print("\nCONTEÚDO DA NOTÍCIA:")
    print(result["content"][:2000] or "Não extraído.")

    print("\nCONTEÚDO DOS EDITAIS:")
    print(result["pdf_content"][:2000] or "Não extraído.")


if __name__ == "__main__":
    main()
