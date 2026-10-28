"""Testes da base de conhecimento (FAQ).

`tmp_path` é uma "fixture" do pytest: uma pasta temporária, nova em cada teste
e apagada no fim. Usamo-la para criar ficheiros JSON de teste sem tocar no
ficheiro verdadeiro data/faq.json.
"""

import json

import pytest

from support_assistant.errors import ConfigurationError
from support_assistant.knowledge_base import DEFAULT_FAQ_PATH, FAQEntry, format_faq, load_faq


def write_json(path, data):
    """Grava `data` em formato JSON e devolve o caminho do ficheiro."""
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_load_valid_file(tmp_path):
    path = write_json(
        tmp_path / "faq.json",
        [{"pergunta": "  Qual é o horário?  ", "resposta": "Das 9h às 19h."}],
    )

    assert load_faq(path) == [FAQEntry(question="Qual é o horário?", answer="Das 9h às 19h.")]


def test_real_faq_file_is_valid():
    # Garante que o ficheiro que vai com o projeto está sempre bem escrito.
    assert len(load_faq(DEFAULT_FAQ_PATH)) > 0


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigurationError, match="não encontrado"):
        load_faq(tmp_path / "nao_existe.json")


def test_invalid_json_raises(tmp_path):
    path = tmp_path / "faq.json"
    path.write_text('[{"pergunta": "Olá",}]', encoding="utf-8")  # vírgula a mais

    with pytest.raises(ConfigurationError, match="não é JSON válido"):
        load_faq(path)


@pytest.mark.parametrize("data", [[], {"pergunta": "x", "resposta": "y"}, "texto"])
def test_content_must_be_non_empty_list(tmp_path, data):
    path = write_json(tmp_path / "faq.json", data)

    with pytest.raises(ConfigurationError, match="lista de FAQ"):
        load_faq(path)


@pytest.mark.parametrize(
    ("entry", "missing_field"),
    [
        ({"pergunta": "Fazem entregas nas ilhas?"}, "resposta"),
        ({"resposta": "Sim."}, "pergunta"),
        ({"pergunta": "Olá?", "resposta": "   "}, "resposta"),
        ({"pergunta": 123, "resposta": "Sim."}, "pergunta"),
    ],
)
def test_entry_with_missing_field_raises(tmp_path, entry, missing_field):
    valid = {"pergunta": "Qual é o horário?", "resposta": "Das 9h às 19h."}
    path = write_json(tmp_path / "faq.json", [valid, entry])

    # A mensagem deve indicar QUAL entrada (a 2.ª) e QUAL campo tem o problema.
    with pytest.raises(ConfigurationError, match=f'entrada 2 .* "{missing_field}"'):
        load_faq(path)


def test_entry_that_is_not_an_object_raises(tmp_path):
    path = write_json(tmp_path / "faq.json", ["isto não é um objeto"])

    with pytest.raises(ConfigurationError, match="entrada 1"):
        load_faq(path)


def test_format_faq():
    entries = [
        FAQEntry(question="Pergunta 1?", answer="Resposta 1."),
        FAQEntry(question="Pergunta 2?", answer="Resposta 2."),
    ]

    assert format_faq(entries) == "P: Pergunta 1?\nR: Resposta 1.\n\nP: Pergunta 2?\nR: Resposta 2."
