"""O núcleo do assistente: envia as perguntas à API do Claude e devolve as respostas."""

from __future__ import annotations

import logging
from typing import Any

import anthropic

from support_assistant.config import Settings
from support_assistant.errors import (
    AssistantAPIError,
    ConfigurationError,
    InvalidQuestionError,
    TemporaryServiceError,
)
from support_assistant.knowledge_base import FAQEntry, format_faq
from support_assistant.tools import ToolExecutor, ToolResult

# Cada módulo tem o seu logger; o nome (__name__) indica de onde vem cada linha no log.
logger = logging.getLogger(__name__)

MAX_QUESTION_LENGTH = 2000
# Funcionalidade beta: se o modelo recusar um pedido por motivos de segurança,
# a API tenta automaticamente com outro modelo adequado ("default").
FALLBACK_BETA = "server-side-fallback-2026-07-01"

REFUSAL_REPLY = (
    "Peço desculpa, mas não consigo ajudar com esse pedido. "
    "Posso ajudar com alguma questão sobre a nossa loja?"
)
EMPTY_REPLY = "Peço desculpa, não consegui gerar uma resposta. Podes reformular a pergunta?"
TRUNCATED_NOTE = "\n\n[A resposta foi cortada por ser demasiado longa.]"

# Número máximo de vezes seguidas que o Claude pode pedir ferramentas numa só pergunta.
MAX_TOOL_ROUNDS = 5
TOOL_LIMIT_REPLY = (
    "Peço desculpa, não consegui encontrar essa informação. "
    "Podes reformular a pergunta ou contactar a nossa equipa de apoio?"
)


def build_system_prompt(company_name: str, faq: list[FAQEntry] | None = None) -> str:
    """Instruções fixas que definem o papel e o comportamento do assistente."""
    prompt = (
        f"És o assistente de apoio ao cliente da {company_name}. "
        "Responde de forma simpática, clara e concisa, no idioma em que o cliente escreve. "
        "Se não souberes a resposta, di-lo com honestidade e sugere contactar a equipa de "
        "apoio humano, em vez de inventar informação sobre produtos, preços ou políticas."
    )
    if not faq:
        return prompt

    # As etiquetas <faq> separam claramente as instruções dos dados,
    # para o modelo saber onde começa e acaba a informação oficial.
    return (
        f"{prompt}\n\n"
        "Para questões sobre a loja (envios, pagamentos, devoluções, garantia, horários...), "
        "usa APENAS a informação oficial dentro de <faq>. Podes reformular as respostas "
        "por palavras tuas, mas nunca acrescentes valores, prazos ou regras que lá não estejam.\n\n"
        f"<faq>\n{format_faq(faq)}\n</faq>"
    )


