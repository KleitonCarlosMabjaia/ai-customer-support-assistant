import pytest

from support_assistant.products import (
    MAX_RESULTS,
    Product,
    ProductCatalog,
    normalize,
)

# Um catálogo pequeno e previsível, só para os testes.
LAPTOP = Product(sku="PC-001", name="Portátil Lenovo IdeaPad", price=799.0, stock=5)
PHONE = Product(sku="TL-001", name="Smartphone Apple iPhone 16", price=979.0, stock=0)
MOUSE = Product(sku="AC-001", name="Rato Logitech MX", price=99.9, stock=20)


@pytest.fixture
def catalog():
    return ProductCatalog([LAPTOP, PHONE, MOUSE])


@pytest.mark.parametrize(
    ("text", "expected"),
    [("Portátil", "portatil"), ("TECLADO MECÂNICO", "teclado mecanico"), ("rato", "rato")],
)
def test_normalize_removes_accents_and_case(text, expected):
    assert normalize(text) == expected


def test_search_finds_product_by_name(catalog):
    assert catalog.search("lenovo") == [LAPTOP]


def test_search_ignores_accents_and_case(catalog):
    assert catalog.search("PORTATIL") == [LAPTOP]


def test_search_needs_all_words(catalog):
    assert catalog.search("apple iphone") == [PHONE]
    assert catalog.search("apple lenovo") == []


@pytest.mark.parametrize("query", ["bicicleta", "", "   "])
def test_search_without_results_returns_empty_list(catalog, query):
    # "Não encontrei" é uma resposta normal: lista vazia, sem exceção.
    assert catalog.search(query) == []


def test_search_limits_number_of_results():
    many = [Product(sku=f"X-{i}", name=f"Cabo USB {i}", price=5.0, stock=1) for i in range(10)]

    assert len(ProductCatalog(many).search("cabo")) == MAX_RESULTS


def test_get_by_sku(catalog):
    assert catalog.get_by_sku(" ac-001 ") == MOUSE
    assert catalog.get_by_sku("NAO-EXISTE") is None


def test_list_all_has_no_result_limit():
    many = [Product(sku=f"X-{i}", name=f"Cabo USB {i}", price=5.0, stock=1) for i in range(10)]

    assert ProductCatalog(many).list_all() == many


def test_default_catalog_has_products():
    assert len(ProductCatalog().search("smartphone")) > 0
