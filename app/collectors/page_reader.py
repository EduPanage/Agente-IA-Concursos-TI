import base64
import json
import re
import time
from io import BytesIO
from urllib.parse import (
    urljoin,
    urlparse,
    parse_qs,
    unquote,
    urlencode,
)

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


class PageReader:
    """
    Lê páginas HTML e PDFs e resolve links do Google News.

    Para links atuais do Google News, usa o fluxo não oficial do endpoint
    batchexecute. Esse mecanismo pode mudar ou sofrer bloqueios/rate limits.
    """

    GOOGLE_NEWS_HOST = "news.google.com"
    GOOGLE_RPC_URL = (
        "https://news.google.com/_/DotsSplashUi/data/batchexecute"
    )

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
                "application/json,*/*;q=0.8"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            "Upgrade-Insecure-Requests": "1",
        })

        self.timeout = (10, 30)
        self.max_content_size = 10 * 1024 * 1024
        self.max_text_length = 15000
        self.max_pdf_links = 2
        self.google_request_delay = 1.0
        self._last_google_request = 0.0

        self.blocked_domains = (
            "google.com",
            "googleusercontent.com",
            "gstatic.com",
            "googleapis.com",
        )

    def is_valid_url(self, url):
        try:
            parsed = urlparse(url)
            return (
                parsed.scheme in ("http", "https")
                and bool(parsed.netloc)
            )
        except (TypeError, ValueError):
            return False

    def hostname(self, url):
        try:
            return (urlparse(url).hostname or "").lower()
        except (TypeError, ValueError):
            return ""

    def is_google_url(self, url):
        host = self.hostname(url)
        return host == "google.com" or host.endswith(".google.com")

    def is_google_news_url(self, url):
        return self.hostname(url) == self.GOOGLE_NEWS_HOST

    def is_external_url(self, url):
        if not self.is_valid_url(url):
            return False

        host = self.hostname(url)
        return not any(
            host == domain or host.endswith("." + domain)
            for domain in self.blocked_domains
        )

    @staticmethod
    def normalize_url(url):
        return (url or "").strip().rstrip(".,;)}]")

    def _google_headers(self, referer=None):
        headers = {
            "User-Agent": self.session.headers["User-Agent"],
            "Accept": (
                "text/html,application/xhtml+xml,application/json,"
                "*/*;q=0.8"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            "Referer": referer or "https://news.google.com/",
        }
        return headers

    def _respect_google_delay(self):
        elapsed = time.monotonic() - self._last_google_request
        if elapsed < self.google_request_delay:
            time.sleep(self.google_request_delay - elapsed)
        self._last_google_request = time.monotonic()

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
                    "content_type": response.headers.get(
                        "Content-Type", ""
                    ).lower(),
                    "content": bytes(content),
                    "status_code": response.status_code,
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

        for script in soup.find_all(
            "script", type="application/ld+json"
        ):
            try:
                data = json.loads(script.string or script.get_text())
                inspect(data)
            except (json.JSONDecodeError, TypeError):
                continue

        return urls

    def extract_original_candidates(self, html, base_url):
        soup = BeautifulSoup(html, "html.parser")
        candidates = []

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

        for tag in soup.find_all(
            "meta", attrs={"http-equiv": re.compile("refresh", re.I)}
        ):
            match = re.search(
                r"url\s*=\s*['\"]?([^'\"]+)",
                tag.get("content", ""),
                re.I,
            )
            if match:
                candidates.append(match.group(1))

        candidates.extend(self.extract_jsonld_urls(soup))

        article = (
            soup.find("article")
            or soup.find("main")
            or soup.body
            or soup
        )
        page_title = (
            soup.title.get_text(" ", strip=True) if soup.title else ""
        )

        for link in article.find_all("a", href=True):
            href = link["href"]
            link_text = link.get_text(" ", strip=True)
            if not link_text or len(link_text) < 8:
                continue

            if page_title and any(
                word.lower() in link_text.lower()
                for word in page_title.split()
                if len(word) > 5
            ):
                candidates.append(urljoin(base_url, href))

        unique = []
        for candidate in candidates:
            absolute = self.normalize_url(urljoin(base_url, candidate))
            if (
                self.is_external_url(absolute)
                and absolute not in unique
            ):
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
                and absolute not in links
            ):
                links.append(absolute)

        return links

    def read_pdf_url(self, url):
        downloaded = self.download(url)
        if not downloaded:
            return ""

        content = downloaded["content"]
        content_type = downloaded["content_type"]

        if (
            "application/pdf" not in content_type
            and not content.startswith(b"%PDF")
        ):
            return ""

        return self.extract_pdf(content)

    @staticmethod
    def _article_id(url):
        parsed = urlparse(url)
        parts = parsed.path.rstrip("/").split("/")
        if len(parts) < 2 or parts[-2] not in ("articles", "read"):
            return None
        return parts[-1] or None

    def _decode_legacy_google_id(self, article_id):
        """Decodifica apenas o formato antigo, que continha a URL em claro."""
        try:
            padded = article_id + "=" * (-len(article_id) % 4)
            raw = base64.urlsafe_b64decode(padded)

            # Formato protobuf legado: 08 13 22 + tamanho + URL.
            if raw.startswith(b"\x08\x13\x22"):
                raw = raw[3:]

            if raw.endswith(b"\xd2\x01\x00"):
                raw = raw[:-3]

            if not raw:
                return None

            first = raw[0]
            if first < 0x80:
                offset = 1
                length = first
            else:
                if len(raw) < 2:
                    return None
                offset = 2
                length = (first & 0x7F) | (raw[1] << 7)

            candidate = raw[offset:offset + length].decode(
                "utf-8", errors="ignore"
            )
            candidate = self.normalize_url(candidate)

            if self.is_external_url(candidate):
                return candidate

            # Fallback para IDs antigos em que a URL aparece diretamente.
            decoded_text = raw.decode("utf-8", errors="ignore")
            match = re.search(r"https?://[^\x00-\x20\"<>]+", decoded_text)
            if match:
                candidate = self.normalize_url(match.group(0))
                if self.is_external_url(candidate):
                    return candidate

        except Exception:
            return None

        return None

    def _extract_google_signature(self, html):
        text = html.decode("utf-8", errors="ignore") if isinstance(
            html, bytes
        ) else html

        signature = re.search(
            r'data-n-a-sg=["\']([^"\']+)["\']', text
        )
        timestamp = re.search(
            r'data-n-a-ts=["\'](\d+)["\']', text
        )

        if not signature or not timestamp:
            return None, None

        return signature.group(1), int(timestamp.group(1))

    def _resolve_google_news_rpc(self, google_url, article_id):
        """
        Resolve IDs atuais do Google News pelo RPC Fbv4je.
        Endpoint não oficial: pode mudar, bloquear ou limitar requisições.
        """
        page_urls = (
            f"https://news.google.com/rss/articles/{article_id}",
            f"https://news.google.com/articles/{article_id}",
        )

        signature = None
        timestamp = None
        page_response = None

        for page_url in page_urls:
            try:
                self._respect_google_delay()
                response = self.session.get(
                    page_url,
                    headers=self._google_headers(),
                    cookies={"CONSENT": "PENDING+987"},
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                page_response = response

                if response.status_code == 429:
                    return None, "Google News limitou as requisições (HTTP 429)."

                response.raise_for_status()
                signature, timestamp = self._extract_google_signature(
                    response.content
                )
                if signature and timestamp:
                    break

            except requests.RequestException as error:
                last_error = str(error)
                continue

        if not signature or timestamp is None:
            status = (
                page_response.status_code
                if page_response is not None else "sem resposta"
            )
            return None, (
                "Não foi possível obter a assinatura e o horário do Google "
                f"News (HTTP {status}). Pode ser bloqueio, consentimento ou "
                "mudança no HTML."
            )

        inner_payload = [
            "garturlreq",
            [
                [
                    "X", "X", ["X", "X"], None, None, 1, 1,
                    "US:en", None, 1, None, None, None, None,
                    None, 0, 1,
                ],
                "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0,
            ],
            article_id,
            timestamp,
            signature,
        ]

        outer_payload = [[[
            "Fbv4je",
            json.dumps(inner_payload, separators=(",", ":")),
        ]]]

        form_value = json.dumps(
            outer_payload, separators=(",", ":")
        )
        body = "f.req=" + urlencode({"": form_value})[1:]

        headers = self._google_headers(
            referer=f"https://news.google.com/rss/articles/{article_id}"
        )
        headers.update({
            "Content-Type": (
                "application/x-www-form-urlencoded;charset=UTF-8"
            ),
            "Origin": "https://news.google.com",
            "X-Same-Domain": "1",
        })

        try:
            self._respect_google_delay()
            rpc_response = self.session.post(
                self.GOOGLE_RPC_URL,
                params={"rpcids": "Fbv4je"},
                data=body,
                headers=headers,
                timeout=self.timeout,
            )

            if rpc_response.status_code == 429:
                return None, "Google News limitou a resolução (HTTP 429)."

            rpc_response.raise_for_status()
            response_text = rpc_response.text

            # Remove o prefixo anti-JSON-hijacking.
            if "\n\n" in response_text:
                response_text = response_text.split("\n\n", 1)[1]
            else:
                response_text = response_text.lstrip()

            frames = json.loads(response_text)
            frame = next(
                (
                    item for item in frames
                    if isinstance(item, list)
                    and len(item) >= 3
                    and item[0] == "wrb.fr"
                    and item[1] == "Fbv4je"
                ),
                None,
            )

            if not frame or not frame[2]:
                return None, (
                    "O Google respondeu, mas não retornou a URL original."
                )

            decoded_payload = json.loads(frame[2])
            if (
                isinstance(decoded_payload, list)
                and len(decoded_payload) > 1
                and decoded_payload[0] == "garturlres"
            ):
                candidate = self.normalize_url(decoded_payload[1])
                if self.is_external_url(candidate):
                    return candidate, ""

            return None, "Resposta do Google News em formato inesperado."

        except (requests.RequestException, json.JSONDecodeError, ValueError) as error:
            return None, f"Falha na consulta de resolução do Google News: {error}"

    def decode_google_news_url(self, url):
        """
        Tenta primeiro o formato legado offline e depois o RPC atual.
        Retorna (URL_original, motivo_da_falha).
        """
        if not self.is_google_news_url(url):
            return url, ""

        article_id = self._article_id(url)
        if not article_id:
            return None, "Não foi possível identificar o ID do artigo Google News."

        legacy_url = self._decode_legacy_google_id(article_id)
        if legacy_url:
            return legacy_url, ""

        return self._resolve_google_news_rpc(url, article_id)

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
        result = self._empty_result(
            original_url, "failed", "Leitura não iniciada."
        )

        if not self.is_valid_url(original_url):
            result["reason"] = "URL inválida."
            return result

        target_url = original_url
        was_google_link = self.is_google_news_url(target_url)

        if was_google_link:
            target_url, resolution_error = self.decode_google_news_url(
                original_url
            )
            if not target_url:
                result["status"] = "empty"
                result["reason"] = resolution_error or (
                    "Não foi possível resolver o link do Google News."
                )
                return result

            result["resolution_status"] = "decoded"
            print(f"URL original identificada: {target_url}")

        downloaded = self.download(target_url)
        if not downloaded:
            result["reason"] = (
                "Não foi possível baixar a página original ou o servidor "
                "não respondeu dentro do tempo limite."
            )
            return result

        final_url = downloaded["url"]
        content = downloaded["content"]
        content_type = downloaded["content_type"]

        if was_google_link and self.is_google_news_url(final_url):
            result["status"] = "empty"
            result["reason"] = (
                "A resolução terminou em uma página do Google News, "
                "não na fonte original."
            )
            return result

        is_pdf = (
            "application/pdf" in content_type
            or content.startswith(b"%PDF")
        )

        if is_pdf:
            pdf_text = self.extract_pdf(content)
            result.update({
                "source_url": final_url,
                "pdf_content": pdf_text[:self.max_text_length],
                "status": "success" if pdf_text.strip() else "empty",
                "resolution_status": (
                    "pdf_direct" if was_google_link else "direct"
                ),
                "reason": (
                    "" if pdf_text.strip()
                    else "PDF baixado, mas sem texto extraível."
                ),
            })
            return result

        is_html = (
            "html" in content_type
            or b"<html" in content[:1000].lower()
            or b"<!doctype html" in content[:1000].lower()
        )

        if not is_html:
            result["status"] = "unsupported"
            result["reason"] = (
                f"Tipo de conteúdo não suportado: "
                f"{content_type or 'desconhecido'}."
            )
            return result

        article_text = self.extract_html(content)
        if len(article_text.strip()) > 100:
            result.update({
                "source_url": final_url,
                "content": article_text[:self.max_text_length],
                "pdf_links": self.find_pdf_links(content, final_url),
                "resolution_status": (
                    "resolved" if was_google_link else "direct"
                ),
            })
        else:
            result["source_url"] = final_url
            result["reason"] = (
                "A página foi acessada, mas não apresentou texto suficiente."
            )

        pdf_texts = []
        for pdf_url in result["pdf_links"][:self.max_pdf_links]:
            extracted = self.read_pdf_url(pdf_url)
            if extracted.strip():
                pdf_texts.append(extracted)

        if pdf_texts:
            result["pdf_content"] = "\n".join(
                pdf_texts
            )[:self.max_text_length]

        has_html = bool(result["content"].strip())
        has_pdf = bool(result["pdf_content"].strip())

        if has_html and has_pdf:
            result["status"] = "success"
            result["reason"] = ""
        elif has_html or has_pdf:
            result["status"] = "partial"
            result["reason"] = ""
        else:
            result["status"] = "empty"
            if not result["reason"]:
                result["reason"] = (
                    "Nenhum texto útil foi extraído da página."
                )

        return result
