import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator, Literal

import openpyxl
import yaml

from scripts.preprocess._common import KarakolasRow

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
            raise ValueError(
                f"unidad {k!r} missing keys: {sorted(required - set(v.keys()))}"
            )
        unidades[k.lower()] = {
            "granel": bool(v["granel"]),
            "pesar": bool(v["pesar"]),
            "descripcion": str(v["descripcion"]),
        }

    return Config(
        productor=str(raw["productor"]),
        productor_id=str(raw.get("productor_id", "")),
        categorias=categorias,
        unidades=unidades,
        defaults=defaults,
    )


@dataclass(frozen=True)
class RawRow:
    kind: Literal["product", "section", "blank"]
    row_no: int
    section: str | None
    producto: str | None
    precio: Any
    unidad: str | None


_SHEET_NAME = "Pedidos Grupo Consumo"
_DATA_START_ROW = 6


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


@dataclass(frozen=True)
class MappedResult:
    row: KarakolasRow | None
    skip_reason: str | None


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
