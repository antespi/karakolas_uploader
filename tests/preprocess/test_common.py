from scripts.preprocess._common import (
    ALLOWED_CATEGORIAS,
    KarakolasRow,
    validate,
    write_csv,
)


def _good_row(**overrides) -> "KarakolasRow":
    base = dict(
        productor="La Vida a Granel",
        nombre="Alga Kombu Eco 25g",
        precio_base="2.50",
        categoria="Algas y plantas acuáticas",
        productor_id="",
        descripcion="",
        granel=True,
        pesar=True,
        destacado=False,
        temporada=False,
        precio_final="",
        precio_productor="",
    )
    base.update(overrides)
    return KarakolasRow(**base)


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


def test_validate_happy_path():
    assert validate(_good_row()) == []


def test_validate_empty_productor():
    assert validate(_good_row(productor="")) == ["productor empty"]


def test_validate_empty_nombre():
    assert validate(_good_row(nombre="   ")) == ["nombre empty"]


def test_validate_bad_precio_base():
    assert validate(_good_row(precio_base="abc")) == ["precio_base not decimal >= 0"]
    assert validate(_good_row(precio_base="-1.00")) == ["precio_base not decimal >= 0"]


def test_validate_categoria_not_in_allowlist():
    assert validate(_good_row(categoria="Fantasía")) == [
        "categoria 'Fantasía' not in allowed list"
    ]


def test_validate_bad_precio_final():
    assert validate(_good_row(precio_final="x")) == ["precio_final not decimal >= 0"]


def test_validate_bad_precio_productor():
    assert validate(_good_row(precio_productor="-3")) == [
        "precio_productor not decimal >= 0"
    ]


def test_validate_empty_optional_prices_ok():
    assert validate(_good_row(precio_final="", precio_productor="")) == []


def test_validate_collects_multiple_errors():
    errs = validate(_good_row(productor="", categoria="Fantasía"))
    assert set(errs) == {"productor empty", "categoria 'Fantasía' not in allowed list"}


def test_write_csv_emits_header_and_rows_in_order(tmp_path):
    out = tmp_path / "out.csv"
    rows = [
        _good_row(),
        _good_row(nombre="Otro", precio_base="3.00", granel=False, pesar=False),
    ]
    write_csv(rows, out)
    text = out.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == (
        "productor,nombre,precio_base,categoria,productor_id,descripcion,"
        "granel,pesar,destacado,temporada,precio_final,precio_productor"
    )
    assert lines[1] == (
        'La Vida a Granel,Alga Kombu Eco 25g,2.50,Algas y plantas acuáticas,,,'
        "True,True,False,False,,"
    )
    assert lines[2] == (
        "La Vida a Granel,Otro,3.00,Algas y plantas acuáticas,,,"
        "False,False,False,False,,"
    )


def test_write_csv_quotes_commas_in_strings(tmp_path):
    out = tmp_path / "out.csv"
    rows = [_good_row(descripcion="Hola, mundo")]
    write_csv(rows, out)
    line = out.read_text(encoding="utf-8").splitlines()[1]
    assert '"Hola, mundo"' in line
