from app.ai.classifier import NewsClassifier

classifier = NewsClassifier()


def result_base():
    return {
        "is_public_competition": True,
        "has_it_opportunity": True,
        "location": "Dourados/MS",
        "relevance": "confirmed_ms",
        "event_type": "edital_publicado",
        "reason": "Classificação inicial do modelo.",
        "evidence": "O edital menciona cargo técnico.",
    }


def test_libras_not_it():
    news = {
        "title": "Edital para Técnicos Especializados em Libras",
        "summary": "Processo seletivo UFGD",
        "content": "Vagas para Técnico Especializado em Libras.",
        "extraction_status": "success",
    }
    result = classifier._apply_rules(result_base(), news)
    assert result["has_it_opportunity"] is False
    assert result["relevance"] == "irrelevant"


def test_explicit_it_role():
    news = {
        "title": "Concurso com vaga para Analista de Tecnologia da Informação",
        "summary": "Vaga para Analista de TI em Mato Grosso do Sul.",
        "content": "Cargo: Analista de Tecnologia da Informação.",
        "extraction_status": "success",
    }
    result = classifier._apply_rules(result_base(), news)
    assert result["has_it_opportunity"] is True


def test_pre_edictal_without_it_role_goes_to_review():
    news = {
        "title": "Concurso TJ-MS: comissão formada para novo edital",
        "summary": "Comissão organizadora formada.",
        "content": "O edital será publicado futuramente.",
        "extraction_status": "success",
    }
    result = classifier._apply_rules(result_base(), news)
    assert result["is_public_competition"] is True
    assert result["has_it_opportunity"] is False
    assert result["relevance"] == "needs_review"
    assert result["event_type"] == "comissao_formada"


if __name__ == "__main__":
    test_libras_not_it()
    test_explicit_it_role()
    test_pre_edictal_without_it_role_goes_to_review()
    print("3 testes de regras do classificador passaram.")
