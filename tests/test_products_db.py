"""Testes do catálogo SQLite.

Cada teste cria a sua própria base de dados dentro de `tmp_path` (a folha de
rascunho), por isso nunca toca no ficheiro verdadeiro data/techloja.db.
"""

import pytest

from support_assistant.errors import ConfigurationError
from support_assistant.products import DEFAULT_PRODUCTS, MAX_RESULTS, Product
from support_assistant.products_db import SQLiteProductCatalog

LAPTOP = Product(sku="PC-001", name="Portátil Lenovo IdeaPad", price=799.0, stock=5)
PHONE = Product(sku="TL-001", name="Smartphone Apple iPhone 16", price=979.0, stock=0)
MOUSE = Product(sku="AC-001", name="Rato Logitech MX", price=99.9, stock=20)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "teste.db"


@pytest.fixture
def catalog(db_path):
    return SQLiteProductCatalog(db_path, initial_products=[LAPTOP, PHONE, MOUSE])


def test_search_finds_product_by_name(catalog):
    assert catalog.search("lenovo") == [LAPTOP]


def test_search_ignores_accents_and_case(catalog):
    assert catalog.search("PORTATIL") == [LAPTOP]


def test_search_needs_all_words(catalog):
    assert catalog.search("apple iphone") == [PHONE]
    assert catalog.search("apple lenovo") == []


@pytest.mark.parametrize("query", ["bicicleta", "", "   "])
def test_search_without_results_returns_empty_list(catalog, query):
    assert catalog.search(query) == []


def test_search_limits_number_of_results(db_path):
    many = [Product(sku=f"X-{i}", name=f"Cabo USB {i}", price=5.0, stock=1) for i in range(10)]

    assert len(SQLiteProductCatalog(db_path, initial_products=many).search("cabo")) == MAX_RESULTS


def test_get_by_sku(catalog):
    assert catalog.get_by_sku(" ac-001 ") == MOUSE
    assert catalog.get_by_sku("NAO-EXISTE") is None


def test_data_survives_reopening(catalog, db_path):
    # Abrimos a MESMA gaveta outra vez, sem produtos iniciais:
    # os produtos continuam lá, porque estão guardados no ficheiro.
    reopened = SQLiteProductCatalog(db_path, initial_products=[])

    assert reopened.search("lenovo") == [LAPTOP]


def test_initial_products_are_only_added_once(catalog, db_path):
    # Se a tabela já tem produtos, os iniciais não são inseridos outra vez.
    SQLiteProductCatalog(db_path, initial_products=[LAPTOP, PHONE, MOUSE])

    assert catalog.search("lenovo") == [LAPTOP]


@pytest.mark.parametrize("attack", ["x' OR '1'='1", "'; DROP TABLE produtos; --"])
def test_sql_injection_is_treated_as_plain_text(catalog, attack):
    # O texto malicioso fica "dentro da caixa": é só um texto que não existe.
    assert catalog.search(attack) == []
    assert catalog.get_by_sku(attack) is None
    # E a tabela continua inteira.
    assert catalog.search("lenovo") == [LAPTOP]


def test_default_products_are_used_when_none_given(db_path):
    catalog = SQLiteProductCatalog(db_path)

    assert catalog.get_by_sku(DEFAULT_PRODUCTS[0].sku) == DEFAULT_PRODUCTS[0]


def test_broken_database_file_raises_configuration_error(db_path):
    db_path.write_text("isto não é uma base de dados", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="base de dados"):
        SQLiteProductCatalog(db_path)
