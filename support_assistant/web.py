"""Interface web (Streamlit): o mesmo assistente, agora numa página de internet.

O Streamlit volta a correr este ficheiro de cima a baixo sempre que o
visitante faz alguma coisa (escreve, carrega num botão...). O que tem de
sobreviver entre essas execuções fica guardado em `st.session_state`,
que é diferente para cada visitante.
"""

from __future__ import annotations

import hmac
import html
import logging
import time
from collections.abc import Iterator

import streamlit as st

from support_assistant.assistant import SupportAssistant
from support_assistant.config import Settings, load_settings
from support_assistant.errors import AssistantError, ConfigurationError, InvalidQuestionError
from support_assistant.knowledge_base import FAQEntry, load_faq
from support_assistant.products import Catalog, Product, normalize
from support_assistant.products_db import SQLiteProductCatalog
from support_assistant.tools import ToolExecutor

logger = logging.getLogger(__name__)

# Travão de custos: num site público, cada pergunta é paga com a NOSSA chave.
MAX_QUESTIONS_PER_SESSION = 20
# Pausa entre palavras no efeito "a escrever" (os testes põem-na a 0).
TYPING_DELAY = 0.03
LOW_STOCK = 3

BOT_AVATAR = "🤖"
USER_AVATAR = "🧑"

VIEW_CHAT = "💬 Conversar"
VIEW_PRODUCTS = "🛍️ Produtos"
VIEW_FAQ = "❓ Perguntas frequentes"
VIEWS = (VIEW_CHAT, VIEW_PRODUCTS, VIEW_FAQ)

WELCOME = (
    "Olá! 👋 Sou o assistente virtual da **{company}**.\n\n"
    "Posso ajudar com envios, pagamentos, devoluções e garantias, "
    "ou dizer-te se um produto está disponível. Em que posso ajudar?"
)
SUGGESTIONS = (
    "🚚 Quanto custa o envio para a Madeira?",
    "💻 Têm portáteis?",
    "↩️ Como faço uma devolução?",
    "🎧 Os auscultadores Sony estão disponíveis?",
)

# O início do código (SKU) diz a categoria: "PC-001" é um portátil.
CATEGORIES = {
    "PC": ("💻", "Portáteis"),
    "TL": ("📱", "Smartphones"),
    "AU": ("🎧", "Áudio"),
    "AC": ("⌨️", "Acessórios"),
}
OTHER_CATEGORY = ("📦", "Outros")

# Aparência extra. As animações são desligadas para quem pediu ao sistema
# operativo "menos movimento" (prefers-reduced-motion).
CSS = """
<style>
.hero {
  display: flex; align-items: center; gap: 1rem;
  padding: 1.25rem 1.5rem; margin-bottom: .5rem; border-radius: 1.25rem;
  background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 55%, #DB2777 100%);
  background-size: 200% 200%; animation: hero-shift 12s ease infinite;
  color: #fff; box-shadow: 0 10px 30px rgba(79, 70, 229, .25);
}
.hero h1 { color: #fff; font-size: 1.6rem; margin: 0; padding: 0; }
.hero p { margin: .2rem 0 0; opacity: .9; }
.hero-emoji { font-size: 2.6rem; animation: wave 2.5s ease-in-out infinite; transform-origin: 70% 70%; }
.hero-status {
  margin-left: auto; white-space: nowrap; font-size: .85rem; font-weight: 600;
  background: rgba(255, 255, 255, .18); padding: .3rem .75rem; border-radius: 999px;
}
.hero-status::before {
  content: ""; display: inline-block; width: .55rem; height: .55rem; margin-right: .4rem;
  border-radius: 50%; background: #4ADE80; animation: pulse 1.8s ease-out infinite;
}
@keyframes hero-shift { 0%, 100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
@keyframes wave { 0%, 60%, 100% { transform: rotate(0); } 10%, 30% { transform: rotate(14deg); } 20%, 40% { transform: rotate(-8deg); } }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(74, 222, 128, .7); } 100% { box-shadow: 0 0 0 .6rem rgba(74, 222, 128, 0); } }

[data-testid="stChatMessage"] { animation: fade-up .35s ease-out; }
@keyframes fade-up { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

[class*="st-key-card_"] { transition: transform .2s ease, box-shadow .2s ease; }
[class*="st-key-card_"]:hover { transform: translateY(-4px); box-shadow: 0 12px 24px rgba(0, 0, 0, .12); }
.product-emoji { font-size: 2.4rem; line-height: 1; }
.product-price { font-size: 1.5rem; font-weight: 700; }

@media (max-width: 640px) {
  .hero { flex-wrap: wrap; padding: 1rem; }
  .hero-status { margin-left: 0; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before { animation: none !important; transition: none !important; }
}
</style>
"""


