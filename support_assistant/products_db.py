"""Catálogo de produtos guardado numa base de dados SQLite (a "gaveta").

Tem os mesmos métodos que o ProductCatalog em memória (search e get_by_sku),
por isso pode substituí-lo sem mudar o resto do programa. A diferença é que os
dados ficam num ficheiro no disco e não se perdem quando o programa fecha.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from support_assistant.errors import ConfigurationError
from support_assistant.products import DEFAULT_PRODUCTS, MAX_RESULTS, Product, normalize

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "techloja.db"

# A "folha de Excel" dos produtos. As regras (NOT NULL, CHECK, PRIMARY KEY)
# são verificadas pela própria base de dados, que recusa dados que as violem.
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS produtos (
    sku           TEXT PRIMARY KEY,
    nome          TEXT NOT NULL,
    nome_pesquisa TEXT NOT NULL,
    preco         REAL NOT NULL CHECK (preco >= 0),
    stock         INTEGER NOT NULL CHECK (stock >= 0)
)
"""


class SQLiteProductCatalog:
    """Permite procurar produtos guardados numa base de dados SQLite."""

    def __init__(
        self,
        path: Path | str = DEFAULT_DB_PATH,
        initial_products: list[Product] | None = None,
    ) -> None:
        """Abre (ou cria) a base de dados e garante que a tabela existe.

        Se a tabela estiver vazia, enche-a com `initial_products` (por omissão,
        os produtos de exemplo). Se já tiver produtos, não lhes toca.
        """
        self._path = path
        products = DEFAULT_PRODUCTS if initial_products is None else initial_products
        try:
            with self._connect() as conn:
                conn.execute(CREATE_TABLE)
                count = conn.execute("SELECT COUNT(*) FROM produtos").fetchone()[0]
                if count == 0:
                    self._insert(conn, products)
        except sqlite3.Error as e:
            # Fail fast: se a base de dados não abre, o programa nem deve arrancar.
            raise ConfigurationError(f"Não foi possível abrir a base de dados {path}: {e}") from e

    def search(self, query: str) -> list[Product]:
        """Devolve os produtos cujo nome contém TODAS as palavras da pesquisa."""
        words = normalize(query).split()
        if not words:
            return []

        # Uma condição "nome_pesquisa LIKE ?" por palavra, ligadas por AND.
        # Só o NOSSO texto fixo entra na frase SQL; as palavras do cliente
        # vão sempre à parte, nos `?` (proteção contra SQL injection).
        conditions = " AND ".join("nome_pesquisa LIKE ?" for _ in words)
        sql = (
            "SELECT sku, nome, preco, stock FROM produtos "
            f"WHERE {conditions} ORDER BY rowid LIMIT ?"
        )
        # Em LIKE, o % quer dizer "qualquer texto": "%lenovo%" = contém "lenovo".
        params = [f"%{word}%" for word in words] + [MAX_RESULTS]

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_product(row) for row in rows]

    def get_by_sku(self, sku: str) -> Product | None:
        """Devolve o produto com este código, ou None se não existir."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT sku, nome, preco, stock FROM produtos WHERE sku = ?",
                (sku.strip().upper(),),
            ).fetchone()
        return None if row is None else _row_to_product(row)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Abre a gaveta, deixa-nos trabalhar e fecha-a SEMPRE no fim.

        `with conn:` guarda as alterações (commit) se tudo correr bem, ou
        desfaz tudo (rollback) se houver um erro a meio.
        """
        conn = sqlite3.connect(self._path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _insert(conn: sqlite3.Connection, products: list[Product]) -> None:
        conn.executemany(
            "INSERT INTO produtos (sku, nome, nome_pesquisa, preco, stock) VALUES (?, ?, ?, ?, ?)",
            [(p.sku, p.name, normalize(p.name), p.price, p.stock) for p in products],
        )


def _row_to_product(row: tuple) -> Product:
    """Converte uma linha da tabela (um tuplo) num Product."""
    sku, name, price, stock = row
    return Product(sku=sku, name=name, price=price, stock=stock)