class SupportAssistant:
    """Mantém uma conversa com um cliente.

    A API é "stateless": não se lembra das mensagens anteriores. Por isso
    guardamos o histórico aqui e enviamo-lo completo em cada pedido.
    """

    def __init__(
        self,
        settings: Settings,
        faq: list[FAQEntry] | None = None,
        tools: ToolExecutor | None = None,
        client: Any | None = None,
    ) -> None:
        # Injeção de dependência: nos testes passamos um cliente falso,
        # na aplicação real criamos o cliente verdadeiro.
        self._settings = settings
        self._client = client or anthropic.Anthropic(
            api_key=settings.api_key,
            timeout=settings.timeout_seconds,
            max_retries=2,  # o SDK repete sozinho em falhas de rede, 429 e 5xx
        )
        self._system_prompt = build_system_prompt(settings.company_name, faq)
        self._tools = tools
        self._history: list[dict[str, Any]] = []

    @property
    def history(self) -> list[dict[str, Any]]:
        """Cópia do histórico, para consulta (não permite alterar o original)."""
        return list(self._history)

    def reset(self) -> None:
        """Começa uma conversa nova."""
        self._history = []

    def ask(self, question: str) -> str:
        """Envia uma pergunta e devolve a resposta em texto."""
        question = self._validate(question)
        messages = [*self._history, {"role": "user", "content": question}]

        response = self._send(messages)

        # O ciclo das ferramentas: ENQUANTO o Claude pedir ferramentas
        # (stop_reason == "tool_use"), executamo-las e enviamos-lhe os resultados.
        tool_rounds = 0
        while response.stop_reason == "tool_use":
            tool_rounds += 1
            if tool_rounds > MAX_TOOL_ROUNDS:
                # Travão de segurança: nunca ficar num ciclo sem fim (e a gastar dinheiro).
                logger.warning("Limite de %d rondas de ferramentas atingido.", MAX_TOOL_ROUNDS)
                return TOOL_LIMIT_REPLY

            messages = [
                *messages,
                # 1) O pedido do Claude (o "bilhete" com os blocos tool_use), sem alterações.
                {"role": "assistant", "content": response.content},
                # 2) As nossas respostas, todas juntas numa única mensagem "user".
                {"role": "user", "content": self._run_tools(response.content)},
            ]
            response = self._send(messages)

        if response.stop_reason == "refusal":
            # Não guardamos este turno: a conversa continua como estava antes.
            logger.info("Pedido recusado pelo modelo.")
            return REFUSAL_REPLY

        # A resposta é uma lista de blocos (texto, raciocínio, ...); só queremos o texto.
        answer = "".join(block.text for block in response.content if block.type == "text").strip()
        if not answer:
            return EMPTY_REPLY
        if response.stop_reason == "max_tokens":
            answer += TRUNCATED_NOTE

        # Guardamos o conteúdo completo da resposta (não só o texto), tal como
        # a API recomenda, para o enviar sem alterações no pedido seguinte.
        self._history = [*messages, {"role": "assistant", "content": response.content}]
        return answer

    def _run_tools(self, content: list[Any]) -> list[dict[str, Any]]:
        """Executa cada ferramenta pedida e devolve os blocos tool_result.

        Cada resultado leva o `tool_use_id` do pedido a que responde, para o
        Claude saber que resposta pertence a que pedido.
        """
        results = []
        for block in content:
            if block.type != "tool_use":
                continue
            if self._tools is None:
                result = ToolResult("Não há ferramentas disponíveis.", is_error=True)
            else:
                result = self._tools.run(block.name, block.input)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result.content,
                    "is_error": result.is_error,
                }
            )
        return results

    @staticmethod
    def _validate(question: str) -> str:
        question = question.strip()
        if not question:
            raise InvalidQuestionError("A pergunta está vazia.")
        if len(question) > MAX_QUESTION_LENGTH:
            raise InvalidQuestionError(
                f"A pergunta é demasiado longa (máximo {MAX_QUESTION_LENGTH} caracteres)."
            )
        return question

    def _send(self, messages: list[dict[str, Any]]) -> Any:
        """Faz o pedido à API e traduz os erros técnicos para as nossas exceções.

        A ordem dos `except` importa: as classes mais específicas vêm primeiro,
        porque por exemplo RateLimitError também é um APIStatusError.
        """
        # Só enviamos o parâmetro `tools` quando há ferramentas.
        extra: dict[str, Any] = {}
        if self._tools is not None:
            extra["tools"] = self._tools.definitions

        try:
            return self._client.beta.messages.create(
                model=self._settings.model,
                max_tokens=self._settings.max_tokens,
                system=self._system_prompt,
                messages=messages,
                output_config={"effort": self._settings.effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
                **extra,
            )
        except anthropic.AuthenticationError as e:
            logger.error("Autenticação falhou: %s", e)
            raise ConfigurationError("A chave da API é inválida. Verifica o ficheiro .env.") from e
        except anthropic.PermissionDeniedError as e:
            logger.error("Sem permissão: %s", e)
            raise ConfigurationError("A chave da API não tem permissão para este pedido.") from e
        except anthropic.NotFoundError as e:
            logger.error("Recurso não encontrado: %s", e)
            raise ConfigurationError(
                f"O modelo '{self._settings.model}' não existe. Verifica ASSISTANT_MODEL."
            ) from e
        except anthropic.RateLimitError as e:
            logger.warning("Limite de pedidos atingido: %s", e)
            raise TemporaryServiceError(
                "Há demasiados pedidos neste momento. Tenta novamente daqui a pouco."
            ) from e
        except anthropic.APIStatusError as e:
            logger.error("Erro da API (%s): %s", e.status_code, e)
            if e.status_code >= 500:
                raise TemporaryServiceError(
                    "O serviço está com problemas. Tenta novamente daqui a pouco."
                ) from e
            raise AssistantAPIError("O pedido foi rejeitado pela API.") from e
        except anthropic.APIConnectionError as e:
            # Inclui APITimeoutError (o pedido demorou demasiado).
            logger.warning("Falha de ligação: %s", e)
            raise TemporaryServiceError(
                "Não foi possível ligar ao serviço. Verifica a tua ligação à internet."
            ) from e
