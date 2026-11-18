
import feedparser
import requests
import time

from urllib.parse import quote
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


class RSSCollector:

    def __init__(self):

        self.days_limit = 3
        self.request_interval = 2
        self.max_retries = 3

        self.queries = [
            # Dourados
            "concurso público Dourados MS",
            "concurso TI Dourados MS",

            # Mato Grosso do Sul
            "concurso público Mato Grosso do Sul",
            "concurso tecnologia informação MS",

            # Concursos federais
            "concurso público federal tecnologia informação",
            "concurso federal analista sistemas",
            "concurso federal técnico informática",

            # Concursos nacionais
            "concurso nacional tecnologia informação",
            "concurso tribunal analista TI",
            "concurso universidade federal tecnologia informação",

            # Avanços e atualizações
            "concurso público banca definida TI",
            "concurso público autorizado tecnologia informação"
        ]

        self.publication_keywords = [
            "concurso",
            "processo seletivo",
            "certame",
            "banca organizadora",
            "concurso autorizado",
            "comissão organizadora",
            "edital de abertura",
            "edital de concurso",
            "nomeação",
            "nomeacao",
            "convocação",
            "convocacao",
            "banca definida"
        ]

        self.stats = {}

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0"
        })

        self.reset_stats()

    def reset_stats(self):

        self.stats = {
            "queries": 0,
            "errors": 0,
            "raw": 0,
            "missing_date": 0,
            "outside_period": 0,
            "no_publication": 0,
            "candidates": 0,
            "duplicates": 0,
            "final": 0
        }

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

        if any(term in text for term in [
            "federal",
            "nacional",
            "universidade federal",
            "instituto federal",
            "tribunal superior",
            "tribunal regional"
        ]):
            return "Nacional - lotação a confirmar"

        return "Localidade a verificar"

    def is_candidate(self, text):

        return self.contains_keyword(
            text,
            self.publication_keywords
        )

    def get_feed(self, url):

        for attempt in range(self.max_retries + 1):

            try:

                response = self.session.get(
                    url,
                    timeout=30
                )

                response.raise_for_status()

                return feedparser.parse(response.content)

            except requests.HTTPError as error:

                status = error.response.status_code

                if status == 429 or status >= 500:

                    if attempt == self.max_retries:
                        raise

                    retry_after = error.response.headers.get(
                        "Retry-After"
                    )

                    wait_time = 5 * (2 ** attempt)

                    if retry_after:

                        try:
                            wait_time = int(retry_after)
                        except ValueError:
                            try:
                                retry_date = parsedate_to_datetime(
                                    retry_after
                                )

                                wait_time = max(
                                    1,
                                    int((
                                        retry_date -
                                        datetime.now(timezone.utc)
                                    ).total_seconds())
                                )
                            except (ValueError, TypeError):
                                pass

                    wait_time = min(wait_time, 60)

                    print(
                        f"Limite ou falha temporária. "
                        f"Nova tentativa em {wait_time}s..."
                    )

                    time.sleep(wait_time)

                else:
                    raise

        return None

    def search(self):

        self.reset_stats()

        results = []

        current_date = datetime.now(timezone.utc)

        cutoff_date = current_date - timedelta(
            days=self.days_limit
        )

        for index, query in enumerate(self.queries):

            self.stats["queries"] += 1

            url = (
                "https://news.google.com/rss/search?q="
                + quote(query + " when:3d")
                + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
            )

            try:

                feed = self.get_feed(url)

                if feed is None:
                    continue

                if feed.bozo:
                    print(
                        f"Aviso ao interpretar RSS: {query}"
                    )

                for entry in feed.entries:

                    self.stats["raw"] += 1

                    published = entry.get(
                        "published_parsed"
                    )

                    if not published:
                        self.stats["missing_date"] += 1
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

                    if not cutoff_date <= published_date <= current_date:
                        self.stats["outside_period"] += 1
                        continue

                    title = entry.get("title", "")
                    summary = entry.get("summary", "")

                    content = f"{title} {summary}"

                    # Filtrar apenas o que não parece
                    # relacionado a concursos públicos.
                    if not self.is_candidate(content):
                        self.stats["no_publication"] += 1
                        continue

                    self.stats["candidates"] += 1

                    results.append({
                        "title": title,
                        "link": entry.get("link", ""),
                        "published": published_date.isoformat(),
                        "summary": summary,
                        "source": "Google News",
                        "location": self.classify_location(content),
                        "search_query": query,
                        "analysis_status": "pending"
                    })

            except requests.RequestException as error:

                self.stats["errors"] += 1

                print(
                    f"Erro na consulta '{query}': {error}"
                )

            except Exception as error:

                self.stats["errors"] += 1

                print(
                    f"Erro inesperado em '{query}': {error}"
                )

            # Intervalo entre consultas
            if index < len(self.queries) - 1:
                time.sleep(self.request_interval)

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

            if not link or link in seen_links:
                self.stats["duplicates"] += 1
                continue

            seen_links.add(link)
            unique_results.append(item)

        self.stats["final"] = len(unique_results)

        return unique_results
