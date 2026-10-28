"""Configuração da aplicação.

As definições são lidas de variáveis de ambiente. Para facilitar o
desenvolvimento, também são lidas de um ficheiro `.env` na raiz do projeto
(que NUNCA vai para o Git). A chave da API nunca aparece no código.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from dotenv import load_dotenv

from support_assistant.errors import ConfigurationError

DEFAULT_MODEL = "claude-opus-5-5"
VALID_EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Texto de exemplo que está no .env.example; se ainda lá estiver, a chave não foi configurada.
PLACEHOLDER_KEY = "coloca-aqui-a-tua-chave"


@dataclass(frozen=True)
class Settings:
    """Todas as definições num único objeto imutável (frozen=True).

    `repr=False` na chave impede que ela apareça ao fazer print(settings)
    ou em mensagens de erro e logs.
    """

    api_key: str = field(repr=False)
    model: str = DEFAULT_MODEL
    effort: str = "medium"
    max_tokens: int = 16000
    timeout_seconds: float = 120.0
    company_name: str = "TechLoja"
    # Palavra-passe da interface web ("" = site aberto a todos). Também é secreta.
    app_password: str = field(default="", repr=False)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Lê e valida as definições.

    `env` permite passar um dicionário nos testes; em uso normal fica a None
    e são lidas as variáveis de ambiente reais (depois de carregar o .env).
    """
    if env is None:
        load_dotenv()
        env = os.environ

    api_key = env.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key or api_key == PLACEHOLDER_KEY:
        raise ConfigurationError(
            "A variável ANTHROPIC_API_KEY não está definida. "
            "Copia o ficheiro .env.example para .env e coloca lá a tua chave."
        )

    effort = env.get("ASSISTANT_EFFORT", "medium").strip().lower()
    if effort not in VALID_EFFORTS:
        raise ConfigurationError(
            f"ASSISTANT_EFFORT inválido: '{effort}'. Valores aceites: {', '.join(VALID_EFFORTS)}."
        )

    return Settings(
        api_key=api_key,
        model=env.get("ASSISTANT_MODEL", DEFAULT_MODEL).strip(),
        effort=effort,
        max_tokens=int(_parse_positive_number(env, "ASSISTANT_MAX_TOKENS", 16000, int)),
        timeout_seconds=_parse_positive_number(env, "ASSISTANT_TIMEOUT_SECONDS", 120.0, float),
        company_name=env.get("ASSISTANT_COMPANY_NAME", "TechLoja").strip(),
        app_password=env.get("APP_PASSWORD", "").strip(),
    )


def _parse_positive_number(env: Mapping[str, str], name: str, default: float, kind: type) -> float:
    """Converte uma variável para número (int ou float) e garante que é > 0."""
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = kind(raw)
    except ValueError:
        raise ConfigurationError(f"{name} tem de ser um número, mas recebeu '{raw}'.") from None
    if value <= 0:
        raise ConfigurationError(f"{name} tem de ser maior que zero.")
    return value