# ---------- Funções simples (sem Streamlit), fáceis de testar ----------


def password_ok(given: str, expected: str) -> bool:
    """Compara palavras-passe em tempo constante, para não dar pistas a quem tenta adivinhar."""
    return hmac.compare_digest(given.encode(), expected.encode())


def format_price(price: float) -> str:
    """Formato português: 1199.0 -> "1 199,00 €"."""
    text = f"{price:,.2f}"  # "1,199.00" (formato inglês)
    return text.replace(",", " ").replace(".", ",") + " €"


def stock_status(stock: int) -> tuple[str, str]:
    """Devolve o texto e a cor da etiqueta de stock."""
    if stock == 0:
        return "Esgotado", "red"
    if stock <= LOW_STOCK:
        return f"Últimas {stock} unidades", "orange"
    return "Em stock", "green"


def category_of(product: Product) -> tuple[str, str]:
    """Devolve o emoji e o nome da categoria, a partir do início do código."""
    return CATEGORIES.get(product.sku.split("-")[0], OTHER_CATEGORY)


def filter_products(
    products: list[Product], query: str = "", category: str | None = None, only_available: bool = False
) -> list[Product]:
    """Filtros da montra: palavras no nome (sem acentos), categoria e disponibilidade."""
    words = normalize(query).split()
    return [
        p
        for p in products
        if all(word in normalize(p.name) for word in words)
        and (category is None or category_of(p)[1] == category)
        and (not only_available or p.stock > 0)
    ]


def filter_faq(entries: list[FAQEntry], query: str) -> list[FAQEntry]:
    """Procura as palavras na pergunta e na resposta (sem acentos)."""
    words = normalize(query).split()
    return [e for e in entries if all(w in normalize(f"{e.question} {e.answer}") for w in words)]


def transcript(messages: list[dict]) -> str:
    """A conversa em texto simples, para o visitante descarregar."""
    names = {"user": "Tu", "assistant": "Assistente"}
    return "\n\n".join(f"{names[m['role']]}: {m['content']}" for m in messages)


# ---------- Montagem do assistente ----------


@st.cache_resource
def load_store() -> tuple[list[FAQEntry], Catalog]:
    """As FAQ e o catálogo são iguais para todos: carregam-se uma vez e partilham-se."""
    return load_faq(), SQLiteProductCatalog()


def create_assistant(settings: Settings, faq: list[FAQEntry], catalog: Catalog) -> SupportAssistant:
    """Monta o assistente com as mesmas peças que a versão de terminal."""
    return SupportAssistant(settings, faq=faq, tools=ToolExecutor(catalog))


# ---------- A página ----------


def main() -> None:
    st.set_page_config(page_title="Apoio ao cliente", page_icon="🤖")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    st.html(CSS)

    try:
        settings = load_settings()
        faq, catalog = load_store()
    except ConfigurationError as e:
        st.error(f"Erro de configuração: {e}")
        return

    _hero(settings.company_name)
    if not _unlocked(settings.app_password):
        return

    state = st.session_state
    if "assistant" not in state:
        state.assistant = create_assistant(settings, faq, catalog)
        state.messages = []  # só para mostrar no ecrã; o histórico "a sério" está no assistente
        state.questions_asked = 0
        state.next_message_id = 0
    if "view" not in state:
        state.view = VIEW_CHAT

    _sidebar()

    view = st.segmented_control(
        "Secção", VIEWS, key="view", required=True, label_visibility="collapsed", width="stretch"
    )
    if view == VIEW_PRODUCTS:
        _products_view(catalog)
    elif view == VIEW_FAQ:
        _faq_view(faq)
    else:
        _chat_view(settings.company_name)


