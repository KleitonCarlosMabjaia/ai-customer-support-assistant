from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from support_assistant import web
from support_assistant.errors import TemporaryServiceError
from support_assistant.knowledge_base import FAQEntry
from support_assistant.products import Product, ProductCatalog

# AppTest abre a página num "browser de faz de conta", sem rede e sem custos.
APP_FILE = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")

LAPTOP = Product(sku="PC-001", name="Portátil Lenovo IdeaPad", price=799.0, stock=5)
PHONE = Product(sku="TL-001", name="Smartphone Apple iPhone 16", price=1199.0, stock=0)
HEADPHONES = Product(sku="AU-001", name="Auscultadores Sony", price=349.0, stock=2)
PRODUCTS = [LAPTOP, PHONE, HEADPHONES]

FAQ = [
    FAQEntry("Fazem devoluções?", "Sim, até 30 dias."),
    FAQEntry("Que pagamentos aceitam?", "MB WAY e cartão."),
]


class FakeAssistant:
    """Duplo do SupportAssistant: responde sem chamar a API."""

    def __init__(self, error=None):
        self.error = error
        self.questions = []

    def ask(self, question):
        if self.error:
            raise self.error
        self.questions.append(question)
        return f"Resposta a: {question}"

    def reset(self):
        self.questions = []


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-teste")
    monkeypatch.setenv("APP_PASSWORD", "")
    monkeypatch.setattr(web, "TYPING_DELAY", 0)
    monkeypatch.setattr(web, "load_store", lambda: (FAQ, ProductCatalog(PRODUCTS)))
    assistant = FakeAssistant()
    monkeypatch.setattr(web, "create_assistant", lambda settings, faq, catalog: assistant)
    return assistant


def open_app(view=None):
    # 10 s de margem: a primeira execução é mais lenta (o Python ainda está a carregar tudo).
    app = AppTest.from_file(APP_FILE, default_timeout=10)
    if view:
        app.session_state["view"] = view
    return app.run()


def chat_texts(app):
    return [m.markdown[0].value for m in app.chat_message]


# ---------- Conversar ----------


def test_chat_starts_with_welcome_and_suggestions(fake):
    app = open_app()

    assert "assistente virtual" in chat_texts(app)[0]
    assert app.button(key="suggestion_0") is not None


def test_question_and_answer_appear_in_chat(fake):
    app = open_app()

    app.chat_input[0].set_value("Têm portáteis?").run()

    assert fake.questions == ["Têm portáteis?"]
    assert chat_texts(app)[-2:] == ["Têm portáteis?", "Resposta a: Têm portáteis?"]


def test_suggestion_button_asks_the_question(fake):
    app = open_app()

    app.button(key="suggestion_1").click().run()

    assert fake.questions == ["Têm portáteis?"]


def test_assistant_error_is_shown_as_message(fake):
    fake.error = TemporaryServiceError("O serviço está com problemas.")
    app = open_app()

    app.chat_input[0].set_value("Olá").run()

    assert "O serviço está com problemas." in app.error[0].value


def test_question_limit_disables_input(fake, monkeypatch):
    monkeypatch.setattr(web, "MAX_QUESTIONS_PER_SESSION", 1)
    app = open_app()

    app.chat_input[0].set_value("Olá").run()

    assert app.chat_input[0].disabled is True
    assert "limite" in app.info[0].value


# ---------- Produtos e FAQ ----------


def test_product_card_button_asks_about_the_product(fake):
    app = open_app(view=web.VIEW_PRODUCTS)

    app.button(key="ask_PC-001").click().run()

    assert app.session_state["view"] == web.VIEW_CHAT
    assert fake.questions == ["O Portátil Lenovo IdeaPad está disponível?"]


def test_faq_view_shows_entries(fake):
    app = open_app(view=web.VIEW_FAQ)

    assert [e.label for e in app.expander] == ["Fazem devoluções?", "Que pagamentos aceitam?"]


# ---------- Arranque e palavra-passe ----------


def test_missing_key_shows_configuration_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    app = open_app()

    assert "ANTHROPIC_API_KEY" in app.error[0].value
    assert len(app.chat_input) == 0


def test_password_protects_the_chat(fake, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "segredo123")
    app = open_app()
    assert len(app.chat_input) == 0  # sem palavra-passe, não há chat

    app.text_input[0].input("errada").run()
    assert "incorreta" in app.error[0].value
    assert len(app.chat_input) == 0

    app.text_input[0].input("segredo123").run()
    assert len(app.chat_input) == 1


# ---------- Funções simples ----------


def test_password_ok():
    assert web.password_ok("abc", "abc") is True
    assert web.password_ok("abd", "abc") is False


@pytest.mark.parametrize(
    ("price", "expected"), [(99.9, "99,90 €"), (1199.0, "1 199,00 €"), (0, "0,00 €")]
)
def test_format_price_uses_portuguese_format(price, expected):
    assert web.format_price(price) == expected


@pytest.mark.parametrize(
    ("stock", "color"), [(0, "red"), (1, "orange"), (web.LOW_STOCK, "orange"), (20, "green")]
)
def test_stock_status_colors(stock, color):
    assert web.stock_status(stock)[1] == color


def test_category_comes_from_sku():
    assert web.category_of(LAPTOP) == ("💻", "Portáteis")
    assert web.category_of(Product("ZZ-1", "Coisa", 1.0, 1)) == web.OTHER_CATEGORY


def test_filter_products():
    assert web.filter_products(PRODUCTS, "portatil") == [LAPTOP]
    assert web.filter_products(PRODUCTS, category="Smartphones") == [PHONE]
    assert web.filter_products(PRODUCTS, only_available=True) == [LAPTOP, HEADPHONES]
    assert web.filter_products(PRODUCTS, "bicicleta") == []


def test_filter_faq_searches_question_and_answer():
    assert web.filter_faq(FAQ, "mb way") == [FAQ[1]]
    assert web.filter_faq(FAQ, "DEVOLUCOES") == [FAQ[0]]
    assert web.filter_faq(FAQ, "") == FAQ


def test_transcript():
    messages = [{"role": "user", "content": "Olá"}, {"role": "assistant", "content": "Olá! 👋"}]

    assert web.transcript(messages) == "Tu: Olá\n\nAssistente: Olá! 👋"
