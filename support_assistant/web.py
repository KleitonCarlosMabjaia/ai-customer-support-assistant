"""Interface web (Streamlit): o mesmo assistente, agora numa página de internet.

O Streamlit volta a correr este ficheiro de cima a baixo sempre que o
visitante faz alguma coisa (escreve, carrega num botão...). O que tem de
sobreviver entre essas execuções fica guardado em `st.session_state`,
que é diferente para cada visitante.
"""

from __future__ import annotations

import hmac
import logging

import streamlit as st

from support_assistant.assistant import SupportAssistant
from support_assistant.config import Settings, load_settings
from support_assistant.errors import AssistantError, ConfigurationError, InvalidQuestionError
from support_assistant.knowledge_base import load_faq
from support_assistant.products_db import SQLiteProductCatalog
from support_assistant.tools import ToolExecutor

logger = logging.getLogger(__name__)

# Travão de custos: num site público, cada pergunta é paga com a NOSSA chave.
MAX_QUESTIONS_PER_SESSION = 20
EXAMPLE_QUESTIONS = (
    "Quanto custa o envio para a Madeira?",
    "Têm portáteis?",
    "O MacBook Air está disponível?",
)


def create_assistant(settings: Settings) -> SupportAssistant:
    """Monta o assistente com as mesmas peças que a versão de terminal."""
    faq = load_faq()
    catalog = SQLiteProductCatalog()
    return SupportAssistant(settings, faq=faq, tools=ToolExecutor(catalog))


def password_ok(given: str, expected: str) -> bool:
    """Compara palavras-passe em tempo constante, para não dar pistas a quem tenta adivinhar."""
    return hmac.compare_digest(given.encode(), expected.encode())


def main() -> None:
    st.set_page_config(page_title="Apoio ao cliente", page_icon="🤖")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        settings = load_settings()
    except ConfigurationError as e:
        st.error(f"Erro de configuração: {e}")
        return

    st.title(f"🤖 Apoio ao cliente da {settings.company_name}")

    if not _unlocked(settings.app_password):
        return

    state = st.session_state
    if "assistant" not in state:
        try:
            state.assistant = create_assistant(settings)
        except ConfigurationError as e:
            st.error(f"Erro de configuração: {e}")
            return
        state.messages = []  # só para mostrar no ecrã; o histórico "a sério" está no assistente
        state.questions_asked = 0

    _sidebar()

    if not state.messages:
        st.caption("Experimenta perguntar: " + " · ".join(f"“{q}”" for q in EXAMPLE_QUESTIONS))

    # Como o ficheiro corre de novo a cada interação, voltamos a desenhar a conversa toda.
    for message in state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    limit_reached = state.questions_asked >= MAX_QUESTIONS_PER_SESSION
    if limit_reached:
        st.info("Chegaste ao limite de perguntas desta sessão. Obrigado pela visita!")

    question = st.chat_input("Escreve a tua pergunta...", disabled=limit_reached)
    if question:
        _answer(question)


def _unlocked(expected: str) -> bool:
    """Se houver palavra-passe definida, só deixa passar quem a souber."""
    if not expected or st.session_state.get("unlocked"):
        return True

    given = st.text_input("Palavra-passe de acesso", type="password")
    if given and password_ok(given, expected):
        st.session_state.unlocked = True
        st.rerun()  # volta a desenhar a página, agora já com o chat
    elif given:
        st.error("Palavra-passe incorreta.")
    return False


def _sidebar() -> None:
    state = st.session_state
    with st.sidebar:
        st.markdown("**Sobre**")
        st.caption(
            "Assistente de demonstração, feito com Python e a API do Claude. "
            "A loja é fictícia."
        )
        st.caption(f"Perguntas usadas: {state.questions_asked}/{MAX_QUESTIONS_PER_SESSION}")
        if st.button("Nova conversa"):
            state.assistant.reset()
            state.messages = []
            # O contador NÃO volta a zero: senão o limite não serviria de nada.
            st.rerun()


def _answer(question: str) -> None:
    state = st.session_state
    with st.chat_message("user"):
        st.markdown(question)

    try:
        with st.spinner("A pensar..."):
            answer = state.assistant.ask(question)
    except InvalidQuestionError as e:
        st.warning(f"Aviso: {e}")
        return
    except AssistantError as e:  # inclui ConfigurationError e erros temporários
        logger.error("Erro ao responder: %s", e)
        st.error(f"Erro: {e}")
        return

    state.questions_asked += 1
    state.messages += [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ]
    if state.questions_asked >= MAX_QUESTIONS_PER_SESSION:
        # A caixa de texto já foi desenhada ativa; redesenhamos para ela aparecer bloqueada.
        st.rerun()
    with st.chat_message("assistant"):
        st.markdown(answer)
