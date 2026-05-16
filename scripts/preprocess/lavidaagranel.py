import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

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
