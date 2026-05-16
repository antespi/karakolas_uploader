from scripts.preprocess._common import (
    ALLOWED_CATEGORIAS,
    KarakolasRow,
)


def test_allowed_categorias_contains_known_labels():
    assert "Verduras" in ALLOWED_CATEGORIAS
    assert "Bebidas" in ALLOWED_CATEGORIAS
    assert "Cereales y Legumbres" in ALLOWED_CATEGORIAS
    assert "_Ninguna de las anteriores" in ALLOWED_CATEGORIAS


def test_karakolas_row_has_twelve_columns_in_order():
    row = KarakolasRow(
        productor="Test",
        nombre="Item",
        precio_base="1.00",
        categoria="Verduras",
        productor_id="",
        descripcion="",
        granel=False,
        pesar=False,
        destacado=False,
        temporada=True,
        precio_final="",
        precio_productor="",
    )
    assert row.column_order() == (
        "productor",
        "nombre",
        "precio_base",
        "categoria",
        "productor_id",
        "descripcion",
        "granel",
        "pesar",
        "destacado",
        "temporada",
        "precio_final",
        "precio_productor",
    )
