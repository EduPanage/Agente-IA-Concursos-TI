
import feedparser
import requests

from urllib.parse import quote
from datetime import datetime, timedelta, timezone


class RSSCollector:

    def __init__(self):

        self.days_limit = 3

        # Pesquisas municipais, estaduais e nacionais
        self.queries = [
            # Dourados
            "concurso TI Dourados MS",
            "concurso técnico informática Dourados",
            "concurso analista sistemas Dourados",
            "processo seletivo TI Dourados",

            # Mato Grosso do Sul
            "concurso TI Mato Grosso do Sul",
            "concurso analista sistemas MS",
            "concurso técnico informática MS",

            # Concursos federais e nacionais
            "concurso federal tecnologia informação",
            "concurso nacional analista TI",
            "concurso federal analista sistemas",
            "concurso tribunal TI",
            "concurso universidade federal TI",
            "concurso instituto federal informática",

            # Possíveis vagas em MS
            "concurso federal TI vagas MS",
            "concurso nacional TI Dourados",
            "concurso órgão federal TI Mato Grosso do Sul"
        ]

        # Palavras relacionadas à área de TI
        self.ti_keywords = [
            "tecnologia da informação",
            "tecnologia de informação",
            "analista de ti",
            "analista de sistemas",
            "técnico de informática",
            "tecnico em informatica",
            "desenvolvedor",
            "programador",
            "administrador de redes",
            "infraestrutura de ti",
            "segurança da informação",
            "banco de dados",
            "suporte técnico",
            "suporte de ti",
            "sistemas de informação",
            "ciência da computação",
            "engenharia de software",
            "analista de infraestrutura",
            "engenheiro de software",
            "redes de computadores"
        ]

        # Indícios de concurso ou contratação pública
        self.publication_keywords = [
            "concurso público",
            "concurso publico",
            "processo seletivo",
            "edital",
            "vagas",
            "cargo público",
            "cargo publico",
            "servidor público",
            "servidor publico",
            "banca organizadora",
            "comissão organizadora",
            "comissao organizadora",
            "concurso autorizado",
            "concurso previsto",
            "nomeação",
            "nomeacao",
            "convocação",
            "convocacao",
            "inscrições",
            "inscricoes",
            "seleção pública",
            "selecao publica"
        ]

        # Indícios de oportunidades nacionais
        self.national_keywords = [
            "federal",
            "nacional",
            "órgão federal",
            "orgao federal",
            "universidade federal",
            "instituto federal",
            "tribunal regional",
            "tribunal superior"
        ]

        # Localidades de outros estados
        self.other_state_keywords = [
            "são paulo", "sao paulo", "ifsp",
            "rio de janeiro", "if rj",
            "paraná", "parana", "ifpr",
            "minas gerais", "ifmg",
            "santa catarina", "ifsc",
            "rio grande do sul", "ifrs",
            "goiás", "goias", "ifg",
            "bahia", "ifba",
            "pernambuco", "ifpe",
            "ceará", "ceara", "ifce",
            "espírito santo", "espirito santo", "ifes",
            "amazonas", "ifam",
            "mato grosso", "ifmt",
            "rondônia", "rondonia", "ifro",
            "acre", "ifac",
            "roraima", "ifrr",
            "amapá", "amapa", "ifap",
            "tocantins", "ifto",
            "sergipe", "ifs",
            "alagoas", "ifal",
            "paraíba", "paraiba", "ifpb",
            "rio grande do norte", "ifrn",
            "maranhão", "maranhao", "ifma",
            "piauí", "piaui", "ifpi"
        ]

    def contains_keyword(self, text, keywords):

        text = text.lower()

        return any(
            keyword in text
            for keyword in keywords
        )

    def classify_location(self, text):

        text = text.lower()

        if any(term in text for term in [
            "dourados",
            "ufgd",
            "campus dourados"
        ]):
            return "Dourados/MS"

        if any(term in text for term in [
            "mato grosso do sul",
            "campo grande",
            "três lagoas",
            "tres lagoas",
            "corumbá",
            "corumba",
            "ponta porã",
            "ponta pora",
            "ifms"
        ]):
            return "Mato Grosso do Sul"

        if self.contains_keyword(
            text, self.other_state_keywords
        ):
            return "Outro estado"

        if self.contains_keyword(
            text, self.national_keywords
        ):
            return "Nacional - lotação a confirmar"

        return "Localidade não identificada"

    def is_relevant(self, text):

        # Precisa mencionar uma área de TI
        if not self.contains_keyword(
            text, self.ti_keywords
        ):
            return False

        # Precisa apresentar indícios de contratação pública
        if not self.contains_keyword(
            text, self.publication_keywords
        ):
            return False

        return True

    def search(self):

        results = []

        current_date = datetime.now(timezone.utc)

        cutoff_date = current_date - timedelta(
            days=self.days_limit
        )

        for query in self.queries:

            url = (
                "https://news.google.com/rss/search?q="
                + quote(query + " when:3d")
                + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
            )

            try:

                response = requests.get(
                    url,
                    timeout=20,
                    headers={
                        "User-Agent": "Mozilla/5.0"
                    }
                )

                response.raise_for_status()

                feed = feedparser.parse(
                    response.content
                )

                if feed.bozo:
                    print(
                        f"Aviso RSS em '{query}': "
                        f"{feed.bozo_exception}"
                    )

                if not feed.entries:
                    print(
                        f"Nenhum resultado para: {query}"
                    )
                    continue

                for entry in feed.entries:

                    published = entry.get(
                        "published_parsed"
                    )

                    if not published:
                        continue

                    published_date = datetime(
                        published.tm_year,
                        published.tm_mon,
                        published.tm_mday,
                        published.tm_hour,
                        published.tm_min,
                        published.tm_sec,
                        tzinfo=timezone.utc
                    )

                    # Limite de três dias
                    if not cutoff_date <= published_date <= current_date:
                        continue

                    title = entry.get("title", "")

                    summary = entry.get(
                        "summary", ""
                    )

                    content = f"{title} {summary}"

                    # Filtrar publicações sem relação com TI
                    if not self.is_relevant(content):
                        continue

                    location = self.classify_location(
                        content
                    )

                    # Descartar oportunidades claramente
                    # direcionadas exclusivamente a outros estados
                    if location == "Outro estado":
                        continue

                    results.append({
                        "title": title,
                        "link": entry.get("link", ""),
                        "published": published_date.isoformat(),
                        "summary": summary,
                        "source": "Google News",
                        "location": location,
                        "search_query": query
                    })

            except requests.RequestException as error:

                print(
                    f"Erro de conexão na consulta "
                    f"'{query}': {error}"
                )

            except Exception as error:

                print(
                    f"Erro inesperado na consulta "
                    f"'{query}': {error}"
                )

        # Ordenar do mais recente para o mais antigo
        results.sort(
            key=lambda item: item["published"],
            reverse=True
        )

        # Remover duplicidades
        unique_results = []
        seen_links = set()

        for item in results:

            link = item["link"]

            if link and link not in seen_links:
                seen_links.add(link)
                unique_results.append(item)

        return unique_results
