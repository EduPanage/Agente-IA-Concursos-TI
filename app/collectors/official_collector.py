import json
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
    from io import BytesIO
except ImportError:
    PdfReader = None
    BytesIO = None


class OfficialCollector:
    """
    Coleta publicações em fontes oficiais.
    A data usada para o filtro deve ser a data da publicação,
    nunca prazo de inscrição, prova ou outra data do edital.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            )
        })

        # Dourados/MS utiliza UTC-4.
        self.local_timezone = timezone(timedelta(hours=-4))
        self.days_limit = 3
        self.timeout = 25
        self.max_detail_requests = 20
        self.max_pdf_requests = 8

        self.sources = [
            {
                "name": "MGI",
                "url": "https://www.gov.br/servidor/pt-br/acesso-a-informacao/gestao-de-pessoas/concursos-publicos-e-provimento-de-pessoal",
                "location": "Nacional",
            },
            {
                "name": "UFGD",
                "url": "https://www.ufgd.edu.br/coordenadoria/centro-de-selecao/index",
                "location": "Dourados/MS",
            },
            {
                "name": "Concursos MS",
                "url": "https://www2.concursos.ms.gov.br/?location=editais",
                "location": "Mato Grosso do Sul",
            },
            {
                "name": "UFMS",
                "url": "https://www.concursos.ufms.br/",
                "location": "Mato Grosso do Sul",
            },
            {
                "name": "IFMS",
                "url": "https://selecao.ifms.edu.br/",
                "location": "Mato Grosso do Sul",
            },
            {
                "name": "CGU",
                "url": "https://www.gov.br/cgu/pt-br/acesso-a-informacao/concursos/concursos-publicos/",
                "location": "Nacional",
            },
        ]

        self.keywords = (
            "concurso", "edital", "processo seletivo",
            "banca organizadora", "banca definida",
            "concurso autorizado", "comissão organizadora",
            "nomeação", "nomeacao", "convocação", "convocacao",
            "retificação", "retificacao",
        )

        self.months = {
            "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3,
            "abril": 4, "maio": 5, "junho": 6, "julho": 7,
            "agosto": 8, "setembro": 9, "outubro": 10,
            "novembro": 11, "dezembro": 12,
        }

        self.stats = {}
        self.reset_stats()

    # ---------------------------------------------------------
    # ESTATÍSTICAS E UTILITÁRIOS
    # ---------------------------------------------------------

    def reset_stats(self):
        self.stats = {
            "sources": 0,
            "errors": 0,
            "links_found": 0,
            "detail_requests": 0,
            "pdf_requests": 0,
            "without_date": 0,
            "outside_period": 0,
            "candidates": 0,
            "duplicates": 0,
        }

    def contains_keyword(self, text):
        text = (text or "").lower()
        return any(keyword in text for keyword in self.keywords)

    def is_generic_title(self, title):
        normalized = re.sub(r"\s+", " ", (title or "").lower()).strip()
        generic_titles = {
            "concursos públicos",
            "concursos públicos e provimento de pessoal",
            "concursos públicos e processos seletivos",
            "concursos de ifes",
            "concursos no mundo",
            "anos anteriores",
            "edital",
            "concursos",
        }
        return normalized in generic_titles or len(normalized) < 12

    def normalize_url(self, url):
        return (url or "").split("#")[0].strip()

    # ---------------------------------------------------------
    # DATAS
    # ---------------------------------------------------------

    def extract_date(self, value):
        """Converte uma data completa ou um trecho textual em datetime."""
        if not value:
            return None

        text = str(value).strip()
        if not text:
            return None

        # ISO: 2026-11-18 ou 2026-11-18T10:30:00-04:00
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=self.local_timezone)
            return parsed.astimezone(self.local_timezone)
        except ValueError:
            pass

        # Formatos numéricos com e sem horário.
        formats = (
            "%d/%m/%Y %H:%M:%S",
            "%d-%m-%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d-%m-%Y %H:%M",
            "%d/%m/%Y",
            "%d-%m-%Y",
        )
        for fmt in formats:
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.replace(tzinfo=self.local_timezone)
            except ValueError:
                continue

        # Ex.: 17 de novembro de 2026
        normalized = text.lower()
        match = re.search(
            r"\b(\d{1,2})\s+de\s+([a-zçãõ]+)\s+de\s+(\d{4})\b",
            normalized,
        )
        if match:
            day = int(match.group(1))
            month = self.months.get(match.group(2))
            year = int(match.group(3))
            if month:
                try:
                    return datetime(
                        year, month, day, tzinfo=self.local_timezone
                    )
                except ValueError:
                    pass

        return None

    def extract_dates_from_text(self, text):
        """
        Extrai datas em formatos conhecidos. Retorna em ordem de ocorrência.
        Não decide sozinho se a data é de publicação; isso depende do contexto.
        """
        if not text:
            return []

        patterns = [
            r"\b\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+\-Z]+)?\b",
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\b",
            r"\b\d{1,2}\s+de\s+[a-zçãõ]+\s+de\s+\d{4}\b",
        ]

        found = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                parsed = self.extract_date(match.group(0))
                if parsed and parsed not in found:
                    found.append(parsed)

        return sorted(found)

    def is_recent(self, published):
        if not published:
            return False

        now = datetime.now(self.local_timezone)
        if published.tzinfo is None:
            published = published.replace(tzinfo=self.local_timezone)
        published = published.astimezone(self.local_timezone)

        return now - timedelta(days=self.days_limit) <= published <= now

    def extract_labeled_publication_date(self, text):
        """
        Só aceita datas próximas a rótulos que indicam publicação.
        Não usa datas de inscrição, prova, recurso ou validade.
        """
        if not text:
            return None

        patterns = [
            r"(?:publicado|publicada|publicação|publicado em|publicada em)"
            r"\s*[:\-]?\s*"
            r"(\d{1,2}[/-]\d{1,2}[/-]\d{4}"
            r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)",
            r"publicado em:\s*(\d{1,2}/\d{1,2}/\d{4})",
            r"informação divulgada em\s*"
            r"(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}:\d{2})",
            r"(?:publicado|publicada)\s+em\s+"
            r"(\d{1,2}\s+de\s+[a-zçãõ]+\s+de\s+\d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                parsed = self.extract_date(match.group(1))
                if parsed:
                    return parsed

        return None

    # ---------------------------------------------------------
    # REQUISIÇÕES E EXTRAÇÃO DE CONTEÚDO
    # ---------------------------------------------------------

    def fetch_page(self, url):
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response

    def parse_jsonld_dates(self, soup):
        def walk(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in ("datePublished", "dateCreated"):
                        parsed = self.extract_date(item)
                        if parsed:
                            return parsed
                    result = walk(item)
                    if result:
                        return result
            elif isinstance(value, list):
                for item in value:
                    result = walk(item)
                    if result:
                        return result
            return None

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or script.get_text())
                result = walk(data)
                if result:
                    return result
            except (ValueError, TypeError):
                continue
        return None

    def extract_page_date(self, soup, text):
        # Metadados explícitos de publicação.
        selectors = (
            'meta[property="article:published_time"]',
            'meta[name="datePublished"]',
            'meta[itemprop="datePublished"]',
            'meta[name="DC.date"]',
            'meta[name="dcterms.created"]',
        )
        for selector in selectors:
            tag = soup.select_one(selector)
            if tag:
                value = tag.get("content") or tag.get("datetime")
                parsed = self.extract_date(value)
                if parsed:
                    return parsed

        # JSON-LD datePublished/dateCreated.
        parsed = self.parse_jsonld_dates(soup)
        if parsed:
            return parsed

        # Elementos <time> normalmente representam a data do conteúdo.
        for tag in soup.find_all("time"):
            value = tag.get("datetime") or tag.get_text(" ", strip=True)
            parsed = self.extract_date(value)
            if parsed:
                return parsed

        # Texto explicitamente rotulado como publicação.
        return self.extract_labeled_publication_date(text)

    def extract_html_text(self, soup):
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()
        return soup.get_text(" ", strip=True)

    def extract_pdf_text(self, url):
        if PdfReader is None:
            return ""

        try:
            response = self.fetch_page(url)
            if not response.content.startswith(b"%PDF"):
                return ""

            reader = PdfReader(BytesIO(response.content))
            pages = []
            for page in reader.pages[:5]:
                pages.append(page.extract_text() or "")
            return "\n".join(pages)
        except Exception as error:
            print(f"  Não foi possível ler PDF {url}: {error}")
            return ""

    def get_publication_details(self, url):
        try:
            response = self.fetch_page(url)
            content_type = response.headers.get("Content-Type", "").lower()

            if "pdf" in content_type or response.content.startswith(b"%PDF"):
                pdf_text = self.extract_pdf_text_from_bytes(response.content)
                return self.extract_labeled_publication_date(pdf_text), pdf_text

            soup = BeautifulSoup(response.content, "html.parser")
            text = soup.get_text(" ", strip=True)
            published = self.extract_page_date(soup, text)

            if published:
                return published, text

            # Se a página contém links para editais em PDF, tenta ler
            # somente alguns documentos para localizar a data de publicação.
            pdf_links = []
            for anchor in soup.find_all("a", href=True):
                href = urljoin(response.url, anchor["href"])
                if urlparse(href).path.lower().endswith(".pdf"):
                    pdf_links.append(href)

            for pdf_url in list(dict.fromkeys(pdf_links))[:self.max_pdf_requests]:
                self.stats["pdf_requests"] += 1
                pdf_text = self.extract_pdf_text(pdf_url)
                published = self.extract_labeled_publication_date(pdf_text)
                if published:
                    return published, pdf_text or text

            return None, text

        except requests.RequestException as error:
            print(f"  Erro ao acessar publicação {url}: {error}")
            return None, ""
        except Exception as error:
            print(f"  Erro ao analisar publicação {url}: {error}")
            return None, ""

    def extract_pdf_text_from_bytes(self, content):
        if PdfReader is None:
            return ""
        try:
            reader = PdfReader(BytesIO(content))
            return "\n".join(
                page.extract_text() or "" for page in reader.pages[:5]
            )
        except Exception:
            return ""

    # ---------------------------------------------------------
    # REGISTRO DE RESULTADOS
    # ---------------------------------------------------------

    def build_result(self, title, url, published, summary, source):
        return {
            "title": title.strip(),
            "link": self.normalize_url(url),
            "published": published.isoformat(),
            "summary": (summary or "")[:1500],
            "source": source["name"],
            "location": source["location"],
            "search_query": "Fonte oficial",
            "analysis_status": "pending",
        }

    def accept_result(self, results, title, url, published, summary, source):
        if not published:
            self.stats["without_date"] += 1
            return

        if not self.is_recent(published):
            self.stats["outside_period"] += 1
            return

        results.append(
            self.build_result(title, url, published, summary, source)
        )
        self.stats["candidates"] += 1

    # ---------------------------------------------------------
    # COLETOR GENÉRICO
    # ---------------------------------------------------------

    def collect_source(self, source):
        results = []
        response = self.fetch_page(source["url"])
        soup = BeautifulSoup(response.content, "html.parser")

        seen_urls = set()
        requests_made = 0

        for link in soup.find_all("a", href=True):
            title = link.get_text(" ", strip=True)
            if not title or self.is_generic_title(title):
                continue
            if not self.contains_keyword(title):
                continue

            url = self.normalize_url(urljoin(response.url, link["href"]))
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Evita páginas de navegação, âncoras e links para a própria página.
            if url == self.normalize_url(response.url):
                continue

            self.stats["links_found"] += 1
            if requests_made >= self.max_detail_requests:
                break

            print(f"  Analisando: {title[:90]}")
            published, detail_text = self.get_publication_details(url)
            requests_made += 1
            self.stats["detail_requests"] += 1

            self.accept_result(
                results, title, url, published, detail_text, source
            )
            time.sleep(0.35)

        return results

    # ---------------------------------------------------------
    # UFGD: A DATA APARECE PRÓXIMA AOS LINKS DE EDITAIS
    # ---------------------------------------------------------

    def collect_ufgd(self, source):
        results = []
        response = self.fetch_page(source["url"])
        soup = BeautifulSoup(response.content, "html.parser")
        visited_pages = set()

        process_links = []
        for anchor in soup.find_all("a", href=True):
            title = anchor.get_text(" ", strip=True)
            if not title or not self.contains_keyword(title):
                continue
            url = self.normalize_url(urljoin(response.url, anchor["href"]))
            if urlparse(url).netloc.endswith("ufgd.edu.br"):
                if url not in visited_pages and url != self.normalize_url(response.url):
                    process_links.append((title, url))
                    visited_pages.add(url)

        for process_title, process_url in process_links[:self.max_detail_requests]:
            print(f"  Analisando página UFGD: {process_title[:85]}")
            try:
                detail_response = self.fetch_page(process_url)
                detail_soup = BeautifulSoup(detail_response.content, "html.parser")
                self.stats["detail_requests"] += 1

                # Cada edital/link documental pode ter sua própria data no
                # bloco HTML que o contém.
                for anchor in detail_soup.find_all("a", href=True):
                    title = anchor.get_text(" ", strip=True)
                    href = anchor.get("href", "")
                    if not title or not self.contains_keyword(title):
                        continue

                    document_url = self.normalize_url(
                        urljoin(detail_response.url, href)
                    )

                    current = anchor
                    published = None
                    context = ""
                    for _ in range(5):
                        if current is None:
                            break
                        context = current.get_text(" ", strip=True)
                        # Primeiro tenta a data rotulada no bloco.
                        published = self.extract_labeled_publication_date(context)
                        # Em páginas da UFGD, a data costuma aparecer junto
                        # ao cabeçalho "EDITAIS - CCS", antes do título.
                        if not published:
                            dates = self.extract_dates_from_text(context)
                            if dates:
                                published = dates[-1]
                        if published:
                            break
                        current = current.parent

                    # Se não encontrou data no bloco do edital, não usa
                    # "Última Atualização" da página como data de publicação.
                    self.accept_result(
                        results, title, document_url, published,
                        context or process_title, source
                    )
            except requests.RequestException as error:
                self.stats["errors"] += 1
                print(f"  Erro na página UFGD {process_url}: {error}")

            time.sleep(0.4)

        return results

    # ---------------------------------------------------------
    # UFMS: LISTAGEM DE NOTÍCIAS
    # ---------------------------------------------------------

    def collect_ufms(self, source):
        results = []
        url = "https://www.concursos.ufms.br/front/news/list"
        print("\nConsultando listagem de notícias da UFMS...")

        response = self.fetch_page(url)
        soup = BeautifulSoup(response.content, "html.parser")

        # O portal pode apresentar cartões em h4, mas a data pode estar
        # em <time>, metadado ou em um ancestral do título.
        headings = soup.find_all(["h4", "h3", "h2"])
        seen = set()

        for heading in headings:
            anchor = heading.find("a", href=True)
            if not anchor:
                continue

            title = anchor.get_text(" ", strip=True)
            if not title or self.is_generic_title(title):
                continue

            news_url = self.normalize_url(urljoin(response.url, anchor["href"]))
            if news_url in seen:
                continue
            seen.add(news_url)

            current = heading
            published = None
            context = ""

            for _ in range(6):
                if current is None:
                    break

                context = current.get_text(" ", strip=True)

                # Datas sem rótulo só são aceitas quando estão no cartão
                # de notícia, próximo ao título, não no texto de uma notícia.
                for time_tag in current.find_all("time"):
                    value = time_tag.get("datetime") or time_tag.get_text(" ", strip=True)
                    published = self.extract_date(value)
                    if published:
                        break

                if not published:
                    published = self.extract_labeled_publication_date(context)

                if not published:
                    dates = self.extract_dates_from_text(context)
                    if dates:
                        published = dates[-1]

                if published:
                    break

                current = current.parent

            if not published:
                # Última tentativa: a página individual pode conter
                # metadados explícitos de publicação.
                published, detail_text = self.get_publication_details(news_url)
                self.stats["detail_requests"] += 1
                if detail_text:
                    context = detail_text

            self.accept_result(
                results, title, news_url, published, context, source
            )

        print(f"Publicações recentes da UFMS: {len(results)}")
        return results

    # ---------------------------------------------------------
    # PESQUISA PRINCIPAL
    # ---------------------------------------------------------

    def search(self):
        results = []
        self.reset_stats()

        for index, source in enumerate(self.sources):
            print(f"\nConsultando fonte oficial: {source['name']}")
            self.stats["sources"] += 1

            try:
                if source["name"] == "UFGD":
                    source_results = self.collect_ufgd(source)
                elif source["name"] == "UFMS":
                    source_results = self.collect_ufms(source)
                else:
                    source_results = self.collect_source(source)

                results.extend(source_results)
                print(f"Publicações candidatas: {len(source_results)}")

            except requests.RequestException as error:
                self.stats["errors"] += 1
                print(f"Erro ao consultar {source['name']}: {error}")
            except Exception as error:
                self.stats["errors"] += 1
                print(f"Erro inesperado em {source['name']}: {error}")

            if index < len(self.sources) - 1:
                time.sleep(1.5)

        unique = {}
        for news in results:
            key = news["link"]
            if key in unique:
                self.stats["duplicates"] += 1
                continue
            unique[key] = news

        results = list(unique.values())
        results.sort(key=lambda item: item["published"], reverse=True)
        return results

    # ---------------------------------------------------------
    # DIAGNÓSTICO
    # ---------------------------------------------------------

    def debug_source(self, source_name):
        source = next(
            (item for item in self.sources if item["name"] == source_name),
            None,
        )
        if not source:
            print("Fonte não encontrada.")
            return

        try:
            response = self.fetch_page(source["url"])
            soup = BeautifulSoup(response.content, "html.parser")

            print(f"\nDIAGNÓSTICO: {source_name}")
            print("=" * 65)
            print(f"URL final: {response.url}")
            print(f"Status HTTP: {response.status_code}")

            for tag in soup.find_all("time")[:15]:
                print("TIME:", tag)

            for selector in (
                'meta[property="article:published_time"]',
                'meta[itemprop="datePublished"]',
                'meta[name="datePublished"]',
            ):
                for tag in soup.select(selector)[:10]:
                    print("METADADO:", tag)

            count = 0
            for anchor in soup.find_all("a", href=True):
                title = anchor.get_text(" ", strip=True)
                if title and self.contains_keyword(title):
                    print("\nTÍTULO:", title)
                    print("LINK:", urljoin(response.url, anchor["href"]))
                    print("HTML:", str(anchor.parent)[:1200])
                    count += 1
                    if count >= 8:
                        break

            if count == 0:
                print("Nenhum link relacionado encontrado.")

        except requests.RequestException as error:
            print(f"Erro no diagnóstico: {error}")
