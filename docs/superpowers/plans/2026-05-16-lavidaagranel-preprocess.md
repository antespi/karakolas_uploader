# La Vida a Granel Preprocess Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first per-producer preprocessor that converts the La Vida a Granel xlsx order form into a normalized `karakolas.csv` consumable by `scripts/upload.py`.

**Architecture:** A `scripts/preprocess/` package with shared serialization/validation in `_common.py` and a producer-specific driver (`lavidaagranel.py`) plus its yaml mapping (`lavidaagranel.yaml`). The driver walks the xlsx, tracks the current `📁` section header to derive category, applies a yaml-driven category and UNIDAD mapping, and writes a dated CSV plus a per-run log. Per-producer future scripts follow the same shape.

**Tech Stack:** Python 3.11+, `openpyxl`, `PyYAML`, `pytest`.

### Spec inconsistencies resolved here

The spec at `docs/superpowers/specs/2026-05-16-lavidaagranel-preprocess-design.md` has three minor inconsistencies that this plan locks in:

1. **yaml key spelling under `unidades`** — yaml block in spec uses `description`, transformation table uses `.descripcion`. **Locked in this plan: `descripcion`** (Spanish, matches the karakolas CSV column).
2. **`productor_id` source** — transformation table says `yaml.productor_id`, Output section says "always empty". **Locked: optional top-level yaml key `productor_id`. Empty string in output when absent.** For La Vida a Granel the yaml omits the key (instance-specific, leave blank).
3. **`defaults.descripcion`** — no longer needed once description comes from `unidades`. **Locked: removed from `defaults`.** The yaml block shipped in Task 7 reflects this.

If these choices need to change, do it now — they ripple through Tasks 2, 6, 7, 8.

---

## File Structure

Create:
- `scripts/preprocess/__init__.py` — empty marker.
- `scripts/preprocess/_common.py` — `KarakolasRow` dataclass, `ALLOWED_CATEGORIAS`, `validate`, `write_csv`. Reusable across producers.
- `scripts/preprocess/lavidaagranel.py` — yaml loader, normalize, xlsx walker, row mapper, CLI/main.
- `scripts/preprocess/lavidaagranel.yaml` — producer config.
- `tests/__init__.py` — empty marker.
- `tests/preprocess/__init__.py` — empty marker.
- `tests/preprocess/test_common.py` — validate + write_csv tests.
- `tests/preprocess/test_lavidaagranel.py` — normalize + yaml loader + xlsx walker + integration tests.
- `tests/preprocess/fixtures/lavidaagranel_min.xlsx` — small fixture xlsx.
- `tests/preprocess/fixtures/lavidaagranel_min.yaml` — small fixture yaml.
- `tests/preprocess/conftest.py` — pytest fixture path helpers.

Modify:
- `requirements.txt` — add `openpyxl`, `PyYAML`, `pytest`.

Each file has one clear responsibility. `_common.py` knows nothing about xlsx or yaml. `lavidaagranel.py` knows everything about the La Vida a Granel format but emits `KarakolasRow` instances and delegates serialization to `_common.py`.

---

## Task 1: Bootstrap project layout and deps

**Files:**
- Modify: `requirements.txt`
- Create: `scripts/preprocess/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/preprocess/__init__.py`
- Create: `tests/preprocess/conftest.py`

- [ ] **Step 1: Add dependencies to `requirements.txt`**

Append these three lines (alphabetical-ish, no version pin yet — let pip resolve):

```
openpyxl
PyYAML
pytest
```

- [ ] **Step 2: Install them**

Run:
```bash
source .venv/bin/activate
pip install openpyxl PyYAML pytest
```
Expected: three successful installs, no errors.

- [ ] **Step 3: Create package markers**

Write `scripts/preprocess/__init__.py`:
```python
```
(empty file)

Write `tests/__init__.py`:
```python
```
(empty file)

Write `tests/preprocess/__init__.py`:
```python
```
(empty file)

- [ ] **Step 4: Create pytest fixture helpers**

Write `tests/preprocess/conftest.py`:
```python
from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
```

- [ ] **Step 5: Verify pytest discovers an empty suite**

