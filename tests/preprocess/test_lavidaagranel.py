import openpyxl
import pytest

from scripts.preprocess.lavidaagranel import (
    Config,
    MappedResult,
    RawRow,
    iter_rows,
    load_config,
    map_row,
    normalize,
)


def _build_fixture_xlsx(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pedidos Grupo Consumo"
    ws.append(["LA VIDA A GRANEL"])
    ws.append(["PEDIDOS GRUPO DE CONSUMO"])
    ws.append(["Fecha"])
    ws.append([])
    ws.append(["PRODUCTO", "PRECIO", "UNIDAD",
               "FAMILIA 1", "FAMILIA 2", "FAMILIA 3", "FAMILIA 4", "FAMILIA 5",
               "FAMILIA 6", "FAMILIA 7", "FAMILIA 8", "FAMILIA 9", "FAMILIA 10",
               "TOTAL"])
    ws.append(["📁 ALGAS"])
    ws.append(["ALGA KOMBU ECO 25G", 2.5, "Unidades"])
    ws.append(["ALGA NORI 25G", 2.95, "Unidades"])
    ws.append(["📁 LEGUMBRES"])
    ws.append(["GARBANZO ECO", 3.20, "kg"])
    ws.append(["📁 MYSTERY"])
    ws.append(["UNKNOWN ITEM", 1.00, "kg"])
    ws.append([None, None, None])
    ws.append(["BROKEN PRICE", "", "kg"])
    ws.append(["BROKEN UNIT", 1.00, ""])
    wb.save(path)


def test_normalize_basic_title_case():
    assert normalize("ALGA KOMBU ECO") == "Alga Kombu Eco"


def test_normalize_digit_letter_suffix_lowercased():
    assert normalize("ALGA KOMBU ECO 25G") == "Alga Kombu Eco 25g"
    assert normalize("VEER 33CL") == "Veer 33cl"
    assert normalize("AGUA 1L") == "Agua 1l"


def test_normalize_collapses_whitespace():
    assert normalize("  ALGA   KOMBU  ") == "Alga Kombu"


def test_normalize_preserves_accents():
    assert normalize("ALIÑO ESPAÑOL") == "Aliño Español"


def test_normalize_does_not_touch_pure_digit_token():
    assert normalize("PACK 12 UNIDADES") == "Pack 12 Unidades"


def test_normalize_does_not_touch_pure_letter_token():
    assert normalize("CAFE MOLIDO") == "Cafe Molido"


def test_load_config_minimal(fixtures_dir):
    cfg = load_config(fixtures_dir / "lavidaagranel_min.yaml")
    assert isinstance(cfg, Config)
    assert cfg.productor == "La Vida a Granel"
    assert cfg.productor_id == ""
    assert cfg.categorias["📁 ALGAS"] == "Algas y plantas acuáticas"
    assert cfg.unidades["kg"] == {"granel": True, "pesar": True, "descripcion": ""}
    assert cfg.unidades["unidades"]["granel"] is False
    assert cfg.defaults == {
        "destacado": False,
        "temporada": False,
        "precio_final": "",
        "precio_productor": "",
    }


def test_load_config_rejects_unknown_top_level_key(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "productor: X\n"
        "categorias: {}\n"
        "unidades: {}\n"
        "defaults: {destacado: false, temporada: false, precio_final: '', precio_productor: ''}\n"
        "surprise: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown top-level keys"):
        load_config(bad)


def test_load_config_skips_null_category_values(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "productor: X\n"
        "categorias:\n"
        "  '📁 ALGAS': { name: 'Algas y plantas acuáticas' }\n"
        "  '📁 MYSTERY': null\n"
        "unidades: { kg: { granel: true, pesar: true, descripcion: '' } }\n"
        "defaults: { destacado: false, temporada: false, precio_final: '', precio_productor: '' }\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert "📁 MYSTERY" not in cfg.categorias
    assert cfg.categorias["📁 ALGAS"] == "Algas y plantas acuáticas"


def test_iter_rows_yields_section_aware_rows(tmp_path):
    xlsx = tmp_path / "min.xlsx"
    _build_fixture_xlsx(xlsx)
    rows = list(iter_rows(xlsx))
    productos = [r for r in rows if r.kind == "product"]
    assert [r.producto for r in productos] == [
        "ALGA KOMBU ECO 25G",
        "ALGA NORI 25G",
        "GARBANZO ECO",
        "UNKNOWN ITEM",
        "BROKEN PRICE",
        "BROKEN UNIT",
    ]
    assert productos[0].section == "📁 ALGAS"
    assert productos[2].section == "📁 LEGUMBRES"
    assert productos[3].section == "📁 MYSTERY"
    assert productos[0].row_no == 7


def _cfg(fixtures_dir):
    return load_config(fixtures_dir / "lavidaagranel_min.yaml")


def test_map_row_happy_unidades(fixtures_dir):
    cfg = _cfg(fixtures_dir)
    raw = RawRow(kind="product", row_no=7, section="📁 ALGAS",
                 producto="ALGA KOMBU ECO 25G", precio=2.5, unidad="Unidades")
    result = map_row(raw, cfg)
    assert result.skip_reason is None
    row = result.row
    assert row.productor == "La Vida a Granel"
    assert row.nombre == "Alga Kombu Eco 25g"
    assert row.precio_base == "2.50"
    assert row.categoria == "Algas y plantas acuáticas"
    assert row.granel is False
    assert row.pesar is False
    assert row.descripcion == "Se pide por unidades, se paga por kg"
    assert row.productor_id == ""
    assert row.temporada is False


def test_map_row_happy_kg(fixtures_dir):
    cfg = _cfg(fixtures_dir)
    raw = RawRow(kind="product", row_no=10, section="📁 LEGUMBRES",
                 producto="GARBANZO ECO", precio=3.2, unidad="kg")
    result = map_row(raw, cfg)
    assert result.skip_reason is None
    assert result.row.precio_base == "3.20"
    assert result.row.granel is True
    assert result.row.pesar is True
    assert result.row.descripcion == ""


def test_map_row_unmapped_category_skipped(fixtures_dir):
    cfg = _cfg(fixtures_dir)
    raw = RawRow(kind="product", row_no=12, section="📁 MYSTERY",
                 producto="UNKNOWN ITEM", precio=1.0, unidad="kg")
    result = map_row(raw, cfg)
    assert result.skip_reason == "unmapped_category"
    assert result.row is None


def test_map_row_missing_price_skipped(fixtures_dir):
    cfg = _cfg(fixtures_dir)
    raw = RawRow(kind="product", row_no=14, section="📁 ALGAS",
                 producto="BROKEN PRICE", precio=None, unidad="kg")
    result = map_row(raw, cfg)
    assert result.skip_reason == "missing_price"


def test_map_row_missing_unit_skipped(fixtures_dir):
    cfg = _cfg(fixtures_dir)
    raw = RawRow(kind="product", row_no=15, section="📁 ALGAS",
                 producto="BROKEN UNIT", precio=1.0, unidad=None)
    result = map_row(raw, cfg)
    assert result.skip_reason == "missing_unit"


def test_map_row_no_current_section_skipped(fixtures_dir):
    cfg = _cfg(fixtures_dir)
    raw = RawRow(kind="product", row_no=6, section=None,
                 producto="ORPHAN", precio=1.0, unidad="kg")
    result = map_row(raw, cfg)
    assert result.skip_reason == "no_section"