def _hero(company: str) -> None:
    st.html(
        '<div class="hero"><div class="hero-emoji">🤖</div>'
        f"<div><h1>Apoio ao cliente</h1><p>{html.escape(company)} · respostas em segundos</p></div>"
        '<span class="hero-status">Online</span></div>'
    )


def _unlocked(expected: str) -> bool:
    """Se houver palavra-passe definida, só deixa passar quem a souber."""
    if not expected or st.session_state.get("unlocked"):
        return True

    given = st.text_input("🔒 Palavra-passe de acesso", type="password")
    if given and password_ok(given, expected):
        st.session_state.unlocked = True
        st.rerun()  # volta a desenhar a página, agora já com o chat
    elif given:
        st.error("Palavra-passe incorreta.")
    return False


def _sidebar() -> None:
    state = st.session_state
    with st.sidebar:
        st.markdown("### 🧭 A tua sessão")
        used = state.questions_asked
        st.progress(used / MAX_QUESTIONS_PER_SESSION, text=f"Perguntas: {used}/{MAX_QUESTIONS_PER_SESSION}")

        if st.button("🔄 Nova conversa", width="stretch", disabled=not state.messages):
            state.assistant.reset()
            state.messages = []
            # O contador NÃO volta a zero: senão o limite não serviria de nada.
            st.toast("Conversa nova. Pergunta à vontade!", icon="✨")
            st.rerun()

        st.download_button(
            "⬇️ Descarregar conversa",
            data=transcript(state.messages),
            file_name="conversa.txt",
            mime="text/plain",
            width="stretch",
            disabled=not state.messages,
        )

        st.divider()
        st.caption(
            "Assistente de demonstração, feito com Python e a API do Claude. "
            "A loja e os produtos são fictícios."
        )


def _ask_later(question: str) -> None:
    """Chamada por um botão: guarda a pergunta e leva o visitante para o chat.

    Corre ANTES de a página ser redesenhada, por isso pode mudar a secção escolhida.
    """
    st.session_state.pending_question = question
    st.session_state.view = VIEW_CHAT


# ---------- Secção: conversar ----------


def _chat_view(company: str) -> None:
    state = st.session_state

    with st.chat_message("assistant", avatar=BOT_AVATAR):
        st.markdown(WELCOME.format(company=company))

    # Como o ficheiro corre de novo a cada interação, voltamos a desenhar a conversa toda.
    for message in state.messages:
        is_bot = message["role"] == "assistant"
        with st.chat_message(message["role"], avatar=BOT_AVATAR if is_bot else USER_AVATAR):
            st.markdown(message["content"])
            if is_bot:
                st.feedback(
                    "thumbs", key=f"feedback_{message['id']}", on_change=_thank, args=(message["id"],)
                )

    if not state.messages:
        st.caption("Experimenta uma destas:")
        with st.container(horizontal=True):
            for i, suggestion in enumerate(SUGGESTIONS):
                question = suggestion.split(" ", 1)[1]  # sem o emoji
                st.button(suggestion, key=f"suggestion_{i}", on_click=_ask_later, args=(question,))

    limit_reached = state.questions_asked >= MAX_QUESTIONS_PER_SESSION
    if limit_reached:
        st.info("Chegaste ao limite de perguntas desta sessão. Obrigado pela visita! 💙")

    typed = st.chat_input("Escreve a tua pergunta...", disabled=limit_reached)
    question = typed or state.pop("pending_question", None)
    if question and not limit_reached:
        _answer(question)