Run: `pytest -q`
Expected: `no tests ran` (exit code 5) — that's fine; we just want pytest installed and importing cleanly.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt scripts/preprocess/__init__.py tests/__init__.py tests/preprocess/__init__.py tests/preprocess/conftest.py
git commit -m "scaffold: preprocess package + pytest layout"
```

---

## Task 2: `_common.py` — `KarakolasRow` dataclass and `ALLOWED_CATEGORIAS`

**Files:**
- Create: `scripts/preprocess/_common.py`
- Create: `tests/preprocess/test_common.py`

- [ ] **Step 1: Write the failing test**

Write `tests/preprocess/test_common.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/preprocess/test_common.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.preprocess._common'`.

- [ ] **Step 3: Write minimal implementation**

Write `scripts/preprocess/_common.py`:
```python
from dataclasses import dataclass, fields

ALLOWED_CATEGORIAS = frozenset({
    "Aceites y grasas",
    "Algas y plantas acuáticas",
    "Alimentos",
    "Aliños y conservantes",
    "Bebidas",
    "Carnes, aves y embutidos",
    "Cereales y Legumbres",
    "Chocolate y dulces",
    "Comidas preparadas",
    "Frutas",
    "Frutos secos",
    "Lácteos y huevos",
    "Oficina",
    "Panadería y bollería",
    "Papel",
    "Pescado y Marisco",
    "Productos de limpieza e higiene",
    "Ropa",
    "Verduras",
    "_Ninguna de las anteriores",
})


@dataclass(frozen=True)
class KarakolasRow:
    productor: str
    nombre: str
    precio_base: str
    categoria: str
    productor_id: str
    descripcion: str
    granel: bool
    pesar: bool
    destacado: bool
    temporada: bool
    precio_final: str
    precio_productor: str

    @staticmethod
    def column_order() -> tuple[str, ...]:
        return tuple(f.name for f in fields(KarakolasRow))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/preprocess/test_common.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/preprocess/_common.py tests/preprocess/test_common.py
git commit -m "feat(preprocess): KarakolasRow dataclass + allowed categorias"
```

---

## Task 3: `_common.py` — `validate(row) -> list[str]`

**Files:**
- Modify: `scripts/preprocess/_common.py`
- Modify: `tests/preprocess/test_common.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/preprocess/test_common.py`:
```python
from scripts.preprocess._common import validate


def _good_row(**overrides) -> KarakolasRow:
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


def test_validate_happy_path():
    assert validate(_good_row()) == []


def test_validate_empty_productor():
    errs = validate(_good_row(productor=""))
    assert errs == ["productor empty"]


def test_validate_empty_nombre():
    errs = validate(_good_row(nombre="   "))
    assert errs == ["nombre empty"]


def test_validate_bad_precio_base():
    assert validate(_good_row(precio_base="abc")) == ["precio_base not decimal >= 0"]
    assert validate(_good_row(precio_base="-1.00")) == ["precio_base not decimal >= 0"]


def test_validate_categoria_not_in_allowlist():
    errs = validate(_good_row(categoria="Fantasía"))
    assert errs == ["categoria 'Fantasía' not in allowed list"]


def test_validate_bad_precio_final():
    assert validate(_good_row(precio_final="x")) == ["precio_final not decimal >= 0"]


def test_validate_bad_precio_productor():
    assert validate(_good_row(precio_productor="-3")) == ["precio_productor not decimal >= 0"]


def test_validate_empty_optional_prices_ok():
    assert validate(_good_row(precio_final="", precio_productor="")) == []


def test_validate_collects_multiple_errors():
    errs = validate(_good_row(productor="", categoria="Fantasía"))
    assert set(errs) == {"productor empty", "categoria 'Fantasía' not in allowed list"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/preprocess/test_common.py -v`
Expected: ImportError on `validate` then collection errors.

- [ ] **Step 3: Implement `validate`**

Append to `scripts/preprocess/_common.py`:
```python
from decimal import Decimal, InvalidOperation


def _is_nonneg_decimal(value: str) -> bool:
    try:
        return Decimal(value) >= 0
    except (InvalidOperation, ValueError):
        return False


def validate(row: KarakolasRow) -> list[str]:
    errors: list[str] = []
    if not row.productor.strip():
        errors.append("productor empty")
    if not row.nombre.strip():
        errors.append("nombre empty")
    if not _is_nonneg_decimal(row.precio_base):
        errors.append("precio_base not decimal >= 0")
    if row.categoria not in ALLOWED_CATEGORIAS:
        errors.append(f"categoria '{row.categoria}' not in allowed list")
    if row.precio_final != "" and not _is_nonneg_decimal(row.precio_final):
        errors.append("precio_final not decimal >= 0")
    if row.precio_productor != "" and not _is_nonneg_decimal(row.precio_productor):
        errors.append("precio_productor not decimal >= 0")
    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/preprocess/test_common.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/preprocess/_common.py tests/preprocess/test_common.py
git commit -m "feat(preprocess): row validation rules from karakolas-template.md"
```

