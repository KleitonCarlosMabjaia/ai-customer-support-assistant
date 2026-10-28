"""Catálogo de produtos da loja (o "armazém").

Por agora é um catálogo de faz-de-conta, guardado numa lista em memória.
Na Etapa 4 vamos trocá-lo por uma base de dados SQLite com os mesmos métodos,
para que o resto do programa não precise de mudar.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Protocol

MAX_RESULTS = 5


@dataclass(frozen=True)
class Product:
    """Um produto da loja."""

    sku: str  # código único do produto (como o código de barras)
    name: str
    price: float  # em euros
    stock: int  # unidades disponíveis


DEFAULT_PRODUCTS = [
    Product(sku="PC-001", name="Portátil Lenovo IdeaPad 5 15\"", price=799.00, stock=5),
    Product(sku="PC-002", name="Portátil Apple MacBook Air 13\"", price=1199.00, stock=0),
    Product(sku="TL-001", name="Smartphone Samsung Galaxy A55", price=399.99, stock=12),
    Product(sku="TL-002", name="Smartphone Apple iPhone 16", price=979.00, stock=3),
    Product(sku="AU-001", name="Auscultadores Sony WH-1000XM5", price=349.00, stock=8),
    Product(sku="AC-001", name="Rato sem fios Logitech MX Master 3S", price=99.90, stock=20),
    Product(sku="AC-002", name="Teclado mecânico Logitech MX Keys", price=119.00, stock=0),
]


def normalize(text: str) -> str:
    """Põe o texto em minúsculas e tira os acentos ("Portátil" -> "portatil").

    Assim um cliente que escreve "portatil", sem acento, também encontra o produto.
    """
    # NFKD separa cada letra do seu acento ("á" passa a "a" + "´");
    # depois ficamos só com as letras e deitamos fora os acentos.
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


class Catalog(Protocol):
    """A "forma da ficha": o que qualquer catálogo de produtos tem de saber fazer.

    Não é preciso herdar desta classe. Qualquer classe com estes dois métodos
    (como ProductCatalog ou SQLiteProductCatalog) serve onde se pede um Catalog.
    """

    def search(self, query: str) -> list[Product]: ...

    def get_by_sku(self, sku: str) -> Product | None: ...


class ProductCatalog:
    """Permite procurar produtos por nome ou por código."""

    def __init__(self, products: list[Product] | None = None) -> None:
        # Nos testes passamos uma lista pequena e controlada; na aplicação usamos a de omissão.
        self._products = list(DEFAULT_PRODUCTS if products is None else products)

    def search(self, query: str) -> list[Product]:
        """Devolve os produtos cujo nome contém TODAS as palavras da pesquisa.

        Exemplo: "iphone apple" encontra "Smartphone Apple iPhone 16".
        Uma lista vazia significa "não encontrei nada", o que é uma resposta normal e não um erro.
        """
        words = normalize(query).split()
        if not words:
            return []

        results = [
            product
            for product in self._products
            if all(word in normalize(product.name) for word in words)
        ]
        return results[:MAX_RESULTS]

    def get_by_sku(self, sku: str) -> Product | None:
        """Devolve o produto com este código, ou None se não existir."""
        sku = sku.strip().upper()
        for product in self._products:
            if product.sku == sku:
                return product
        return None
