"""Ferramentas (tools) que o Claude pode pedir para usar.

O Claude nunca executa código: quando precisa de uma ferramenta, devolve um
pedido (um bloco "tool_use") com o nome da ferramenta e os dados de entrada.
É o NOSSO programa que executa o pedido, aqui, e lhe devolve o resultado.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from support_assistant.products import Catalog, Product

logger = logging.getLogger(__name__)

SEARCH_PRODUCTS = "procurar_produtos"

# A "etiqueta do telefone": é tudo o que o Claude sabe sobre a ferramenta.
# A descrição diz-lhe QUANDO a usar; o input_schema diz-lhe QUE dados enviar.
SEARCH_PRODUCTS_TOOL = {
    "name": SEARCH_PRODUCTS,
    "description": (
        "Procura produtos no catálogo da loja pelo nome, marca ou tipo, e devolve o "
        "código (sku), o preço em euros e as unidades em stock. Usa esta ferramenta "
        "sempre que o cliente perguntar por um produto, um preço ou disponibilidade, "
        "e nunca inventes esses dados. Se a lista de produtos vier vazia, a loja não "
        "tem nenhum produto com esse nome."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pesquisa": {
                "type": "string",
                "description": "Palavras a procurar, por exemplo 'portátil lenovo' ou 'iphone'.",
            }
        },
        "required": ["pesquisa"],
        "additionalProperties": False,
    },
    # strict=True: a API garante que o Claude envia os dados exatamente neste formato.
    "strict": True,
}


@dataclass(frozen=True)
class ToolResult:
    """O resultado de uma ferramenta, já em texto, pronto a enviar ao Claude."""

    content: str
    is_error: bool = False


class ToolExecutor:
    """Recebe os pedidos de ferramentas do Claude e executa-os."""

    def __init__(self, catalog: Catalog) -> None:
        # Qualquer catálogo com a "ficha" certa serve: em memória ou SQLite.
        self._catalog = catalog

    @property
    def definitions(self) -> list[dict[str, Any]]:
        """As descrições de todas as ferramentas, para enviar no pedido à API."""
        return [SEARCH_PRODUCTS_TOOL]

    def run(self, name: str, tool_input: dict[str, Any]) -> ToolResult:
        """Executa a ferramenta `name` com os dados `tool_input`.

        Nunca lança exceções: qualquer problema volta como ToolResult com
        is_error=True, para o Claude poder explicar ao cliente o que se passou
        em vez de a conversa terminar com um erro.
        """
        logger.info("Ferramenta pedida: %s %s", name, tool_input)

        if name != SEARCH_PRODUCTS:
            return ToolResult(f"A ferramenta '{name}' não existe.", is_error=True)

        query = tool_input.get("pesquisa")
        if not isinstance(query, str) or not query.strip():
            return ToolResult("Falta o campo 'pesquisa' com o texto a procurar.", is_error=True)

        try:
            products = self._catalog.search(query)
        except Exception:
            # Rede de segurança: se o "armazém" falhar (por exemplo, a base de dados
            # da Etapa 4 estiver indisponível), registamos o detalhe técnico no log
            # e dizemos ao Claude apenas que o sistema não respondeu.
            logger.exception("Falha ao procurar produtos.")
            return ToolResult(
                "O sistema de produtos está indisponível de momento.", is_error=True
            )

        return ToolResult(_products_to_json(products))


def _products_to_json(products: list[Product]) -> str:
    """Converte os produtos num texto JSON que o Claude consegue ler facilmente."""
    data = {
        "produtos": [
            {
                "sku": product.sku,
                "nome": product.name,
                "preco_eur": product.price,
                "stock": product.stock,
                "disponivel": product.stock > 0,
            }
            for product in products
        ]
    }
    # ensure_ascii=False mantém os acentos legíveis ("Portátil" em vez de "Portátil").
    return json.dumps(data, ensure_ascii=False)