---

## Task 4: `_common.py` — `write_csv`

**Files:**
- Modify: `scripts/preprocess/_common.py`
- Modify: `tests/preprocess/test_common.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/preprocess/test_common.py`:
```python
from scripts.preprocess._common import write_csv


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/preprocess/test_common.py -v -k write_csv`
Expected: ImportError on `write_csv`.

- [ ] **Step 3: Implement `write_csv`**

Add to top of `scripts/preprocess/_common.py`:
```python
import csv
from pathlib import Path
from typing import Iterable
```

Append:
```python
def write_csv(rows: Iterable[KarakolasRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = KarakolasRow.column_order()
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow(_serialize(row, columns))


def _serialize(row: KarakolasRow, columns: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for col in columns:
        v = getattr(row, col)
        if isinstance(v, bool):
            out.append("True" if v else "False")
        else:
            out.append(str(v))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/preprocess/test_common.py -v`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/preprocess/_common.py tests/preprocess/test_common.py
git commit -m "feat(preprocess): CSV writer with mandatory-first column order"
```

---

## Task 5: `lavidaagranel.py` — `normalize(name)`

**Files:**
- Create: `scripts/preprocess/lavidaagranel.py`
- Create: `tests/preprocess/test_lavidaagranel.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/preprocess/test_lavidaagranel.py`:
```python
from scripts.preprocess.lavidaagranel import normalize


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/preprocess/test_lavidaagranel.py -v`
Expected: ImportError on `normalize`.

- [ ] **Step 3: Implement `normalize`**

Write `scripts/preprocess/lavidaagranel.py`:
```python
import re

_DIGIT_LETTER_TOKEN = re.compile(r"^(\d+)([A-Za-z]+)$")


def normalize(name: str) -> str:
    collapsed = " ".join(name.split())
    titled = collapsed.title()
    out_tokens: list[str] = []
    for token in titled.split(" "):
        m = _DIGIT_LETTER_TOKEN.match(token)
        if m:
            out_tokens.append(f"{m.group(1)}{m.group(2).lower()}")
        else:
            out_tokens.append(token)
    return " ".join(out_tokens)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/preprocess/test_lavidaagranel.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/preprocess/lavidaagranel.py tests/preprocess/test_lavidaagranel.py
git commit -m "feat(lavidaagranel): nombre normalize rule"
```

---

## Task 6: `lavidaagranel.py` — yaml `Config` loader

**Files:**
- Modify: `scripts/preprocess/lavidaagranel.py`
- Modify: `tests/preprocess/test_lavidaagranel.py`
- Create: `tests/preprocess/fixtures/lavidaagranel_min.yaml`

- [ ] **Step 1: Create minimal fixture yaml**

Write `tests/preprocess/fixtures/lavidaagranel_min.yaml`:
```yaml
productor: La Vida a Granel

categorias:
  "📁 ALGAS": { name: "Algas y plantas acuáticas" }
  "📁 LEGUMBRES": { name: "Cereales y Legumbres" }

unidades:
  kg:       { granel: true,  pesar: true,  descripcion: "" }
  Unidades: { granel: false, pesar: false, descripcion: "Se pide por unidades, se paga por kg" }

defaults:
  destacado: false
  temporada: false
  precio_final: ""
  precio_productor: ""
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/preprocess/test_lavidaagranel.py`:
```python
import pytest

from scripts.preprocess.lavidaagranel import Config, load_config


def test_load_config_minimal(fixtures_dir):
    cfg = load_config(fixtures_dir / "lavidaagranel_min.yaml")
    assert isinstance(cfg, Config)
    assert cfg.productor == "La Vida a Granel"
    assert cfg.productor_id == ""
    assert cfg.categorias["📁 ALGAS"] == "Algas y plantas acuáticas"
    assert cfg.unidades["kg"] == {"granel": True, "pesar": True, "descripcion": ""}
    assert cfg.unidades["unidades"]["granel"] is False  # case-insensitive key
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


