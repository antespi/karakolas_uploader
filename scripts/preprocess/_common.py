import csv
from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

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


def _serialize(row: KarakolasRow, columns: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for col in columns:
        v = getattr(row, col)
        if isinstance(v, bool):
            out.append("True" if v else "False")
        else:
            out.append(str(v))
    return out


def write_csv(rows: Iterable[KarakolasRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = KarakolasRow.column_order()
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow(_serialize(row, columns))
