import json
from unittest.mock import MagicMock

import pytest

from support_assistant.products import Product, ProductCatalog
from support_assistant.products_db import SQLiteProductCatalog
from support_assistant.tools import SEARCH_PRODUCTS, SEARCH_PRODUCTS_TOOL, ToolExecutor

LAPTOP = Product(sku="PC-001", name="Portátil Lenovo IdeaPad", price=799.0, stock=5)
PHONE = Product(sku="TL-001", name="Smartphone Apple iPhone 16", price=979.0, stock=0)


@pytest.fixture
def executor():
    return ToolExecutor(ProductCatalog([LAPTOP, PHONE]))


def test_definitions_contain_search_tool(executor):
    assert executor.definitions == [SEARCH_PRODUCTS_TOOL]
    assert SEARCH_PRODUCTS_TOOL["input_schema"]["required"] == ["pesquisa"]


def test_search_returns_products_as_json(executor):
    result = executor.run(SEARCH_PRODUCTS, {"pesquisa": "lenovo"})

    assert result.is_error is False
    assert json.loads(result.content) == {
        "produtos": [
            {
                "sku": "PC-001",
                "nome": "Portátil Lenovo IdeaPad",
                "preco_eur": 799.0,
                "stock": 5,
                "disponivel": True,
            }
        ]
    }


def test_out_of_stock_product_is_marked_unavailable(executor):
    result = executor.run(SEARCH_PRODUCTS, {"pesquisa": "iphone"})

    assert json.loads(result.content)["produtos"][0]["disponivel"] is False


def test_no_results_is_not_an_error(executor):
    # "Não temos bicicletas" é uma resposta normal, não um erro.
    result = executor.run(SEARCH_PRODUCTS, {"pesquisa": "bicicleta"})

    assert result.is_error is False
    assert json.loads(result.content) == {"produtos": []}


def test_unknown_tool_is_an_error(executor):
    result = executor.run("apagar_produtos", {})

    assert result.is_error is True
    assert "não existe" in result.content


@pytest.mark.parametrize("tool_input", [{}, {"pesquisa": ""}, {"pesquisa": 42}])
def test_invalid_input_is_an_error(executor, tool_input):
    assert executor.run(SEARCH_PRODUCTS, tool_input).is_error is True


def test_works_with_sqlite_catalog(tmp_path):
    # A "tomada": o mesmo ToolExecutor funciona com o catálogo SQLite.
    catalog = SQLiteProductCatalog(tmp_path / "teste.db", initial_products=[LAPTOP])

    result = ToolExecutor(catalog).run(SEARCH_PRODUCTS, {"pesquisa": "lenovo"})

    assert json.loads(result.content)["produtos"][0]["sku"] == "PC-001"


def test_catalog_failure_becomes_error_result():
    # Simulamos um "armazém" que não atende: search() lança uma exceção.
    broken_catalog = MagicMock()
    broken_catalog.search.side_effect = RuntimeError("base de dados em baixo")

    result = ToolExecutor(broken_catalog).run(SEARCH_PRODUCTS, {"pesquisa": "lenovo"})

    assert result.is_error is True
    assert "indisponível" in result.content
    # O detalhe técnico ("base de dados em baixo") não é enviado ao Claude.
    assert "base de dados" not in result.content