def test_load_config_skips_null_category_values(fixtures_dir, tmp_path):
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/preprocess/test_lavidaagranel.py -v -k config`
Expected: ImportError on `Config`/`load_config`.

- [ ] **Step 4: Implement loader**

Add to `scripts/preprocess/lavidaagranel.py` (top imports):
```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
```

Append:
```python
_REQUIRED_TOP_KEYS = {"productor", "categorias", "unidades", "defaults"}
_OPTIONAL_TOP_KEYS = {"productor_id"}
_REQUIRED_DEFAULTS_KEYS = {"destacado", "temporada", "precio_final", "precio_productor"}


@dataclass(frozen=True)
class Config:
    productor: str
    productor_id: str
    categorias: dict[str, str]
    unidades: dict[str, dict[str, Any]]
    defaults: dict[str, Any]


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"config root must be a mapping, got {type(raw).__name__}")

    keys = set(raw.keys())
    missing = _REQUIRED_TOP_KEYS - keys
    if missing:
        raise ValueError(f"missing required top-level keys: {sorted(missing)}")
    unknown = keys - _REQUIRED_TOP_KEYS - _OPTIONAL_TOP_KEYS
    if unknown:
        raise ValueError(f"unknown top-level keys: {sorted(unknown)}")

    defaults = raw["defaults"] or {}
    missing_defaults = _REQUIRED_DEFAULTS_KEYS - set(defaults.keys())
    if missing_defaults:
        raise ValueError(f"missing required defaults keys: {sorted(missing_defaults)}")

    categorias: dict[str, str] = {}
    for k, v in (raw["categorias"] or {}).items():
        if v is None:
            continue
        if not isinstance(v, dict) or "name" not in v:
            raise ValueError(f"categoria {k!r} must be a mapping with key 'name'")
        categorias[k] = v["name"]

    unidades: dict[str, dict[str, Any]] = {}
    for k, v in (raw["unidades"] or {}).items():
        if not isinstance(v, dict):
            raise ValueError(f"unidad {k!r} must be a mapping")
        required = {"granel", "pesar", "descripcion"}
        if not required.issubset(v.keys()):
            raise ValueError(f"unidad {k!r} missing keys: {sorted(required - set(v.keys()))}")
        unidades[k.lower()] = {"granel": bool(v["granel"]),
                                "pesar": bool(v["pesar"]),
                                "descripcion": str(v["descripcion"])}

    return Config(
        productor=str(raw["productor"]),
        productor_id=str(raw.get("productor_id", "")),
        categorias=categorias,
        unidades=unidades,
        defaults=defaults,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/preprocess/test_lavidaagranel.py -v`
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/preprocess/lavidaagranel.py tests/preprocess/test_lavidaagranel.py tests/preprocess/fixtures/lavidaagranel_min.yaml
git commit -m "feat(lavidaagranel): yaml Config loader with strict schema"
```

---

## Task 7: Ship the producer yaml

**Files:**
- Create: `scripts/preprocess/lavidaagranel.yaml`

- [ ] **Step 1: Write the producer config**

Write `scripts/preprocess/lavidaagranel.yaml`:
```yaml
productor: La Vida a Granel

# Vendor section-header label → karakolas categoria label.
# Missing key, or null value → rows under it are skipped + logged.
categorias:
  "📁 ALGAS": { name: "Algas y plantas acuáticas" }
  "📁 ALIMENTOS / BEBIDAS": { name: "Bebidas" }
  "📁 ALIMENTOS / VARIOS": { name: "Alimentos" }
  "📁 ARROCES": { name: "Cereales y Legumbres" }
  "📁 AZUCAR, CACAO Y CHOCOLATE": { name: "Chocolate y dulces" }
  "📁 CAFE": { name: "Bebidas" }
  "📁 CEREALES Y COPOS": { name: "Cereales y Legumbres" }
  "📁 ESPECIAS": { name: "Aliños y conservantes" }
  "📁 FRUTAS DESHIDRATADAS": { name: "Frutas" }
  "📁 FRUTOS SECOS": { name: "Frutos secos" }
  "📁 HARINAS": { name: "Cereales y Legumbres" }
  "📁 HIGIENE": { name: "Productos de limpieza e higiene" }
  "📁 HOGAR": { name: "Productos de limpieza e higiene" }
  "📁 INFUSIONES Y TE": { name: "Bebidas" }
  "📁 LEGUMBRES": { name: "Cereales y Legumbres" }
  "📁 PASTAS Y SEMOLAS": { name: "Cereales y Legumbres" }
  "📁 SALES": { name: "Aliños y conservantes" }
  "📁 SEMILLAS Y SUPERALIMENTOS": { name: "Alimentos" }
  "📁 SETAS": { name: "Alimentos" }
  "📁 VERDURAS DESHIDRATADAS": { name: "Verduras" }

# UNIDAD cell value (case-insensitive) → granel/pesar booleans + per-unidad descripcion.
unidades:
  kg:       { granel: true,  pesar: true,  descripcion: "" }
  Unidades: { granel: false, pesar: false, descripcion: "Se pide por unidades, se paga por kg" }

defaults:
  destacado: false
  temporada: false
  precio_final: ""
  precio_productor: ""
```

- [ ] **Step 2: Validate it loads**

Run:
```bash
python -c "from pathlib import Path; from scripts.preprocess.lavidaagranel import load_config; c = load_config(Path('scripts/preprocess/lavidaagranel.yaml')); print(c.productor, len(c.categorias), 'categorias')"
```
Expected: `La Vida a Granel 20 categorias`

- [ ] **Step 3: Commit**

```bash
git add scripts/preprocess/lavidaagranel.yaml
git commit -m "feat(lavidaagranel): producer yaml mapping"
```

---

## Task 8: xlsx walker — `iter_rows(xlsx_path) -> Iterator[RawRow]`

**Files:**
- Modify: `scripts/preprocess/lavidaagranel.py`
- Modify: `tests/preprocess/test_lavidaagranel.py`
- Create: `tests/preprocess/fixtures/lavidaagranel_min.xlsx` (built programmatically by the test)

- [ ] **Step 1: Add a fixture-builder helper to the test file**

The fixture xlsx is generated by the test on demand so the binary doesn't live in git. Append to `tests/preprocess/test_lavidaagranel.py`:

```python
import openpyxl


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
    ws.append(["📁 MYSTERY"])  # unmapped category in fixture yaml
    ws.append(["UNKNOWN ITEM", 1.00, "kg"])
    ws.append([None, None, None])  # blank row
    ws.append(["BROKEN PRICE", "", "kg"])  # missing price
    ws.append(["BROKEN UNIT", 1.00, ""])  # missing unit
    wb.save(path)
```

- [ ] **Step 2: Write failing tests for the walker**

Append:
```python
from scripts.preprocess.lavidaagranel import RawRow, iter_rows


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
    # Section tracking
    assert productos[0].section == "📁 ALGAS"
    assert productos[2].section == "📁 LEGUMBRES"
    assert productos[3].section == "📁 MYSTERY"
    # row_no preserved for log lines
    assert productos[0].row_no == 7  # 1-indexed: 5 header rows + section + first product
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/preprocess/test_lavidaagranel.py -v -k iter_rows`
Expected: ImportError on `RawRow`/`iter_rows`.

- [ ] **Step 4: Implement the walker**

Append to `scripts/preprocess/lavidaagranel.py`:
```python
from typing import Iterator, Literal

import openpyxl


@dataclass(frozen=True)
class RawRow:
    kind: Literal["product", "section", "blank"]
    row_no: int
    section: str | None
    producto: str | None
    precio: Any
    unidad: str | None


_SHEET_NAME = "Pedidos Grupo Consumo"
_DATA_START_ROW = 6  # first row after header banner + column header


def iter_rows(xlsx_path: Path) -> Iterator[RawRow]:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    ws = wb[_SHEET_NAME]
    current_section: str | None = None
    row_no = 0
    for raw in ws.iter_rows(values_only=True):
        row_no += 1
        if row_no < _DATA_START_ROW:
            continue
        a = raw[0] if len(raw) > 0 else None
        b = raw[1] if len(raw) > 1 else None
        c = raw[2] if len(raw) > 2 else None
        if a is None and b is None and c is None:
            yield RawRow(kind="blank", row_no=row_no, section=current_section,
                         producto=None, precio=None, unidad=None)
            continue
        if isinstance(a, str) and a.startswith("📁"):
            current_section = a.strip()
            yield RawRow(kind="section", row_no=row_no, section=current_section,
                         producto=None, precio=None, unidad=None)
            continue
        yield RawRow(
            kind="product",
            row_no=row_no,
            section=current_section,
            producto=str(a) if a is not None else None,
            precio=b,
            unidad=str(c) if c is not None else None,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/preprocess/test_lavidaagranel.py -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add scripts/preprocess/lavidaagranel.py tests/preprocess/test_lavidaagranel.py
git commit -m "feat(lavidaagranel): xlsx walker with section tracking"
```

---

## Task 9: Row mapper — `map_row(raw, cfg) -> MappedResult`

**Files:**
- Modify: `scripts/preprocess/lavidaagranel.py`
- Modify: `tests/preprocess/test_lavidaagranel.py`

- [ ] **Step 1: Write the failing tests**

Append:
```python
from scripts.preprocess.lavidaagranel import MappedResult, map_row


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/preprocess/test_lavidaagranel.py -v -k map_row`
Expected: ImportError on `MappedResult`/`map_row`.

- [ ] **Step 3: Implement the mapper**

Add at top of `scripts/preprocess/lavidaagranel.py`:
```python
from decimal import Decimal, InvalidOperation

from scripts.preprocess._common import KarakolasRow
```

Append:
```python
@dataclass(frozen=True)
class MappedResult:
    row: KarakolasRow | None
    skip_reason: str | None  # None on success; otherwise a stable reason code


def _format_price(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return f"{d:.2f}"


def map_row(raw: RawRow, cfg: Config) -> MappedResult:
    if raw.section is None:
        return MappedResult(None, "no_section")
    if raw.section not in cfg.categorias:
        return MappedResult(None, "unmapped_category")
    if raw.producto is None or not str(raw.producto).strip():
        return MappedResult(None, "missing_producto")
    precio = _format_price(raw.precio)
    if precio is None:
        return MappedResult(None, "missing_price")
    if not raw.unidad or raw.unidad.lower() not in cfg.unidades:
        return MappedResult(None, "missing_unit")
    unidad = cfg.unidades[raw.unidad.lower()]
    d = cfg.defaults
    row = KarakolasRow(
        productor=cfg.productor,
        nombre=normalize(raw.producto),
        precio_base=precio,
        categoria=cfg.categorias[raw.section],
        productor_id=cfg.productor_id,
        descripcion=unidad["descripcion"],
        granel=unidad["granel"],
        pesar=unidad["pesar"],
        destacado=bool(d["destacado"]),
        temporada=bool(d["temporada"]),
        precio_final=str(d["precio_final"]),
        precio_productor=str(d["precio_productor"]),
    )
    return MappedResult(row, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/preprocess/test_lavidaagranel.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/preprocess/lavidaagranel.py tests/preprocess/test_lavidaagranel.py
git commit -m "feat(lavidaagranel): RawRow → KarakolasRow mapper with skip reasons"
```

---

## Task 10: CLI driver `run()` + `main()` (logging + summary + exit codes)

**Files:**
- Modify: `scripts/preprocess/lavidaagranel.py`
- Modify: `tests/preprocess/test_lavidaagranel.py`

- [ ] **Step 1: Write the failing integration test**

Append:
```python
import json
from datetime import date


def test_run_integration(tmp_path, fixtures_dir):
    from scripts.preprocess.lavidaagranel import run

    xlsx = tmp_path / "min.xlsx"
    _build_fixture_xlsx(xlsx)
    out_dir = tmp_path / "out"
    log_dir = tmp_path / "logs"

    summary = run(
        xlsx=xlsx,
        config=fixtures_dir / "lavidaagranel_min.yaml",
        out_dir=out_dir,
        log_dir=log_dir,
        today=date(2026, 5, 16),
    )

    assert summary == {
        "read": 6,            # 6 product rows in fixture
        "emitted": 3,         # 2 algas + 1 legumbre
        "skipped_unmapped": 1,   # MYSTERY/UNKNOWN
        "skipped_invalid": 2,    # missing price, missing unit
        "skipped_dedup": 0,
        "rejected": 0,
    }

    csv_path = out_dir / "2026-05-16-karakolas-lavidaagranel.csv"
    log_path = log_dir / "2026-05-16-preprocess-lavidaagranel.log"
    assert csv_path.exists()
    assert log_path.exists()

    csv_lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert len(csv_lines) == 1 + 3  # header + 3 emitted rows
    assert "Alga Kombu Eco 25g" in csv_lines[1]
    assert "Garbanzo Eco" in csv_lines[3]

    log_text = log_path.read_text(encoding="utf-8")
    assert "unmapped_category" in log_text
    assert "missing_price" in log_text
    assert "missing_unit" in log_text
    assert "SUMMARY" in log_text


def test_run_dedup(tmp_path, fixtures_dir):
    from scripts.preprocess.lavidaagranel import run

    xlsx = tmp_path / "dup.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pedidos Grupo Consumo"
    for _ in range(4):
        ws.append([])
    ws.append(["PRODUCTO", "PRECIO", "UNIDAD"])
    ws.append(["📁 ALGAS"])
    ws.append(["ALGA KOMBU ECO 25G", 2.5, "Unidades"])
    ws.append(["alga kombu eco 25g", 2.5, "Unidades"])  # case-different dup after normalize
    wb.save(xlsx)

    out_dir = tmp_path / "out"
    log_dir = tmp_path / "logs"
    summary = run(
        xlsx=xlsx,
        config=fixtures_dir / "lavidaagranel_min.yaml",
        out_dir=out_dir,
        log_dir=log_dir,
        today=date(2026, 5, 16),
    )
    assert summary["emitted"] == 1
    assert summary["skipped_dedup"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/preprocess/test_lavidaagranel.py -v -k run`
Expected: ImportError on `run`.

- [ ] **Step 3: Implement `run()` + `main()`**

Add imports at top:
```python
import argparse
import sys
from datetime import date as _date

from scripts.preprocess._common import write_csv, validate
```

Append:
```python
_SKIP_REASON_BUCKET = {
    "no_section": "skipped_invalid",
    "unmapped_category": "skipped_unmapped",
    "missing_producto": "skipped_invalid",
    "missing_price": "skipped_invalid",
    "missing_unit": "skipped_invalid",
}


def _log(fh, level: str, row_no: int, category: str | None, nombre: str | None, msg: str) -> None:
    fh.write(f"{level}\trow={row_no}\tcategory={category or '-'}\tnombre={nombre or '-'}\t{msg}\n")


def run(
    *,
    xlsx: Path,
    config: Path,
    out_dir: Path,
    log_dir: Path,
    today: _date | None = None,
) -> dict[str, int]:
    today = today or _date.today()
    cfg = load_config(config)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{today.isoformat()}-karakolas-lavidaagranel.csv"
    log_path = log_dir / f"{today.isoformat()}-preprocess-lavidaagranel.log"

    summary = {
        "read": 0,
        "emitted": 0,
        "skipped_unmapped": 0,
        "skipped_invalid": 0,
        "skipped_dedup": 0,
        "rejected": 0,
    }

    emitted_rows: list[KarakolasRow] = []
    seen: set[tuple[str, str]] = set()

    with log_path.open("w", encoding="utf-8") as logfh:
        for raw in iter_rows(xlsx):
            if raw.kind != "product":
                continue
            summary["read"] += 1
            result = map_row(raw, cfg)
            if result.skip_reason is not None:
                bucket = _SKIP_REASON_BUCKET[result.skip_reason]
                summary[bucket] += 1
                _log(logfh, "WARN", raw.row_no, raw.section, raw.producto, result.skip_reason)
                continue
            row = result.row
            key = (row.productor, row.nombre)
            if key in seen:
                summary["skipped_dedup"] += 1
                _log(logfh, "WARN", raw.row_no, raw.section, row.nombre, "duplicate_nombre")
                continue
            errs = validate(row)
            if errs:
                summary["rejected"] += 1
                _log(logfh, "ERROR", raw.row_no, raw.section, row.nombre, "; ".join(errs))
                continue
            seen.add(key)
            emitted_rows.append(row)
            summary["emitted"] += 1

        write_csv(emitted_rows, csv_path)

        logfh.write("\nSUMMARY\n")
        for k in ("read", "emitted", "skipped_unmapped", "skipped_invalid",
                  "skipped_dedup", "rejected"):
            logfh.write(f"  {k:<18} {summary[k]}\n")

    return summary


def _exit_code(summary: dict[str, int]) -> int:
    bad = (summary["skipped_unmapped"] + summary["skipped_invalid"]
           + summary["skipped_dedup"] + summary["rejected"])
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="preprocess.lavidaagranel")
    p.add_argument("--xlsx", type=Path,
                   default=Path("docs/Pedidos_LaVidaAGranel_original.xlsx"))
    p.add_argument("--config", type=Path,
                   default=Path("scripts/preprocess/lavidaagranel.yaml"))
    p.add_argument("--out-dir", type=Path, default=Path("data/output"))
    p.add_argument("--log-dir", type=Path, default=Path("logs"))
    args = p.parse_args(argv)

    try:
        summary = run(
            xlsx=args.xlsx,
            config=args.config,
            out_dir=args.out_dir,
            log_dir=args.log_dir,
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    for k, v in summary.items():
        print(f"{k:<18} {v}")
    return _exit_code(summary)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/preprocess/test_lavidaagranel.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/preprocess/lavidaagranel.py tests/preprocess/test_lavidaagranel.py
git commit -m "feat(lavidaagranel): CLI driver, logging, summary, exit codes"
```

---

## Task 11: Idempotency check

**Files:** none (verification only)

- [ ] **Step 1: Add idempotency test**

Append to `tests/preprocess/test_lavidaagranel.py`:
```python
def test_run_idempotent(tmp_path, fixtures_dir):
    from scripts.preprocess.lavidaagranel import run

    xlsx = tmp_path / "min.xlsx"
    _build_fixture_xlsx(xlsx)
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    log_a = tmp_path / "la"
    log_b = tmp_path / "lb"
    args = dict(xlsx=xlsx, config=fixtures_dir / "lavidaagranel_min.yaml",
                today=date(2026, 5, 16))
    run(out_dir=out_a, log_dir=log_a, **args)
    run(out_dir=out_b, log_dir=log_b, **args)
    csv_a = (out_a / "2026-05-16-karakolas-lavidaagranel.csv").read_bytes()
    csv_b = (out_b / "2026-05-16-karakolas-lavidaagranel.csv").read_bytes()
    assert csv_a == csv_b
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/preprocess/test_lavidaagranel.py -v`
Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add tests/preprocess/test_lavidaagranel.py
git commit -m "test(lavidaagranel): idempotency of preprocess run"
```

---

## Task 12: End-to-end smoke run on the real xlsx

**Files:** none (verification only)

- [ ] **Step 1: Run the driver against the real producer file**

Run:
```bash
source .venv/bin/activate
python -m scripts.preprocess.lavidaagranel
```

Expected stdout (counts may shift slightly if xlsx layout has surprises):
```
read               <n>
emitted            <m>
skipped_unmapped   0
skipped_invalid    <k>
skipped_dedup      <d>
rejected           0
```

Where `<n>` ≈ 511, `<m>` ≈ 510 minus skips. `skipped_unmapped` should be 0 because the shipped yaml covers all 20 vendor sections.

- [ ] **Step 2: Inspect the output CSV**

Run:
```bash
head -5 data/output/$(date +%Y-%m-%d)-karakolas-lavidaagranel.csv
wc -l data/output/$(date +%Y-%m-%d)-karakolas-lavidaagranel.csv
```

Expected: header line + N data lines, N matching `emitted` count above. Header equals exactly:
```
productor,nombre,precio_base,categoria,productor_id,descripcion,granel,pesar,destacado,temporada,precio_final,precio_productor
```

- [ ] **Step 3: Inspect the log**

Run:
```bash
tail -20 logs/$(date +%Y-%m-%d)-preprocess-lavidaagranel.log
```

Expected: a `SUMMARY` block matching stdout. Any `WARN`/`ERROR` lines above it should look plausible (e.g. a row with missing PRECIO).

- [ ] **Step 4: Commit the generated output and log**

```bash
git add data/output/*.csv logs/*.log
git commit -m "chore(lavidaagranel): initial preprocess output snapshot"
```

(If `.gitignore` already excludes `data/output/` or `logs/`, skip this step and instead document the run in the PR/notes.)

---

## Self-Review

- **Spec coverage**
  - Inputs (xlsx, yaml) → Tasks 6/7/8. ✓
  - Output path/format → Tasks 4/10. ✓
  - Transformation rules → Tasks 5/6/9. ✓
  - normalize rule → Task 5. ✓
  - Skip/reject rules → Tasks 9/10. ✓
  - Logging + summary → Task 10. ✓
  - CLI + exit codes → Task 10. ✓
  - Layout (`scripts/preprocess/...`) → Tasks 1–7. ✓
  - Dependencies (openpyxl, PyYAML) → Task 1. ✓
  - Testing strategy (normalize, validate, integration, idempotency) → Tasks 3/5/10/11. ✓
- **Placeholder scan** — no TBD/TODO; every code step contains complete code.
- **Type consistency** — `KarakolasRow`, `RawRow`, `Config`, `MappedResult` are each defined once; method/field names match across tasks (`column_order`, `productor_id`, `descripcion`, `iter_rows`, `map_row`, `run`).
- **Spec inconsistencies** — surfaced at top of this plan; resolution choices reflected in the yaml shipped in Task 7 and the loader/mapper in Tasks 6/9.
