# Preprocess: La Vida a Granel → karakolas.csv

## Goal

Convert `docs/Pedidos_LaVidaAGranel_original.xlsx` (vendor order-form
spreadsheet) into a normalized `karakolas.csv` consumable by
`scripts/upload.py`. This is the first per-producer preprocessor. The
design must generalize: future producers ship their own xlsx/csv format
and get their own preprocessor + config file but emit rows into the same
canonical schema documented in `docs/karakolas-template.md`.

## Scope

In scope:
- One Python script tailored to the La Vida a Granel xlsx shape.
- One YAML config file holding producer name, category map, unit-flag
  map, and field defaults.
- Output written to a dated CSV under `data/output/`.
- A run log under `logs/`.

Out of scope:
- Any other producer's format (each gets its own script + yaml).
- Upload logic (lives in `scripts/upload.py`).
- A generic dispatcher CLI — preprocessors are run individually.

## Inputs

### Vendor xlsx

`docs/Pedidos_LaVidaAGranel_original.xlsx`. Single sheet
`Pedidos Grupo Consumo`. Header banner rows 1–3, blank row 4, column
header row 5:

| col | header   | role                                    |
| --- | -------- | --------------------------------------- |
| A   | PRODUCTO | product name or `📁 …` section header   |
| B   | PRECIO   | unit price (decimal)                    |
| C   | UNIDAD   | `kg` or `Unidades`                      |
| D–M | FAMILIA n| per-family order quantities (ignored)   |
| N   | TOTAL    | computed total (ignored)                |

From row 6 onwards, the sheet alternates between **section header rows**
(column A starts with `📁`, other cells empty) and **product rows**
(PRECIO non-empty). Empty rows occur and are skipped. Twenty section
headers, ~511 product rows.

### YAML config

Path: `scripts/preprocess/lavidaagranel.yaml`.

```yaml
productor: La Vida a Granel

# Vendor section-header label → karakolas categoria label.
# Missing key, or null value → rows under it are skipped + logged.
categorias:
  "📁 ALGAS": Algas y plantas acuáticas
  "📁 ALIMENTOS / BEBIDAS": Bebidas
  "📁 ALIMENTOS / VARIOS": Alimentos
  "📁 ARROCES": Cereales y Legumbres
  "📁 AZUCAR, CACAO Y CHOCOLATE": Chocolate y dulces
  "📁 CAFE": Bebidas
  "📁 CEREALES Y COPOS": Cereales y Legumbres
  "📁 ESPECIAS": Aliños y conservantes
  "📁 FRUTAS DESHIDRATADAS": Frutas
  "📁 FRUTOS SECOS": Frutos secos
  "📁 HARINAS": Cereales y Legumbres
  "📁 HIGIENE": Productos de limpieza e higiene
  "📁 HOGAR": Productos de limpieza e higiene
  "📁 INFUSIONES Y TE": Bebidas
  "📁 LEGUMBRES": Cereales y Legumbres
  "📁 PASTAS Y SEMOLAS": Cereales y Legumbres
  "📁 SALES": Aliños y conservantes
  "📁 SEMILLAS Y SUPERALIMENTOS": Alimentos
  "📁 SETAS": Alimentos
  "📁 VERDURAS DESHIDRATADAS": Verduras

# UNIDAD cell value (case-insensitive) → granel/pesar booleans.
unidades:
  kg:       { granel: true,  pesar: true  }
  Unidades: { granel: false, pesar: false }

defaults:
  destacado: false
  temporada: true
  precio_final: ""
  precio_productor: ""
  descripcion: ""
```

All four sub-keys (`productor`, `categorias`, `unidades`, `defaults`)
are required. Any unknown top-level key triggers a fatal error.

## Output

Path: `data/output/<YYYY-MM-DD>-karakolas-lavidaagranel.csv` (date =
local-time run date).

Columns in mandatory-first order from `docs/karakolas-template.md`:

```
productor,nombre,precio_base,categoria,productor_id,descripcion,
granel,pesar,destacado,temporada,precio_final,precio_productor
```

- UTF-8, `,` delimiter, `"` quotes, `\n` line endings.
- `productor_id` always empty (resolved at upload time).
- Booleans serialized as `True` / `False`.

## Transformation rules

Per product row:

