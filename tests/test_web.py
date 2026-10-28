from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from support_assistant import web
from support_assistant.errors import TemporaryServiceError

# AppTest abre a página num "browser de faz de conta", sem rede e sem custos.
APP_FILE = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


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
    assistant = FakeAssistant()
    monkeypatch.setattr(web, "create_assistant", lambda settings: assistant)
    return assistant


def open_app():
    return AppTest.from_file(APP_FILE).run()


def test_question_and_answer_appear_in_chat(fake):
    app = open_app()

    app.chat_input[0].set_value("Têm portáteis?").run()

    assert fake.questions == ["Têm portáteis?"]
    texts = [m.markdown[0].value for m in app.chat_message]
    assert texts == ["Têm portáteis?", "Resposta a: Têm portáteis?"]


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


def test_password_ok():
    assert web.password_ok("abc", "abc") is True
    assert web.password_ok("abd", "abc") is False
