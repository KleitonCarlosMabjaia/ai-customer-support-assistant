import pytest

from support_assistant.config import DEFAULT_MODEL, PLACEHOLDER_KEY, load_settings
from support_assistant.errors import ConfigurationError

# Uma chave falsa: os testes nunca usam a chave verdadeira.
FAKE_KEY = "sk-ant-teste-123"


def test_valid_key_uses_defaults():
    settings = load_settings({"ANTHROPIC_API_KEY": FAKE_KEY})

    assert settings.api_key == FAKE_KEY
    assert settings.model == DEFAULT_MODEL
    assert settings.effort == "medium"
    assert settings.max_tokens == 16000


def test_values_from_environment_override_defaults():
    settings = load_settings(
        {
            "ANTHROPIC_API_KEY": FAKE_KEY,
            "ASSISTANT_EFFORT": "LOW",
            "ASSISTANT_MAX_TOKENS": "500",
            "ASSISTANT_COMPANY_NAME": "Loja do Bairro",
        }
    )

    assert settings.effort == "low"
    assert settings.max_tokens == 500
    assert settings.company_name == "Loja do Bairro"


@pytest.mark.parametrize("key", ["", "   ", PLACEHOLDER_KEY])
def test_missing_or_placeholder_key_raises(key):
    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
        load_settings({"ANTHROPIC_API_KEY": key})


def test_key_absent_raises():
    with pytest.raises(ConfigurationError):
        load_settings({})


def test_key_is_hidden_from_repr():
    settings = load_settings({"ANTHROPIC_API_KEY": FAKE_KEY})

    assert FAKE_KEY not in repr(settings)


def test_app_password_is_optional_and_hidden():
    assert load_settings({"ANTHROPIC_API_KEY": FAKE_KEY}).app_password == ""

    settings = load_settings({"ANTHROPIC_API_KEY": FAKE_KEY, "APP_PASSWORD": "segredo123"})

    assert settings.app_password == "segredo123"
    assert "segredo123" not in repr(settings)


def test_invalid_effort_raises():
    with pytest.raises(ConfigurationError, match="ASSISTANT_EFFORT"):
        load_settings({"ANTHROPIC_API_KEY": FAKE_KEY, "ASSISTANT_EFFORT": "turbo"})


@pytest.mark.parametrize("value", ["abc", "0", "-5"])
def test_invalid_max_tokens_raises(value):
    with pytest.raises(ConfigurationError, match="ASSISTANT_MAX_TOKENS"):
        load_settings({"ANTHROPIC_API_KEY": FAKE_KEY, "ASSISTANT_MAX_TOKENS": value})
