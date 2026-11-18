import base64
import json
import re
import time
from io import BytesIO
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


class PageReader:
    """
    Lê páginas HTML e PDFs e tenta resolver links do Google News.
    Mantém a estrutura de retorno utilizada por analyze_pending.py.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/pdf,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        })

        self.timeout = (10, 30)
        self.max_content_size = 10 * 1024 * 1024
        self.max_text_length = 15000
        self.max_pdf_links = 2
        self.max_redirect_attempts = 2

        self.blocked_domains = (
            "google.com",
            "googleusercontent.com",
            "gstatic.com",
            "googleapis.com",
        )

    def is_valid_url(self, url):
        try:
            parsed = urlparse(url)
            return parsed.scheme in ("http", "https") and bool(parsed.netloc)
        except (TypeError, ValueError):
            return False

    def hostname(self, url):
        return (urlparse(url).hostname or "").lower()

    def is_google_url(self, url):
        host = self.hostname(url)
        return host == "google.com" or host.endswith(".google.com")

    def is_external_url(self, url):
        if not self.is_valid_url(url):
            return False

        host = self.hostname(url)
        return not any(
            host == domain or host.endswith("." + domain)
            for domain in self.blocked_domains
        )

    def normalize_url(self, url):
        return (url or "").strip().rstrip(".,;)}]")

    def download(self, url):
        """Baixa conteúdo com limite de tamanho e segue redirecionamentos."""
        if not self.is_valid_url(url):
            return None

        try:
            with self.session.get(
                url,
                timeout=self.timeout,
                stream=True,
                allow_redirects=True,
            ) as response:
                response.raise_for_status()

                content = bytearray()
                for chunk in response.iter_content(8192):
                    if not chunk:
                        continue
                    content.extend(chunk)
                    if len(content) > self.max_content_size:
                        print(f"Arquivo excede 10 MB: {response.url}")
                        return None

                return {
                    "url": response.url,
                    "content_type": response.headers.get("Content-Type", "").lower(),
                    "content": bytes(content),
                    "status_code": response.status_code,
                }

        except requests.RequestException as error:
            print(f"Erro ao acessar {url}: {error}")
            return None

    def decode_google_news_url(self, url):
        """
        Tenta decodificar IDs usados em URLs do Google News.
        Nem todos os formatos do Google contêm a URL original em Base64;
        por isso, a resolução HTTP continua sendo uma alternativa.
        """
        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)

            # Alguns links intermediários carregam a URL em parâmetros.
            for key in ("url", "u", "q"):
                for value in query.get(key, []):
                    candidate = self.normalize_url(unquote(value))
                    if self.is_external_url(candidate):
                        return candidate

            article_id = parsed.path.rstrip("/").split("/")[-1]
            article_id = article_id.split("?")[0]
            if not article_id:
                return None

            padding = "=" * (-len(article_id) % 4)
            decoded = base64.urlsafe_b64decode(article_id + padding)
            decoded_text = decoded.decode("utf-8", errors="ignore")

            candidates = re.findall(
                r'https?://[^\x00-\x20"<>]+',
                decoded_text,
                flags=re.IGNORECASE,
            )

            for candidate in candidates:
                candidate = self.normalize_url(candidate)
                if self.is_external_url(candidate):
                    return candidate

            # Alguns payloads contêm URL codificada como texto percentual.
            decoded_text = unquote(decoded_text)
            candidates = re.findall(
                r'https?://[^\x00-\x20"<>]+',
                decoded_text,
                flags=re.IGNORECASE,
            )
            for candidate in candidates:
                candidate = self.normalize_url(candidate)
                if self.is_external_url(candidate):
                    return candidate

        except Exception:
            pass

        return None

    def extract_jsonld_urls(self, soup):
        urls = []

        def inspect(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in ("url", "mainEntityOfPage"):
                        if isinstance(item, str):
                            urls.append(item)
                        elif isinstance(item, dict):
                            inspect(item)
                    else:
                        inspect(item)
            elif isinstance(value, list):
                for item in value:
                    inspect(item)

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or script.get_text())
                inspect(data)
            except (json.JSONDecodeError, TypeError):
                continue

        return urls

    def extract_original_candidates(self, html, base_url):
        soup = BeautifulSoup(html, "html.parser")
        candidates = []

        # Metadados e canonical costumam apontar para a página original.
        for attribute, key in (
            ("property", "og:url"),
            ("name", "twitter:url"),
        ):
            tag = soup.find("meta", attrs={attribute: key})
            if tag and tag.get("content"):
                candidates.append(tag["content"])

        canonical = soup.find(
            "link",
            rel=lambda value: value and "canonical" in value,
        )
        if canonical and canonical.get("href"):
            candidates.append(canonical["href"])

        for tag in soup.find_all("meta", attrs={"http-equiv": re.compile("refresh", re.I)}):
            content = tag.get("content", "")
            match = re.search(r"url\s*=\s*['\"]?([^'\"]+)", content, re.I)
            if match:
                candidates.append(match.group(1))

        candidates.extend(self.extract_jsonld_urls(soup))

        # Links externos relevantes na área principal.
        article = soup.find("article") or soup.find("main") or soup.body or soup
        page_title = soup.title.get_text(" ", strip=True) if soup.title else ""

        for link in article.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(" ", strip=True)
            if not text or len(text) < 8:
                continue
            if page_title and any(
                word.lower() in text.lower()
                for word in page_title.split()
                if len(word) > 5
            ):
                candidates.append(urljoin(base_url, href))

        unique = []
        for candidate in candidates:
            absolute = self.normalize_url(urljoin(base_url, candidate))
            if self.is_external_url(absolute) and absolute not in unique:
                unique.append(absolute)

        return unique

    def extract_html(self, content):
        soup = BeautifulSoup(content, "html.parser")
        for element in soup((
            "script", "style", "nav", "footer", "header",
            "aside", "form", "noscript",
        )):
            element.decompose()

        article = (
            soup.find("article")
            or soup.find(attrs={"itemprop": "articleBody"})
            or soup.find("main")
            or soup.body
            or soup
        )
        return article.get_text(separator="\n", strip=True)

    def find_pdf_links(self, content, base_url):
        soup = BeautifulSoup(content, "html.parser")
        links = []

        for anchor in soup.find_all("a", href=True):
            absolute = urljoin(base_url, anchor["href"])
            if (
                self.is_valid_url(absolute)
                and urlparse(absolute).path.lower().endswith(".pdf")
            ):
                if absolute not in links:
                    links.append(absolute)

        return links

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

    def read_pdf_url(self, url):
        downloaded = self.download(url)
        if not downloaded:
            return ""

        content = downloaded["content"]
        content_type = downloaded["content_type"]

        if "application/pdf" not in content_type and not content.startswith(b"%PDF"):
            return ""

        return self.extract_pdf(content)

    def _empty_result(self, original_url, status, reason):
        return {
            "url": original_url,
            "source_url": None,
            "content": "",
            "pdf_content": "",
            "pdf_links": [],
            "status": status,
            "resolution_status": "failed",
            "reason": reason,
        }

    def read(self, original_url):
        result = self._empty_result(original_url, "failed", "Leitura não iniciada.")

        if not self.is_valid_url(original_url):
            result["reason"] = "URL inválida."
            return result

        target_url = original_url
        was_google_link = self.is_google_url(target_url)

        # Primeira tentativa: decodificação local do identificador.
        if was_google_link:
            decoded_url = self.decode_google_news_url(target_url)
            if decoded_url:
                target_url = decoded_url
                result["resolution_status"] = "decoded"
                print(f"URL original identificada por decodificação: {target_url}")

        # Segunda tentativa: GET seguindo redirecionamentos HTTP.
        downloaded = self.download(target_url)
        if not downloaded:
            result["reason"] = "Não foi possível baixar a URL ou o servidor excedeu o tempo limite."
            return result

        final_url = downloaded["url"]
        content = downloaded["content"]
        content_type = downloaded["content_type"]

        # Um redirecionamento pode resolver o link mesmo sem decodificação.
        if was_google_link and not self.is_google_url(final_url):
            result["resolution_status"] = "redirected"
            print(f"URL original identificada por redirecionamento: {final_url}")

        is_pdf = "application/pdf" in content_type or content.startswith(b"%PDF")
        if is_pdf:
            pdf_text = self.extract_pdf(content)
            result.update({
                "source_url": final_url,
                "pdf_content": pdf_text[:self.max_text_length],
                "status": "success" if pdf_text.strip() else "empty",
                "reason": "" if pdf_text.strip() else "PDF baixado, mas sem texto extraível.",
            })
            return result

        is_html = (
            "html" in content_type
            or b"<html" in content[:1000].lower()
            or b"<!doctype html" in content[:1000].lower()
        )
        if not is_html:
            result["status"] = "unsupported"
            result["reason"] = f"Tipo de conteúdo não suportado: {content_type or 'desconhecido'}."
            return result

        # Não aceitar texto do Google como conteúdo original.
        if self.is_google_url(final_url):
            candidates = self.extract_original_candidates(content, final_url)
            for candidate in candidates[:5]:
                candidate_download = self.download(candidate)
                if not candidate_download:
                    continue

                candidate_content = candidate_download["content"]
                candidate_type = candidate_download["content_type"]
                candidate_url = candidate_download["url"]

                if "pdf" in candidate_type or candidate_content.startswith(b"%PDF"):
                    pdf_text = self.extract_pdf(candidate_content)
                    if pdf_text.strip():
                        result.update({
                            "source_url": candidate_url,
                            "pdf_content": pdf_text[:self.max_text_length],
                            "status": "success",
                            "resolution_status": "resolved_pdf",
                            "reason": "",
                        })
                        return result

                elif (
                    "html" in candidate_type
                    or b"<html" in candidate_content[:1000].lower()
                ):
                    article_text = self.extract_html(candidate_content)
                    if len(article_text.strip()) > 200 and not self.is_google_url(candidate_url):
                        result.update({
                            "source_url": candidate_url,
                            "content": article_text[:self.max_text_length],
                            "pdf_links": self.find_pdf_links(candidate_content, candidate_url),
                            "resolution_status": "resolved",
                        })
                        break

            if not result["source_url"]:
                result["status"] = "empty"
                result["reason"] = (
                    "O Google News não redirecionou para a fonte original "
                    "e não foi possível identificar um link externo."
                )
                return result

        else:
            article_text = self.extract_html(content)
            if len(article_text.strip()) > 100:
                result.update({
                    "source_url": final_url,
                    "content": article_text[:self.max_text_length],
                    "pdf_links": self.find_pdf_links(content, final_url),
                    "resolution_status": (
                        result["resolution_status"]
                        if result["resolution_status"] != "failed"
                        else "direct"
                    ),
                })
            else:
                result["source_url"] = final_url
                result["reason"] = "A página foi acessada, mas não apresentou texto suficiente."

        # Ler até dois PDFs associados à página original.
        pdf_texts = []
        for pdf_url in result["pdf_links"][:self.max_pdf_links]:
            extracted = self.read_pdf_url(pdf_url)
            if extracted.strip():
                pdf_texts.append(extracted)

        if pdf_texts:
            result["pdf_content"] = "\n".join(pdf_texts)[:self.max_text_length]

        has_html = bool(result["content"].strip())
        has_pdf = bool(result["pdf_content"].strip())

        if has_html and has_pdf:
            result["status"] = "success"
            result["reason"] = ""
        elif has_html or has_pdf:
            result["status"] = "partial"
            result["reason"] = ""
        elif result["status"] != "empty":
            result["status"] = "empty"
            if not result["reason"]:
                result["reason"] = "Nenhum texto útil foi extraído da página."

        return result
