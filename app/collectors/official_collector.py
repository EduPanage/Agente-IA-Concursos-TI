
import requests
import re
import time

from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timedelta, timezone


class OfficialCollector:

    def __init__(self):

        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"
            )
        })

        # Fuso horário de Dourados/MS
        self.local_timezone = timezone(timedelta(hours=-4))

        self.days_limit = 3
        self.timeout = 20
        self.max_detail_requests = 15

        self.sources = [
            {
                "name": "MGI",
                "url": "https://www.gov.br/servidor/pt-br/acesso-a-informacao/gestao-de-pessoas/concursos-publicos-e-provimento-de-pessoal",
                "location": "Nacional"
            },
            {
                "name": "UFGD",
                "url": "https://www.ufgd.edu.br/coordenadoria/centro-de-selecao/index",
                "location": "Dourados/MS"
            },
            {
                "name": "Concursos MS",
                "url": "https://www2.concursos.ms.gov.br/?location=editais",
                "location": "Mato Grosso do Sul"
            },
            {
                "name": "UFMS",
                "url": "https://www.concursos.ufms.br/",
                "location": "Mato Grosso do Sul"
            },
            {
                "name": "IFMS",
                "url": "https://selecao.ifms.edu.br/",
                "location": "Mato Grosso do Sul"
            },
            {
                "name": "CGU",
                "url": "https://www.gov.br/cgu/pt-br/acesso-a-informacao/concursos/concursos-publicos/",
                "location": "Nacional"
            }
        ]

        self.keywords = [
            "concurso",
            "edital",
            "processo seletivo",
            "banca organizadora",
            "banca definida",
            "concurso autorizado",
            "comissão organizadora",
            "nomeação",
            "nomeacao",
            "convocação",
            "convocacao",
            "retificação",
            "retificacao"
        ]

        self.months = {
            "janeiro": 1,
            "fevereiro": 2,
            "março": 3,
            "marco": 3,
            "abril": 4,
            "maio": 5,
            "junho": 6,
            "julho": 7,
            "agosto": 8,
            "setembro": 9,
            "outubro": 10,
            "novembro": 11,
            "dezembro": 12
        }

        self.stats = {}

        self.reset_stats()

    # --------------------------------------------------
    # ESTATÍSTICAS
    # --------------------------------------------------

    def reset_stats(self):

        self.stats = {
            "sources": 0,
            "errors": 0,
            "links_found": 0,
            "detail_requests": 0,
            "without_date": 0,
            "outside_period": 0,
            "candidates": 0,
            "duplicates": 0
        }

    # --------------------------------------------------
    # FILTROS
    # --------------------------------------------------

    def contains_keyword(self, text):

        text = text.lower()

        return any(
            keyword in text
            for keyword in self.keywords
        )

    def is_recent(self, published):

        now = datetime.now(self.local_timezone)

        if published.tzinfo is None:
            published = published.replace(
                tzinfo=self.local_timezone
            )

        published = published.astimezone(
            self.local_timezone
        )

        cutoff = now - timedelta(
            days=self.days_limit
        )

        return cutoff <= published <= now

    # --------------------------------------------------
    # EXTRAÇÃO DE DATAS
    # --------------------------------------------------

    def extract_date(self, text):

        if not text:
            return None

        text = text.strip()

        # Formato ISO
        try:

            parsed = datetime.fromisoformat(
                text.replace("Z", "+00:00")
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=self.local_timezone
                )

            return parsed.astimezone(
                self.local_timezone
            )

        except ValueError:
            pass

        # DD-MM-YYYY HH:MM:SS
        formats = [
            "%d-%m-%Y %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%d/%m/%Y %H:%M",
            "%d-%m-%Y",
            "%d/%m/%Y"
        ]

        for fmt in formats:

            try:

                parsed = datetime.strptime(
                    text,
                    fmt
                )

                return parsed.replace(
                    tzinfo=self.local_timezone
                )

            except ValueError:
                continue

        # DD de mês de YYYY
        match = re.search(
            r"(\d{1,2})\s+de\s+"
            r"([a-zçãõ]+)\s+de\s+(\d{4})",
            text.lower()
        )

        if match:

            day = int(match.group(1))
            month = self.months.get(match.group(2))
            year = int(match.group(3))

            if month:

                try:

                    return datetime(
                        year,
                        month,
                        day,
                        tzinfo=self.local_timezone
                    )

                except ValueError:
                    pass

        return None

    # --------------------------------------------------
    # CONSULTA DE PÁGINAS
    # --------------------------------------------------

    def fetch_page(self, url):

        try:

            response = self.session.get(
                url,
                timeout=self.timeout
            )

            response.raise_for_status()

            return response

        except requests.RequestException as error:

            print(f"Erro ao acessar {url}: {error}")

            raise

    # --------------------------------------------------
    # DETALHES DA PUBLICAÇÃO
    # --------------------------------------------------

    def get_publication_details(self, url):

        try:

            response = self.fetch_page(url)

            soup = BeautifulSoup(
                response.content,
                "html.parser"
            )

            text = soup.get_text(
                " ",
                strip=True
            )

            # 1. Metadados específicos de publicação
            selectors = [
                'meta[property="article:published_time"]',
                'meta[itemprop="datePublished"]',
                'meta[name="datePublished"]'
            ]

            for selector in selectors:

                tag = soup.select_one(selector)

                if tag and tag.get("content"):

                    date = self.extract_date(
                        tag["content"]
                    )

                    if date:
                        return date, text

            # 2. JSON-LD: data de publicação
            for script in soup.find_all(
                "script",
                type="application/ld+json"
            ):

                import json

                try:

                    data = json.loads(
                        script.string or script.get_text()
                    )

                    objects = (
                        data if isinstance(data, list)
                        else [data]
                    )

                    for item in objects:

                        if not isinstance(item, dict):
                            continue

                        date_value = item.get(
                            "datePublished"
                        )

                        if date_value:

                            date = self.extract_date(
                                date_value
                            )

                            if date:
                                return date, text

                except (ValueError, TypeError):
                    continue

            # 3. Padrões específicos de publicação
            patterns = [
                r"Informação divulgada em\s+"
                r"(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}:\d{2})",

                r"(?:Publicado|Publicada|Publicação)"
                r"\s+(?:em\s+)?"
                r"(\d{2}[/-]\d{2}[/-]\d{4})",

                r"Data de publicação\s*[:\-]?\s*"
                r"(\d{2}[/-]\d{2}[/-]\d{4})"
            ]

            for pattern in patterns:

                match = re.search(
                    pattern,
                    text,
                    re.IGNORECASE
                )

                if match:

                    date = self.extract_date(
                        match.group(1)
                    )

                    if date:
                        return date, text
                    
            # Diagnóstico de datas não identificadas
            print("\nDATA NÃO IDENTIFICADA:")
            print(f"URL: {url}")

            date_terms = re.findall(
                r".{0,60}(?:data|public|divulg|atualiz).{0,100}",
                text,
                re.IGNORECASE
            )

            for item in date_terms[:5]:
                print("Trecho:", item)

            if not date_terms:
                print("Nenhuma referência a datas encontrada.")

            print("Início do conteúdo:", text[:300])

            return None, text

        except requests.RequestException:

            return None, ""

        except Exception as error:

            print(
                f"Erro ao analisar publicação {url}: {error}"
            )

            return None, ""

    # --------------------------------------------------
    # COLETA DE UMA FONTE
    # --------------------------------------------------

    def collect_source(self, source):

        results = []

        response = self.fetch_page(
            source["url"]
        )

        soup = BeautifulSoup(
            response.content,
            "html.parser"
        )

        seen_urls = set()

        detail_requests = 0

        for link in soup.find_all(
            "a",
            href=True
        ):

            title = link.get_text(
                " ",
                strip=True
            )

            if not title or len(title) < 10:
                continue

            if not self.contains_keyword(title):
                continue

            url = urljoin(
                response.url,
                link["href"]
            )

            if url in seen_urls:
                continue

            seen_urls.add(url)

            self.stats["links_found"] += 1

            if detail_requests >= self.max_detail_requests:
                break

            print(
                f"  Analisando: {title[:80]}"
            )

            published, detail_content = (
                self.get_publication_details(url)
            )

            detail_requests += 1

            self.stats["detail_requests"] += 1

            time.sleep(0.5)

            if not published:

                self.stats["without_date"] += 1
                continue

            if not self.is_recent(published):

                self.stats["outside_period"] += 1
                continue

            results.append({

                "title": title,

                "link": url,

                "published": published.isoformat(),

                "summary": detail_content[:1500],

                "source": source["name"],

                "location": source["location"],

                "search_query": "Fonte oficial",

                "analysis_status": "pending"

            })

            self.stats["candidates"] += 1

        return results

    # --------------------------------------------------
    # PESQUISA GERAL
    # --------------------------------------------------

    def search(self):

        results = []

        self.reset_stats()

        for index, source in enumerate(self.sources):

            print(
                f"\nConsultando fonte oficial: "
                f"{source['name']}"
            )

            self.stats["sources"] += 1

            try:

                source_results = self.collect_source(
                    source
                )

                results.extend(source_results)

                print(
                    f"Publicações candidatas: "
                    f"{len(source_results)}"
                )

            except requests.RequestException as error:

                self.stats["errors"] += 1

                print(
                    f"Erro ao consultar "
                    f"{source['name']}: {error}"
                )

            except Exception as error:

                self.stats["errors"] += 1

                print(
                    f"Erro inesperado em "
                    f"{source['name']}: {error}"
                )

            if index < len(self.sources) - 1:
                time.sleep(2)

        # Remover duplicidades
        unique = {}

        for news in results:

            if news["link"] in unique:

                self.stats["duplicates"] += 1
                continue

            unique[news["link"]] = news

        results = list(unique.values())

        results.sort(
            key=lambda item: item["published"],
            reverse=True
        )

        return results

    # --------------------------------------------------
    # DIAGNÓSTICO DE FONTES
    # --------------------------------------------------

    def debug_source(self, source_name):

        source = next(
            (
                item for item in self.sources
                if item["name"] == source_name
            ),
            None
        )

        if not source:

            print("Fonte não encontrada.")
            return

        try:

            response = self.fetch_page(
                source["url"]
            )

            soup = BeautifulSoup(
                response.content,
                "html.parser"
            )

            print(
                f"\nDIAGNÓSTICO: {source_name}"
            )

            print("=" * 60)

            for tag in soup.find_all(
                attrs={
                    "itemprop": re.compile(
                        r"datePublished|dateModified"
                    )
                }
            ):

                print("METADADO:", tag)

            for tag in soup.find_all("time"):

                print("TIME:", tag)

            count = 0

            for link in soup.find_all(
                "a",
                href=True
            ):

                title = link.get_text(
                    " ",
                    strip=True
                )

                if (
                    self.contains_keyword(title)
                    and len(title) >= 10
                ):

                    print("\nTÍTULO:", title)

                    print(
                        "HTML:",
                        str(link.parent)[:1500]
                    )

                    count += 1

                    if count >= 3:
                        break

            if count == 0:

                print(
                    "Nenhum link relacionado encontrado."
                )

        except requests.RequestException as error:

            print(
                f"Erro no diagnóstico: {error}"
            )
