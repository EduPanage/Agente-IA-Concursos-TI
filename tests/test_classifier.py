
from app.ai.classifier import NewsClassifier


def main():

    classifier = NewsClassifier()

    news = {
        "title": "Concurso público oferece vagas para Analista de Sistemas",
        "summary": (
            "Edital de concurso público prevê vagas "
            "para profissionais de Tecnologia da Informação "
            "em diferentes unidades do Mato Grosso do Sul."
        ),
        "location": "Mato Grosso do Sul",
        "source": "Teste"
    }

    print("Analisando notícia...\n")

    result = classifier.classify(news)

    if result:

        print("RESULTADO DA ANÁLISE")
        print("-" * 50)

        for key, value in result.items():
            print(f"{key}: {value}")

    else:

        print("Não foi possível classificar a notícia.")


if __name__ == "__main__":
    main()
