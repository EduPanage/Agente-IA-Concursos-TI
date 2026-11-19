import unittest
from unittest.mock import patch

from app.collectors.page_reader import PageReader


class TestPageReader(unittest.TestCase):
    def setUp(self):
        self.reader = PageReader()

    def test_validates_urls(self):
        self.assertTrue(self.reader.is_valid_url("https://exemplo.com/noticia"))
        self.assertFalse(self.reader.is_valid_url("ftp://exemplo.com/arquivo"))
        self.assertFalse(self.reader.is_valid_url("nao-e-url"))

    def test_extracts_article_and_ignores_navigation(self):
        html = b"""
        <html><body>
          <nav>Texto de navegacao que nao deve aparecer</nav>
          <article><h1>Noticia</h1><p>Conteudo principal da noticia.</p></article>
        </body></html>
        """
        extracted = self.reader.extract_html(html)
        self.assertIn("Conteudo principal da noticia.", extracted)
        self.assertNotIn("Texto de navegacao", extracted)

    def test_finds_pdf_links_and_makes_them_absolute(self):
        html = b'<html><body><a href="/edital.pdf">Edital</a></body></html>'
        links = self.reader.find_pdf_links(html, "https://exemplo.com/noticia")
        self.assertEqual(links, ["https://exemplo.com/edital.pdf"])

    def test_html_article_without_pdf_is_success(self):
        article = "Texto da noticia. " * 12
        html = f"<html><body><article>{article}</article></body></html>".encode()
        downloaded = {
            "url": "https://exemplo.com/noticia",
            "content_type": "text/html; charset=utf-8",
            "content": html,
            "status_code": 200,
        }
        with patch.object(self.reader, "download", return_value=downloaded):
            result = self.reader.read("https://exemplo.com/noticia")

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["content"])
        self.assertEqual(result["pdf_links"], [])
        self.assertEqual(result["reason"], "")

    def test_html_with_pdf_that_cannot_be_read_is_partial(self):
        article = "Texto da noticia. " * 12
        html = (
            f'<html><body><article>{article}</article>'
            '<a href="/edital.pdf">Baixar edital</a></body></html>'
        ).encode()
        downloaded = {
            "url": "https://exemplo.com/noticia",
            "content_type": "text/html; charset=utf-8",
            "content": html,
            "status_code": 200,
        }
        with patch.object(self.reader, "download", return_value=downloaded), \
             patch.object(self.reader, "read_pdf_url", return_value=""):
            result = self.reader.read("https://exemplo.com/noticia")

        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["content"])
        self.assertEqual(len(result["pdf_links"]), 1)
        self.assertIn("material vinculado", result["reason"])

    def test_unsupported_content_type_is_reported(self):
        downloaded = {
            "url": "https://exemplo.com/arquivo",
            "content_type": "application/octet-stream",
            "content": b"conteudo binario",
            "status_code": 200,
        }
        with patch.object(self.reader, "download", return_value=downloaded):
            result = self.reader.read("https://exemplo.com/arquivo")

        self.assertEqual(result["status"], "unsupported")
        self.assertIn("não suportado", result["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