def _thank(message_id: int) -> None:
    liked = st.session_state[f"feedback_{message_id}"] == 1
    logger.info("Feedback na mensagem %d: %s", message_id, "positivo" if liked else "negativo")
    if liked:
        st.toast("Obrigado! Ainda bem que ajudou.", icon="💙")
    else:
        st.toast("Obrigado pelo aviso! Experimenta reformular a pergunta.", icon="🙏")


def _typing(text: str) -> Iterator[str]:
    """Entrega a resposta palavra a palavra, como se alguém estivesse a escrever."""
    for word in text.split(" "):
        yield word + " "
        time.sleep(TYPING_DELAY)


def _answer(question: str) -> None:
    state = st.session_state
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(question)

    with st.chat_message("assistant", avatar=BOT_AVATAR):
        try:
            with st.spinner("A escrever..."):
                answer = state.assistant.ask(question)
        except InvalidQuestionError as e:
            st.warning(f"Aviso: {e}")
            return
        except AssistantError as e:  # inclui ConfigurationError e erros temporários
            logger.error("Erro ao responder: %s", e)
            st.error(f"Erro: {e}")
            return
        st.write_stream(_typing(answer))

    state.questions_asked += 1
    for role, content in (("user", question), ("assistant", answer)):
        state.messages.append({"id": state.next_message_id, "role": role, "content": content})
        state.next_message_id += 1
    # Redesenha a página: aparecem os botões 👍/👎, o contador atualizado
    # e, se o limite foi atingido, a caixa de texto bloqueada.
    st.rerun()


# ---------- Secção: produtos ----------


def _products_view(catalog: Catalog) -> None:
    query = st.text_input(
        "Procurar produto", placeholder="🔎 Procurar (ex.: iphone, sony...)", label_visibility="collapsed"
    )
    category_names = [f"{emoji} {name}" for emoji, name in CATEGORIES.values()]
    chosen = st.pills("Categoria", category_names, label_visibility="collapsed")
    only_available = st.toggle("Mostrar só produtos disponíveis")

    category = chosen.split(" ", 1)[1] if chosen else None
    products = filter_products(catalog.list_all(), query, category, only_available)

    if not products:
        st.info("Não encontrámos nenhum produto com esses filtros. 🤔")
        if query.strip():
            st.button(
                f"💬 Perguntar ao assistente sobre “{query.strip()}”",
                on_click=_ask_later,
                args=(f"Têm {query.strip()}?",),
            )
        return

    st.caption(f"{len(products)} produto(s)")
    columns = st.columns(2)
    for i, product in enumerate(products):
        with columns[i % 2]:
            _product_card(product)


def _product_card(product: Product) -> None:
    emoji, category = category_of(product)
    label, color = stock_status(product.stock)
    with st.container(border=True, key=f"card_{product.sku}"):
        st.html(f'<div class="product-emoji">{emoji}</div>')
        st.markdown(f"**{product.name}**")
        st.caption(f"{category} · {product.sku}")
        st.html(f'<div class="product-price">{format_price(product.price)}</div>')
        st.badge(label, color=color)
        st.button(
            "💬 Perguntar ao assistente",
            key=f"ask_{product.sku}",
            width="stretch",
            on_click=_ask_later,
            args=(f"O {product.name} está disponível?",),
        )


# ---------- Secção: perguntas frequentes ----------


def _faq_view(faq: list[FAQEntry]) -> None:
    query = st.text_input(
        "Procurar nas perguntas frequentes",
        placeholder="🔎 Procurar (ex.: devolução, MB WAY...)",
        label_visibility="collapsed",
    )
    entries = filter_faq(faq, query)
    if not entries:
        st.info("Nenhuma pergunta frequente fala disso. 🤔")
        st.button("💬 Perguntar ao assistente", on_click=_ask_later, args=(query.strip(),))
        return

    for entry in entries:
        with st.expander(entry.question):
            st.markdown(entry.answer)