| karakolas field    | source                                                                 |
| ------------------ | ---------------------------------------------------------------------- |
| `productor`        | `yaml.productor`                                                       |
| `nombre`           | normalize(PRODUCTO)                                                    |
| `precio_base`      | `f"{PRECIO:.2f}"`                                                      |
| `categoria`        | `yaml.categorias[current_section_header]`                              |
| `productor_id`     | empty                                                                  |
| `descripcion`      | `yaml.defaults.descripcion`                                            |
| `granel`           | `yaml.unidades[UNIDAD.lower()].granel`                                 |
| `pesar`            | `yaml.unidades[UNIDAD.lower()].pesar`                                  |
| `destacado`        | `yaml.defaults.destacado`                                              |
| `temporada`        | `yaml.defaults.temporada`                                              |
| `precio_final`     | `yaml.defaults.precio_final`                                           |
| `precio_productor` | `yaml.defaults.precio_productor`                                       |

### `normalize(PRODUCTO)`

1. Strip surrounding whitespace, collapse internal runs of whitespace to
   single space.
2. Apply Python `str.title()`.
3. For each token, if it matches the regex `^\d+[A-Za-z]+$`, lowercase
   the alphabetic suffix (so `25G` → `25g`, `33Cl` → `33cl`,
   `1L` → `1l`).

This rule is the producer-facing identity of the product, so it is
**idempotency-critical**: changing it later will cause duplicate
products in karakolas on the next upload run. Do not adjust without a
coordinated cleanup.

## Skip and reject rules

A row is **skipped silently** when:
- Both PRODUCTO and PRECIO are empty (blank spacer row).
- PRODUCTO starts with `📁` (section header — used to update the
  current category, not emitted).

A row is **skipped with a warn-level log entry** when:
- PRECIO is empty or non-numeric.
- The current section header is not present in `yaml.categorias` (or
  its value is null).
- UNIDAD is empty or not a key in `yaml.unidades`.
- `(productor, nombre)` was already emitted earlier in the run
  (duplicate after normalization).

A row is **rejected with an error-level log entry** when, after
mapping, it fails any rule in `docs/karakolas-template.md` §
"Validation rules". Rejected rows are not written; the run continues.

## Logging

Path: `logs/<YYYY-MM-DD>-preprocess-lavidaagranel.log`. Plain text,
one event per line: `LEVEL\trow=<n>\tcategory=<…>\tnombre=<…>\t<msg>`.

At end of run, append a summary block:

```
SUMMARY
  read:               <int>
  emitted:            <int>
  skipped_unmapped:   <int>
  skipped_invalid:    <int>
  skipped_dedup:      <int>
  rejected:           <int>
```

Same summary echoed to stdout.

## CLI

```
python -m scripts.preprocess.lavidaagranel \
    --xlsx docs/Pedidos_LaVidaAGranel_original.xlsx \
    --config scripts/preprocess/lavidaagranel.yaml \
    --out-dir data/output \
    --log-dir logs
```

All four flags have sensible defaults matching the paths above; running
with no args works for the canonical layout.

Exit codes:
- `0` clean run, zero skips and zero rejects.
- `1` ran to completion but some rows were skipped or rejected.
- `2` fatal: xlsx unreadable, yaml malformed, output dir creation
  failed.

## Layout

```
scripts/
  preprocess/
    __init__.py
    _common.py           # CSV writer + validation shared across producers
    lavidaagranel.py     # this producer's driver
    lavidaagranel.yaml   # this producer's config
```

`_common.py` exposes:
- `KarakolasRow` dataclass with the 12-column schema.
- `validate(row, allowed_categorias) -> list[str]` returning rule
  violations (empty list = OK).
- `write_csv(rows, path)` emitting the mandatory-first column order.
- `ALLOWED_CATEGORIAS` constant from the template doc.

`lavidaagranel.py` owns the xlsx walk and yaml loading and never
touches CSV serialization directly.

## Dependencies

Add to `requirements.txt`:
- `openpyxl` — xlsx reader.
- `PyYAML` — config loader.

(Confirm both not already present before adding.)

## Testing strategy

- Unit test `normalize` against a small table covering `25G`, `33CL`,
  `1L`, accented characters, multiple spaces.
- Unit test `validate` with happy-path row + one row per rule
  violation.
- Integration test: run the driver against a tiny fixture xlsx (4–6
  rows covering mapped/unmapped/missing-price/dup) and assert the
  emitted CSV + log summary byte-for-byte.
- Idempotency test: run twice against the same fixture; outputs
  identical.

## Future producers

A new producer follows the same shape:
1. Add `scripts/preprocess/<producer>.py` reading its native format.
2. Add `scripts/preprocess/<producer>.yaml` with the same four keys
   (`productor`, `categorias`, `unidades`, `defaults`). The
   `categorias` keys are whatever section labels the source format
   uses; values stay constrained to the karakolas allowed list.
3. Reuse `_common.py` for validation and CSV output.

No central registry is needed — each producer's CLI is independent.
