"""Testes do SupportAssistant.

Nenhum teste chama a API verdadeira: usamos um cliente falso (MagicMock).
Assim os testes são rápidos, gratuitos, não precisam de internet e dão
sempre o mesmo resultado.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx2
import pytest

from support_assistant.assistant import (
    MAX_QUESTION_LENGTH,
    MAX_TOOL_ROUNDS,
    REFUSAL_REPLY,
    TOOL_LIMIT_REPLY,
    TRUNCATED_NOTE,
    SupportAssistant,
)
from support_assistant.config import Settings
from support_assistant.errors import (
    AssistantAPIError,
    ConfigurationError,
    InvalidQuestionError,
    TemporaryServiceError,
)
from support_assistant.knowledge_base import FAQEntry
from support_assistant.products import Product, ProductCatalog
from support_assistant.tools import SEARCH_PRODUCTS, ToolExecutor

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def make_response(text="Olá! Em que posso ajudar?", stop_reason="end_turn"):
    """Cria um objeto com o mesmo formato de uma resposta da API."""
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
    )


def make_tool_use_response(query="lenovo", tool_id="toolu_01"):
    """Cria uma resposta em que o Claude pede para usar a ferramenta de produtos."""
    return SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use", id=tool_id, name=SEARCH_PRODUCTS, input={"pesquisa": query}
            )
        ],
        stop_reason="tool_use",
    )


def make_status_error(error_class, status_code):
    """Cria um erro HTTP da biblioteca anthropic, como se viesse da API."""
    response = httpx2.Response(status_code, request=REQUEST)
    return error_class("erro simulado", response=response, body=None)


@pytest.fixture
def settings():
    return Settings(api_key="sk-ant-teste", company_name="TechLoja")


@pytest.fixture
def fake_client():
    client = MagicMock()
    client.beta.messages.create.return_value = make_response()
    return client


@pytest.fixture
def assistant(settings, fake_client):
    return SupportAssistant(settings, client=fake_client)


@pytest.fixture
def tools():
    laptop = Product(sku="PC-001", name="Portátil Lenovo IdeaPad", price=799.0, stock=5)
    return ToolExecutor(ProductCatalog([laptop]))


@pytest.fixture
def assistant_with_tools(settings, fake_client, tools):
    return SupportAssistant(settings, tools=tools, client=fake_client)


def test_ask_returns_answer_text(assistant):
    assert assistant.ask("Olá") == "Olá! Em que posso ajudar?"


def test_ask_sends_expected_request(assistant, fake_client, settings):
    assistant.ask("  Qual é o horário?  ")

    kwargs = fake_client.beta.messages.create.call_args.kwargs
    assert kwargs["model"] == settings.model
    assert kwargs["messages"] == [{"role": "user", "content": "Qual é o horário?"}]
    assert "TechLoja" in kwargs["system"]
    assert kwargs["output_config"] == {"effort": "medium"}


def test_faq_is_included_in_system_prompt(settings, fake_client):
    faq = [FAQEntry(question="Qual é o prazo de devolução?", answer="30 dias.")]
    assistant = SupportAssistant(settings, faq=faq, client=fake_client)

    assistant.ask("Posso devolver?")

    system = fake_client.beta.messages.create.call_args.kwargs["system"]
    assert "<faq>" in system
    assert "P: Qual é o prazo de devolução?\nR: 30 dias." in system


def test_without_faq_system_prompt_has_no_faq_section(assistant, fake_client):
    assistant.ask("Olá")

    assert "<faq>" not in fake_client.beta.messages.create.call_args.kwargs["system"]


def test_tool_definitions_are_sent(assistant_with_tools, fake_client, tools):
    assistant_with_tools.ask("Olá")

    assert fake_client.beta.messages.create.call_args.kwargs["tools"] == tools.definitions


def test_without_tools_no_tools_parameter_is_sent(assistant, fake_client):
    assistant.ask("Olá")

    assert "tools" not in fake_client.beta.messages.create.call_args.kwargs


def test_tool_is_executed_and_result_sent_back(assistant_with_tools, fake_client):
    # 1.º pedido: o Claude pede a ferramenta. 2.º pedido: o Claude dá a resposta final.
    fake_client.beta.messages.create.side_effect = [
        make_tool_use_response(query="lenovo", tool_id="toolu_01"),
        make_response(text="Sim, temos o Lenovo por 799 €."),
    ]

    answer = assistant_with_tools.ask("Têm o portátil Lenovo?")

    assert answer == "Sim, temos o Lenovo por 799 €."
    assert fake_client.beta.messages.create.call_count == 2

    # No 2.º pedido vão: a pergunta, o pedido do Claude e o nosso resultado.
    messages = fake_client.beta.messages.create.call_args.kwargs["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    [tool_result] = messages[2]["content"]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "toolu_01"  # tem de corresponder ao pedido
    assert tool_result["is_error"] is False
    assert "PC-001" in tool_result["content"]


def test_tool_exchange_is_kept_in_history(assistant_with_tools, fake_client):
    fake_client.beta.messages.create.side_effect = [
        make_tool_use_response(),
        make_response(text="Temos sim."),
    ]

    assistant_with_tools.ask("Têm o Lenovo?")

    roles = [m["role"] for m in assistant_with_tools.history]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_tool_loop_stops_after_limit(assistant_with_tools, fake_client):
    # O Claude pede ferramentas sem parar: o travão de segurança tem de atuar.
    fake_client.beta.messages.create.return_value = make_tool_use_response()

    assert assistant_with_tools.ask("Têm o Lenovo?") == TOOL_LIMIT_REPLY
    assert fake_client.beta.messages.create.call_count == MAX_TOOL_ROUNDS + 1
    assert assistant_with_tools.history == []


def test_history_is_sent_on_next_question(assistant, fake_client):
    assistant.ask("Primeira pergunta")
    assistant.ask("Segunda pergunta")

    messages = fake_client.beta.messages.create.call_args.kwargs["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[0]["content"] == "Primeira pergunta"
    assert messages[2]["content"] == "Segunda pergunta"


def test_reset_clears_history(assistant):
    assistant.ask("Olá")
    assistant.reset()

    assert assistant.history == []


@pytest.mark.parametrize("question", ["", "   ", "x" * (MAX_QUESTION_LENGTH + 1)])
def test_invalid_question_raises_without_calling_api(assistant, fake_client, question):
    with pytest.raises(InvalidQuestionError):
        assistant.ask(question)

    fake_client.beta.messages.create.assert_not_called()


def test_refusal_returns_polite_reply_and_keeps_history(assistant, fake_client):
    fake_client.beta.messages.create.return_value = make_response(text="", stop_reason="refusal")

    assert assistant.ask("Pedido problemático") == REFUSAL_REPLY
    assert assistant.history == []


def test_truncated_answer_gets_note(assistant, fake_client):
    fake_client.beta.messages.create.return_value = make_response(
        text="Resposta longa", stop_reason="max_tokens"
    )

    assert assistant.ask("Explica tudo") == "Resposta longa" + TRUNCATED_NOTE


@pytest.mark.parametrize(
    ("api_error", "expected"),
    [
        (make_status_error(anthropic.AuthenticationError, 401), ConfigurationError),
        (make_status_error(anthropic.PermissionDeniedError, 403), ConfigurationError),
        (make_status_error(anthropic.NotFoundError, 404), ConfigurationError),
        (make_status_error(anthropic.BadRequestError, 400), AssistantAPIError),
        (make_status_error(anthropic.RateLimitError, 429), TemporaryServiceError),
        (make_status_error(anthropic.InternalServerError, 500), TemporaryServiceError),
        (anthropic.APIConnectionError(request=REQUEST), TemporaryServiceError),
        (anthropic.APITimeoutError(request=REQUEST), TemporaryServiceError),
    ],
)
def test_api_errors_are_translated(assistant, fake_client, api_error, expected):
    fake_client.beta.messages.create.side_effect = api_error

    with pytest.raises(expected):
        assistant.ask("Olá")

    # Um pedido falhado não deve ficar no histórico.
    assert assistant.history == []
