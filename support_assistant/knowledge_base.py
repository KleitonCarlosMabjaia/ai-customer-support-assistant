"""Base de conhecimento: as perguntas frequentes (FAQ) da loja.

As FAQ estão num ficheiro JSON separado do código, para que possam ser
alteradas sem mexer no Python. Este módulo lê esse ficheiro, verifica se
está bem escrito e transforma-o no texto que vai para o prompt de sistema.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from support_assistant.errors import ConfigurationError

# Caminho construído a partir da localização DESTE ficheiro, e não da pasta
# onde o programa é executado. Assim funciona seja qual for a pasta atual.
DEFAULT_FAQ_PATH = Path(__file__).resolve().parent.parent / "data" / "faq.json"
REQUIRED_FIELDS = ("pergunta", "resposta")


@dataclass(frozen=True)
class FAQEntry:
    """Uma pergunta frequente e a respetiva resposta oficial."""

    question: str
    answer: str


def load_faq(path: Path = DEFAULT_FAQ_PATH) -> list[FAQEntry]:
    """Lê e valida o ficheiro de FAQ.

    Qualquer problema no ficheiro lança ConfigurationError logo ao arrancar
    ("fail fast"), em vez de o programa funcionar com dados estragados.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigurationError(f"Ficheiro de FAQ não encontrado: {path}") from None

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ConfigurationError(
            f"O ficheiro {path.name} não é JSON válido (linha {e.lineno}, coluna {e.colno})."
        ) from None

    if not isinstance(data, list) or not data:
        raise ConfigurationError(f"O ficheiro {path.name} tem de conter uma lista de FAQ não vazia.")

    # enumerate(..., start=1) numera as entradas a partir de 1, como uma pessoa contaria.
    return [_parse_entry(item, number, path.name) for number, item in enumerate(data, start=1)]


def _parse_entry(item: Any, number: int, file_name: str) -> FAQEntry:
    """Converte um elemento do JSON num FAQEntry, verificando os campos."""
    if not isinstance(item, dict):
        raise ConfigurationError(f"A entrada {number} de {file_name} não é um objeto {{...}}.")

    for field_name in REQUIRED_FIELDS:
        value = item.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(
                f'A entrada {number} de {file_name} não tem "{field_name}" (ou está vazia).'
            )

    return FAQEntry(question=item["pergunta"].strip(), answer=item["resposta"].strip())


def format_faq(entries: list[FAQEntry]) -> str:
    """Transforma a lista de FAQ num texto simples, uma pergunta/resposta por bloco."""
    return "\n\n".join(f"P: {entry.question}\nR: {entry.answer}" for entry in entries)
