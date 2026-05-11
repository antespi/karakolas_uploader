# `karakolas.csv` — column reference

Normalized CSV consumed by `upload.py`. One row per product. A single file may
hold rows for many producers — the first column (`productor`) routes each row to
its producer.

Encoding: UTF-8. Delimiter: `,`. Quote: `"`. Line endings: `\n` or `\r\n`.

Columns are ordered **mandatory first, optional last**. Keep this order in
generated files for readability and easier diffing.

## Mandatory

| #  | Column        | Type    | Notes                                                                                                                                |
| -- | ------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| 1  | `productor`   | string  | Producer display name as it appears in karakolas (e.g. `Menudos Huertos`). Must match a **propio** producer of the configured group. Used to resolve `productor_id` when that column is empty, and as a safety check (label vs. id) when both are filled. |
| 2  | `nombre`      | string  | Idempotency key per `(productor, nombre)`. Must be unique within file **per producer**. Trim whitespace. Renaming = delete old + create new. |
| 3  | `precio_base` | decimal | Price seen by buyers. Format: `1.00` (two decimals, dot separator). No currency symbol.                                              |
| 4  | `categoria`   | string  | Category **label** as displayed in karakolas (e.g. `Verduras`, `Bebidas`, `Aceites y grasas`). `upload.py` resolves to internal id at runtime. Required by the editor — empty → submit fails. |

Allowed `categoria` values (test instance — confirm against prod):

```
Aceites y grasas, Algas y plantas acuáticas, Alimentos, Aliños y conservantes,
Bebidas, Carnes, aves y embutidos, Cereales y Legumbres, Chocolate y dulces,
Comidas preparadas, Frutas, Frutos secos, Lácteos y huevos, Oficina,
Panadería y bollería, Papel, Pescado y Marisco, Productos de limpieza e higiene,
Ropa, Verduras, _Ninguna de las anteriores
```

## Optional

| #  | Column             | Type    | Default | Notes                                                                                                       |
| -- | ------------------ | ------- | ------- | ----------------------------------------------------------------------------------------------------------- |
| 5  | `productor_id`     | int     | (resolved from `productor`) | Karakolas internal producer id (e.g. `460`). When present, `upload.py` uses it directly to build `productos.html?productor={id}` and skips the name lookup. **Instance-specific** (test ≠ prod) — leave blank for portable CSVs. If both `productor` and `productor_id` are filled, the resolved id must match the supplied id, otherwise the row is rejected. |
| 6  | `descripcion`      | string  | empty   | Free text. May contain commas — quote the cell.                                                             |
| 7  | `granel`           | bool    | `False` | "Se vende a granel". Accepts `True`/`False`, `1`/`0`, `yes`/`no` (case-insensitive).                        |
| 8  | `pesar`            | bool    | `False` | "Se pesa al repartir". Same accepted forms as `granel`. Absent from CSV export — preserve when round-tripping. |
| 9  | `destacado`        | bool    | `False` | Highlight in the order UI.                                                                                  |
| 10 | `temporada`        | bool    | `True`  | "En temporada". `False` greys out the product.                                                              |
| 11 | `precio_final`     | decimal | `precio_base` (via formula on producer) | Override per row. Leave blank to inherit.                                       |
| 12 | `precio_productor` | decimal | `precio_base` (via formula on producer) | Override per row. Leave blank to inherit.                                       |

## Validation rules `preprocess.py` must enforce

- All mandatory columns present and non-empty per row.
- `nombre` unique within `(productor, nombre)` — duplicates across producers are allowed.
- `productor` resolves to a propio producer of the configured `KARAKOLAS_GROUP_ID` (validated by `upload.py` at runtime against `vista_productores.load`; `preprocess.py` only checks non-empty / consistent spelling).
- `precio_base` parses as decimal ≥ 0.
- `categoria` is in the allowed list (case-sensitive — match karakolas labels exactly, including accents).
- `precio_final` and `precio_productor`, if non-empty, parse as decimal ≥ 0.
- Booleans normalized to `True` / `False` on output.

## See also

- `discovery.md` §6.4 (per-row form fields) and §6.7 (categoria id table) for what
  `upload.py` does with each column when POSTing to karakolas.
