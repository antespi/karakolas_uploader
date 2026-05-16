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
