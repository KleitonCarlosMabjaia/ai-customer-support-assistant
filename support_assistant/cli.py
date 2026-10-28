"""Interface de terminal: o cliente escreve perguntas e lê as respostas."""

from __future__ import annotations

import logging
import sys

from support_assistant.assistant import SupportAssistant
from support_assistant.config import load_settings
from support_assistant.errors import AssistantError, ConfigurationError, InvalidQuestionError
from support_assistant.knowledge_base import load_faq
from support_assistant.products_db import SQLiteProductCatalog
from support_assistant.tools import ToolExecutor

EXIT_COMMANDS = {"sair", "exit", "quit"}
RESET_COMMAND = "/novo"
LOG_FILE = "assistant.log"


def main() -> int:
    """Ponto de entrada. Devolve o código de saída (0 = sucesso, 1 = erro)."""
    # Os detalhes técnicos vão para um ficheiro; o utilizador só vê mensagens amigáveis.
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )

    try:
        settings = load_settings()
        faq = load_faq()
        catalog = SQLiteProductCatalog()
    except ConfigurationError as e:
        print(f"Erro de configuração: {e}", file=sys.stderr)
        return 1

    tools = ToolExecutor(catalog)
    assistant = SupportAssistant(settings, faq=faq, tools=tools)
    print(f"Assistente de apoio ao cliente da {settings.company_name}")
    print(f"Escreve a tua pergunta. '{RESET_COMMAND}' começa uma conversa nova, 'sair' termina.")

    while True:
        try:
            question = input("\nTu: ")
        except (EOFError, KeyboardInterrupt):  # Ctrl+Z / Ctrl+C
            print("\nAté breve!")
            return 0

        command = question.strip().lower()
        if command in EXIT_COMMANDS:
            print("Até breve!")
            return 0
        if command == RESET_COMMAND:
            assistant.reset()
            print("Conversa reiniciada.")
            continue

        try:
            answer = assistant.ask(question)
        except InvalidQuestionError as e:
            print(f"Aviso: {e}")
            continue
        except ConfigurationError as e:
            # Sem configuração válida não vale a pena continuar.
            print(f"Erro de configuração: {e}", file=sys.stderr)
            return 1
        except AssistantError as e:
            print(f"Erro: {e}")
            continue

        print(f"\nAssistente: {answer}")
