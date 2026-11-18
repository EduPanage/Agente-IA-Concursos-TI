
import requests
import json


class NewsClassifier:

    def __init__(self):

        self.api_url = "http://localhost:11434/api/chat"
        self.model = "qwen2.5:3b"

    def classify(self, news):

        prompt = f"""
Você é um analista especializado em concursos públicos brasileiros.

Sua tarefa é identificar oportunidades REAIS de Tecnologia
da Informação para acompanhamento em Dourados/MS.

Analise exclusivamente as informações fornecidas.

NOTÍCIA:
Título: {news.get('title', '')}
Resumo: {news.get('summary', '')}
Localidade preliminar: {news.get('location', '')}
Fonte: {news.get('source', '')}

REGRAS OBRIGATÓRIAS:

1. CONCURSO PÚBLICO
Identifique se a publicação trata efetivamente de concurso
público, processo seletivo público ou atualização de um deles.

Cursos, especializações, pós-graduações e notícias genéricas
não são oportunidades de concurso.

2. TECNOLOGIA DA INFORMAÇÃO
Só considere uma oportunidade de TI quando houver evidência
de cargo, vaga ou atribuição relacionada à tecnologia.

Exemplos:
- Analista de Sistemas
- Analista de TI
- Técnico de Informática
- Desenvolvedor
- Programador
- Administrador de Redes
- Segurança da Informação
- Banco de Dados
- Infraestrutura de TI
- Suporte Técnico

A simples menção a tecnologia em uma notícia não significa
que existam vagas de TI.

3. LOCALIZAÇÃO
NUNCA presuma que uma vaga existe em Dourados ou MS.

confirmed_dourados:
Somente quando o conteúdo indicar explicitamente vagas
ou lotação em Dourados/MS.

confirmed_ms:
Somente quando o conteúdo indicar explicitamente vagas
ou lotação em Mato Grosso do Sul, sem confirmação de Dourados.

national_unknown:
Somente para concurso federal ou nacional com oportunidade
de TI identificada, mas sem lotação definida.

other_state:
Quando as vagas estiverem explicitamente destinadas
a outro estado, sem possibilidade identificada em MS.

not_identified:
Quando não houver informações suficientes sobre a localização.

4. PROIBIÇÕES
- Não invente vagas.
- Não invente cargos.
- Não invente localidades.
- Não associe concursos de outros estados a Dourados.
- Não considere que todo concurso nacional oferece vagas em MS.
- Não utilize o interesse do usuário como evidência geográfica.
- Não confunda concursos administrativos com concursos de TI.

5. TIPO DE NOVIDADE

Identifique:
- Concurso autorizado
- Comissão formada
- Banca definida
- Edital publicado
- Inscrições abertas
- Retificação
- Convocação ou nomeação
- Outra atualização
- Não identificado

6. EVIDÊNCIAS

O campo evidence deve conter um trecho literal do título
ou resumo que sustente a classificação.

Se não existir evidência, escreva "Não identificado".

Responda exclusivamente em JSON válido:

{{
    "is_public_competition": false,
    "has_it_opportunity": false,
    "location": "Não identificada",
    "relevance": "irrelevant",
    "event_type": "Não identificado",
    "reason": "Justificativa objetiva",
    "evidence": "Trecho literal ou Não identificado"
}}

Valores permitidos para relevance:
- confirmed_dourados
- confirmed_ms
- national_unknown
- other_state
- needs_review
- irrelevant
"""

        try:

            response = requests.post(
                self.api_url,
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "format": "json",
                    "stream": False,
                    "options": {
                        "temperature": 0
                    }
                },
                timeout=120
            )

            response.raise_for_status()

            content = response.json()["message"]["content"]

            result = json.loads(content)

            allowed_relevance = {
                "confirmed_dourados",
                "confirmed_ms",
                "national_unknown",
                "other_state",
                "needs_review",
                "irrelevant"
            }

            if result.get("relevance") not in allowed_relevance:
                raise ValueError("Classificação inválida.")

            if not isinstance(
                result.get("is_public_competition"), bool
            ):
                raise ValueError("Campo de concurso inválido.")

            if not isinstance(
                result.get("has_it_opportunity"), bool
            ):
                raise ValueError("Campo de TI inválido.")

            # Impedir classificações incompatíveis
            if (
                not result["is_public_competition"]
                or not result["has_it_opportunity"]
            ):
                result["relevance"] = "irrelevant"

            return result

        except (
            requests.RequestException,
            KeyError,
            ValueError,
            json.JSONDecodeError
        ) as error:

            print(f"Erro na classificação: {error}")

            return None
