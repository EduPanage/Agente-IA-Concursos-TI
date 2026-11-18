
import json
import re
import base64
import requests

from bs4 import BeautifulSoup
from pypdf import PdfReader
from urllib.parse import urljoin, urlparse
from io import BytesIO


class PageReader:

    def __init__(self):

        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"
            )
        })

        self.timeout = 20
        self.max_content_size = 10 * 1024 * 1024
        self.max_text_length = 15000

        self.blocked_domains = [
            "google.com",
            "googleusercontent.com",
            "gstatic.com",
            "googleapis.com"
        ]

    def is_valid_url(self, url):

        try:
            parsed = urlparse(url)

            return (
                parsed.scheme in ("http", "https")
                and bool(parsed.netloc)
            )

        except Exception:
            return False

    def is_google_url(self, url):

        host = urlparse(url).hostname or ""

        return (
            host == "google.com"
            or host.endswith(".google.com")
        )

    def is_external_url(self, url):

        if not self.is_valid_url(url):
            return False

        host = urlparse(url).hostname or ""

        return not any(
            host == domain or host.endswith("." + domain)
            for domain in self.blocked_domains
        )

    def download(self, url):

        if not self.is_valid_url(url):
            return None

        try:

            with self.session.get(
                url,
                timeout=self.timeout,
                stream=True,
                allow_redirects=True
            ) as response:

                response.raise_for_status()

                content = bytearray()

                for chunk in response.iter_content(8192):

                    if not chunk:
                        continue

                    content.extend(chunk)

                    if len(content) > self.max_content_size:
                        print("Arquivo excede 10 MB.")
                        return None

                return {
                    "url": response.url,
                    "content_type": response.headers.get(
                        "Content-Type", ""
                    ).lower(),
                    "content": bytes(content)
                }

        except requests.RequestException as error:

            print(f"Erro ao acessar {url}: {error}")
            return None

    def extract_pdf(self, content):

        try:

            reader = PdfReader(BytesIO(content))

            pages = []

            for page in reader.pages[:30]:

                text = page.extract_text() or ""

                if text:
                    pages.append(text)

            return "\n".join(pages)

        except Exception as error:

            print(f"Erro ao extrair PDF: {error}")
            return ""

    def extract_jsonld_urls(self, soup):

        urls = []

        def inspect(value):

            if isinstance(value, dict):

                for key, item in value.items():

                    if key in ["url", "mainEntityOfPage"]:

                        if isinstance(item, str):
                            urls.append(item)

                        elif isinstance(item, dict):
                            inspect(item)

                    else:
                        inspect(item)

            elif isinstance(value, list):

                for item in value:
                    inspect(item)

        for script in soup.find_all(
            "script",
            type="application/ld+json"
        ):

            try:

                data = json.loads(
                    script.string or script.get_text()
                )

                inspect(data)

            except (json.JSONDecodeError, TypeError):
                continue

        return urls

    def extract_original_candidates(self, html, base_url):

        soup = BeautifulSoup(html, "html.parser")

        candidates = []

        for attribute, key in [
            ("property", "og:url"),
            ("name", "twitter:url")
        ]:

            tag = soup.find(
                "meta",
                attrs={attribute: key}
            )

            if tag and tag.get("content"):
                candidates.append(tag["content"])

        canonical = soup.find(
            "link",
            rel=lambda value: value and "canonical" in value
        )

        if canonical and canonical.get("href"):
            candidates.append(canonical["href"])

        candidates.extend(
            self.extract_jsonld_urls(soup)
        )

        article = (
            soup.find("article")
            or soup.find("main")
            or soup.body
            or soup
        )

        title = (
            soup.title.get_text(" ", strip=True)
            if soup.title else ""
        )

        for link in article.find_all("a", href=True):

            href = link["href"]
            text = link.get_text(" ", strip=True)

            if not text or len(text) < 8:
                continue

            if title and any(
                word.lower() in text.lower()
                for word in title.split()
                if len(word) > 5
            ):

                candidates.append(
                    urljoin(base_url, href)
                )

        unique = []

        for candidate in candidates:

            absolute = urljoin(base_url, candidate)

            if (
                self.is_external_url(absolute)
                and absolute not in unique
            ):
                unique.append(absolute)

        return unique

    def extract_html(self, content):

        soup = BeautifulSoup(content, "html.parser")

        for element in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
            "noscript"
        ]):

            element.decompose()

        article = (
            soup.find("article")
            or soup.find("main")
            or soup.find(attrs={"itemprop": "articleBody"})
            or soup.body
            or soup
        )

        return article.get_text(
            separator="\n",
            strip=True
        )

    def find_pdf_links(self, content, base_url):

        soup = BeautifulSoup(content, "html.parser")

        pdf_links = []

        for link in soup.find_all("a", href=True):

            href = link["href"]

            absolute_url = urljoin(base_url, href)

            if (
                self.is_valid_url(absolute_url)
                and urlparse(absolute_url).path.lower().endswith(".pdf")
            ):

                pdf_links.append(absolute_url)

        return list(dict.fromkeys(pdf_links))

    def read_pdf_url(self, url):

        downloaded = self.download(url)

        if not downloaded:
            return ""

        content = downloaded["content"]
        content_type = downloaded["content_type"]

        is_pdf = (
            "application/pdf" in content_type
            or content.startswith(b"%PDF")
        )

        if not is_pdf:
            return ""

        return self.extract_pdf(content)

    def decode_google_news_url(self, url):

        try:

            article_id = urlparse(url).path.split("/")[-1]
            article_id = article_id.split("?")[0]

            padding = "=" * (-len(article_id) % 4)

            decoded = base64.urlsafe_b64decode(
                article_id + padding
            )

            decoded_text = decoded.decode(
                "latin-1",
                errors="ignore"
            )

            urls = re.findall(
                r'https?://[^\x00-\x20"<>]+',
                decoded_text
            )

            for candidate in urls:

                candidate = candidate.rstrip(".,;)}]")

                if self.is_external_url(candidate):
                    return candidate

            return None

        except Exception as error:

            print(f"Falha ao decodificar link: {error}")
            return None

    # IMPORTANTE: read() agora pertence à classe PageReader.

    def read(self, url):

        result = {
            "url": url,
            "source_url": None,
            "content": "",
            "pdf_content": "",
            "pdf_links": [],
            "status": "failed",
            "resolution_status": "not_resolved"
        }

        # Tentar decodificar links do Google News
        if self.is_google_url(url):

            decoded_url = self.decode_google_news_url(url)

            if decoded_url:
                url = decoded_url
                print(f"URL original identificada: {url}")

        downloaded = self.download(url)

        if not downloaded:
            return result

        # Estas variáveis precisam ficar fora do if anterior.
        final_url = downloaded["url"]
        content = downloaded["content"]
        content_type = downloaded["content_type"]

        # Caso o link já seja um PDF
        if (
            "application/pdf" in content_type
            or content.startswith(b"%PDF")
        ):

            result["source_url"] = final_url
            result["pdf_content"] = self.extract_pdf(content)

            result["status"] = (
                "success" if result["pdf_content"] else "empty"
            )

            return result

        if "html" not in content_type:
            result["status"] = "unsupported"
            return result

        html_text = self.extract_html(content)

        # Primeira tentativa: conteúdo da própria página
        if not self.is_google_url(final_url) and len(html_text) > 200:

            result["source_url"] = final_url
            result["content"] = html_text

            result["pdf_links"] = self.find_pdf_links(
                content,
                final_url
            )

            result["resolution_status"] = "direct"

        else:

            # Segunda tentativa: localizar publicação original
            candidates = self.extract_original_candidates(
                content,
                final_url
            )

            for candidate in candidates[:5]:

                original = self.download(candidate)

                if not original:
                    continue

                original_content = original["content"]
                original_type = original["content_type"]

                if (
                    "pdf" in original_type
                    or original_content.startswith(b"%PDF")
                ):

                    pdf_text = self.extract_pdf(original_content)

                    if pdf_text:

                        result["source_url"] = original["url"]
                        result["pdf_content"] = pdf_text
                        result["resolution_status"] = "pdf_direct"

                        break

                elif "html" in original_type:

                    extracted = self.extract_html(
                        original_content
                    )

                    if len(extracted) > 200:

                        result["source_url"] = original["url"]
                        result["content"] = extracted

                        result["pdf_links"] = self.find_pdf_links(
                            original_content,
                            original["url"]
                        )

                        result["resolution_status"] = "resolved"

                        break

        # Ler até dois PDFs encontrados
        pdf_texts = []

        for pdf_url in result["pdf_links"][:2]:

            extracted = self.read_pdf_url(pdf_url)

            if extracted:
                pdf_texts.append(extracted)

        if pdf_texts:
            result["pdf_content"] = "\n".join(pdf_texts)

        # Definir qualidade da extração
        if result["content"] and result["pdf_content"]:
            result["status"] = "success"

        elif result["content"] or result["pdf_content"]:
            result["status"] = "partial"

        else:
            result["status"] = "empty"

        result["content"] = result["content"][
            :self.max_text_length
        ]

        result["pdf_content"] = result["pdf_content"][
            :self.max_text_length
        ]

        return result
