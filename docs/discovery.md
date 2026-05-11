# karakolas.net — Discovery Notes

Reverse-engineered behavior of the karakolas.net web app (v `5.0.2`) needed to drive
unattended product uploads. All probes performed on the test instance
(`https://test.karakolas.org`) as user `bilbo` (admin of group `La Comarca`,
`grupo=523`). Every write was reverted; producer 460 (Menudos Huertos) used as the
write target.

Companion HAR captures live in `logs/`:
- `logs/discover-session1.har` — initial browse + edit-page render
- `logs/save-roundtrip.har` — POST capture of the product-save endpoint

> **Cert quirk**: `https://www.karakolas.net` returns `ERR_CERT_COMMON_NAME_INVALID`.
> Always use the apex `https://karakolas.net` (or `https://test.karakolas.org`).

---

## 1. Stack

- web2py app, Spanish UI, GPL-AGPL.
- Frontend SPA shell: `/karakolas/static/_5.0.2/front/src/index.html` loaded for any
  HTML route. Real content arrives via `.load` XHR partials (jQuery `LOAD()` + web2py
  components).
- Same controller serves `.html` (browser entry, returns SPA shell) and `.load`
  (XHR partial, returns HTML fragment). The product editor submits to `.load`.
- All `.load` partials require header `X-Requested-With: XMLHttpRequest`. Without
  it the server returns the SPA shell.
- Version probe: `GET /default/version.json`.

## 2. Auth

- Login form: `GET /user.html/login` → POST `/user.load/login`
  with form fields `username`, `password`.
- Test instance landing `/` redirects to `/default/home.load` showing demo notice
  (users gandalf/frodo/bilbo/aragorn/faramir/sauron/anillo, password `karakolas`)
  before the user clicks the login link.
- Sessions are cookie-based. Sessions can expire mid-run with the response body
  containing `NOT AUTHORIZED Please login to view this content.` — re-login and retry.

## 3. Group enumeration

- Source of truth: `GET /karakolas/default/menu.load` (with XHR header).
- Top-level `<li class="dropdown">` items whose label is **not** one of
  `Usuaria | Home | Ayuda | Admin <name>` are groups. The dropdown's child links
  carry `?grupo={ID}`. Label = group display name.
- The same IDs appear in `/default/home.load`. For a single-group user any
  `<a href="...?grupo=N">` will do.
- Practical: have the user supply `KARAKOLAS_GROUP_ID` in `.env` to skip
  enumeration in the upload pipeline.

## 4. Producer discovery (per group)

Two distinct partials, both behind the admin "Productoras/es" page
(`/productores/index.html?grupo={G}`):

| Partial                                                                 | Returns                                       | upload.py touches? |
| ----------------------------------------------------------------------- | --------------------------------------------- | ------------------ |
| `GET /productores/vista_productores.load?grupo={G}`                     | **Propios** (own producers)                   | **Yes**            |
| `GET /productores/productores_coordinados.load?grupo={G}`               | Coordinated (network) producers — read-only   | No                 |
| `GET /productores/index.load?grupo={G}`                                 | Page skeleton + admin links                   | No                 |
| `GET /productores/nuevo_productor.load?grupo={G}`                       | "Add producer" form                           | Out of scope       |

`vista_productores.load` returns a `<table id="tabla_productores">` with one row
per propio producer. Each row exposes:

- `Editar productos` → `/productores/productos.html?productor={P}` (CRUD page).
- `Editar datos`    → `/productores/edita_productor.html?productor={P}`.
- `Exportar datos`  → `/gestion_pedidos/exportar_productos.csv?auth_code={CODE}&productor={P}`.

> **`auth_code` rotates per session/render** (e.g. `SkOBgrprvi…QA` →
> `PaEVQExMdC…VR` between sessions). Never cache it across runs — always re-scrape
> from `vista_productores.load`.

Test fixture (group La Comarca, `grupo=523`):
- Propio: `productor=460` "Menudos Huertos".
- Coordinated: `productor=458` "Cervezas Veer", `productor=461` "Otro" (under
  red "Tierra Media", `grupo=520`).

## 5. CSV export — the read endpoint

```
GET /gestion_pedidos/exportar_productos.csv?auth_code={CODE}&productor={P}
```

Returns four labelled sections in one CSV (CRLF line endings):

```
PRODUCTOR
nombre,Menudos Huertos
email,
grupo,La Comarca
telefono,
direccion,
descripcion,
comentarios_internos,
info_pedido,<h3>Abrir pedido</h3>...
activo,True
formula_precio_final,precio_base
formula_precio_productor,precio_base
formula_coste_extra_pedido,0
formula_coste_extra_productor,0
reglas,


CAMPOS EXTRA
campo_extra_pedido.nombre,campo_extra_pedido.valor


COLUMNAS EXTRA
columna_extra_pedido.nombre,columna_extra_pedido.tipo


PRODUCTOS
productoXpedido.nombre,productoXpedido.precio_base,productoXpedido.precio_final,productoXpedido.precio_productor,productoXpedido.descripcion,productoXpedido.granel,productoXpedido.destacado,productoXpedido.temporada,categorias_productos.codigo
Zanahoria,2.00,2.00,2.00,,True,,True,50101500
Tomate,1.00,1.00,1.00,,True,,True,50101500
Calabaza,1.00,1.00,1.00,"Se pide por unidades, se paga por kg",,,True,50101500
```

Notes:
- `categorias_productos.codigo` is the **UNSPSC code** (e.g. `50101500` = vegetables).
  This is **not** the value the form POSTs back (see §6.4).
- `pesar` field exists in the editor form but is **absent** from the CSV — semantics
  unclear; likely "weigh at delivery" boolean. Round-trip safe to omit on read,
  preserve from prior POST on write.
- Boolean fields export as `True` / blank.

Use this as the read-side of the idempotency check. Cheaper than scraping the
editor HTML.

## 6. Product editor — the write endpoint

### 6.1 GET (page render)

```
GET /productores/productos.html?productor={P}    # browser → SPA shell
GET /productores/productos.load?productor={P}    # XHR partial
```

The XHR partial returns the editable form. Submit posts back to the same `.load`
URL. Form `action="#"` + `data-w2p_target="main-region"` (web2py LOAD-style
component, replaces the in-page region with the response).

### 6.2 POST (save)

```
POST /productores/productos.load?productor={P}
Content-Type: multipart/form-data; boundary=...
X-Requested-With: XMLHttpRequest
Referer: https://test.karakolas.org/productores/productos.html?productor={P}
Cookie: session=...
```

Response: `200 OK` with HTML fragment of the re-rendered editor (often empty body
when the request was a no-op). No JSON.

### 6.3 Ertable widget anatomy

The editor uses web2py's "ertable" widget. **Two ertables coexist on the page**;
both must round-trip in the POST even if empty:

| Hidden `_table_name_{TID}` value | Purpose                  |
| -------------------------------- | ------------------------ |
| `productoXpedido`                | The product rows         |
| `campo_extra_pedido`             | Extra per-order fields   |

**`{TID}` is a random number regenerated on every render.** Always scrape from the
GET response — never hardcode. Find it via:

```js
const tid = document.querySelector('input[name^=_table_name_][value=productoXpedido]')
              .name.replace('_table_name_', '');
```

### 6.4 Per-row form fields (productoXpedido)

Field name pattern: `ertable_{TID}_cell_{field}_{N}` where `N` is the 0-indexed row.

| Field             | Type      | Notes                                                                  |
| ----------------- | --------- | ---------------------------------------------------------------------- |
| `nombre`          | string    | **Idempotency key** per (producer, nombre).                            |
| `precio_base`     | decimal   | String like `"1.00"`.                                                  |
| `precio_final`    | decimal   | Only sent when "Controles avanzados" is open. Defaults `"0"` if blank. |
| `precio_productor`| decimal   | Same as above.                                                         |
| `descripcion`     | string    | Free text.                                                             |
| `categoria`       | int (id)  | **Internal DB id** (e.g. `1088`=Verduras), **not** UNSPSC.             |
| `granel`          | bool      | Submit `"on"` if checked, **omit field entirely** if unchecked.        |
| `pesar`           | bool      | Same.                                                                  |
| `destacado`       | bool      | Same.                                                                  |
| `temporada`       | bool      | Same.                                                                  |

### 6.5 Required hidden control fields

Per ertable (must be present even when empty):

```
_ertable_{TID}_fields                 = comma-list of column names in order
_table_name_{TID}                     = productoXpedido | campo_extra_pedido
_ultima_fila_{TID}                    = highest row index in the submission (int)
_ertable_{TID}_paste_into_cell        = nombre_0
_sample_row_{TID}                     = HTML template for blank row
_ertable_{TID}_sample_th              = HTML template for new column header
_ertable_{TID}_sample_td_decimal      = HTML template for new decimal cell
_ertable_{TID}_sample_td_string       = HTML template for new string cell
```

Plus page-level:

```
formula_precio_final     = precio_base
formula_precio_productor = precio_base
```

The `_sample_*` HTML blobs are echoed back to the server unchanged — copy verbatim
from the GET response.

### 6.6 Submit buttons

In the rendered HTML:

| Selector              | `value`                       | Behavior                       |
| --------------------- | ----------------------------- | ------------------------------ |
| `#submit_button`      | "Grabar los cambios"          | Save and stay on page.         |
| `#submit_and_go_button` | "Grabar los cambios y volver" | Save and redirect.             |

Either triggers the POST in §6.2. For headless replay, the click is unnecessary —
just send the multipart body directly.

### 6.7 Categoria id ↔ label (test instance)

Scraped from `<select.ertable_field_categoria option>`. **IDs are likely
per-instance — re-scrape on production.**

| ID    | Label                          |
| ----- | ------------------------------ |
| 1075  | Frutos secos                   |
| 1076  | Carnes, aves y embutidos       |
| 1077  | Pescado y Marisco              |
| 1078  | Lácteos y huevos               |
| 1079  | Aceites y grasas               |
| 1080  | Chocolate y dulces             |
| 1081  | Aliños y conservantes          |
| 1082  | Panadería y bollería           |
| 1083  | Comidas preparadas             |
| 1084  | Bebidas                        |
| 1085  | Cereales y Legumbres           |
| 1086  | _Ninguna de las anteriores     |
| 1087  | Productos de limpieza e higiene|
| 1088  | Verduras                       |
| 1089  | Frutas                         |
| 1090  | Algas y plantas acuáticas      |
| 1091  | Ropa                           |
| 1092  | Alimentos                      |
| 1093  | Oficina                        |
| 1094  | Papel                          |

The CSV export's `categorias_productos.codigo` (UNSPSC) is a separate, stable
identifier — not exchangeable with the form ID. Mapping between the two is not
exposed in the UI; if needed for cross-instance portability, build it once by
joining categoria-label → UNSPSC-of-existing-product.

## 7. Idempotency model (empirically established)

Three POST experiments on producer 460:

1. Submit form unchanged → CSV byte-stable (1015 → 1015 bytes). Safe no-op.
2. Append row at index 3 with `nombre=Calabaza` (already row 0) and `precio=9.99`
   → CSV unchanged. Server **silently drops the duplicate** (likely a UNIQUE
   constraint on `(productor_id, nombre)` failing only at insert time).
3. Modify row 0 `precio_base` `1.00` → `9.99` → CSV updated. Reverted likewise.
4. Modify row 0 `nombre` "Calabaza" → "Calabaza_X" → row updated **in place**,
   all other fields preserved.

Conclusion: server treats rows by **position** in the submission. Rows `0..N-1`
update existing DB rows in order; rows `>= existing-count` are inserts (subject to
the `nombre` UNIQUE constraint). Renames work in place server-side.

**No hidden DB id per row in the form** (verified by inspecting `<tr>` HTML — only
cell inputs, no `_id`).

## 8. upload.py rules (project decisions)

Per project owner:

- Only touch producers marked **propios** for the configured group.
- For each product in input CSV, key by `nombre`:
  - **same name, changed price / categoria / descripcion / flags** → update at
    that row's existing position.
  - **name in CSV not in current** → append as new row.
  - **name in current not in CSV** → delete row.
  - **renamed** (different name in CSV) → falls out naturally as delete-old +
    create-new (input CSV has no rename concept).
- Idempotency key locked: `(productor_id, productoXpedido.nombre)`.
- Whole-table replace on POST — must always send all kept rows, not just diffs.

## 9. Editor pagination

The product editor paginates at **~20 rows per page** for producers with more
than 20 products. Pages are exposed as anchors at the top of the form:

```html
<a href="/productores/productos.html?page=0&productor=460" title="From X up to Y">1</a>
<a href="/productores/productos.html?page=1&productor=460" title="From P up to Q">2</a>
```

The default GET (no `page` param) returns page 0. To read the **complete**
current state, walk all `?page=N&productor={P}` links. Only the cell rows
differ across pages — TID values, hidden control templates, categoria `<select>`
options, and submit buttons are identical.

Save POST behavior across pagination is empirically permissive: a POST sent to
`productos.load?productor={P}` with N rows (no `page` param) will accept all N
rows even if N > the per-page cap. Server appears to treat save as whole-table
replace, with `nombre` UNIQUE constraint applying to inserts.

> **Caution untested**: behavior when POSTing **fewer** rows than DB currently
> holds. Whole-table-replace semantics suggest the missing rows would be
> deleted. Verify before relying on it.

`upload.py` walks all pages on `fetch_editor` and submits one consolidated POST.

## 10. Open questions (next session)

- **Row delete mechanics**: does omitting a row from the POST delete it
  server-side, or is the client-side `delete` link (`POST /none.load` removing the
  `<tr>`) load-bearing? `_ultima_fila_{TID}` decrements on delete client-side.
  Need empirical test before relying on omit-to-delete in upload.py.
- **Production categoria IDs**: re-scrape on prod; build label↔ID map at runtime
  rather than hardcoding the table in §6.7.
- **`pesar` semantics**: present in editor form, absent in CSV export. Confirm with
  product owner whether it must be preserved on round-trip and whether input CSV
  needs a column for it.
- **Multi-group users**: bilbo only has La Comarca. For users in multiple groups
  (gandalf etc.) confirm `vista_productores.load?grupo={G}` filters strictly by
  the queried group.
- **Concurrency / locking**: behavior when two browsers edit the same producer is
  unknown. The "salir sin guardar" client-side guard suggests last-write-wins.
- **Rename input semantics**: project rule prefers delete+create on rename, but
  the form supports rename-in-place. Decide whether upload.py should ever expose
  a "rename" path (e.g. via an explicit alias column in input CSV) or always
  follow the simple name-keyed diff.

## 11. Environment

`.env` keys (test values shown — overwrite for prod):

```env
KARAKOLAS_URL=https://test.karakolas.org
KARAKOLAS_USER=bilbo
KARAKOLAS_PASS=karakolas
KARAKOLAS_GROUP_ID=523        # La Comarca on test; numeric, prod will differ
```

Tooling:

- `agent-browser` (Vercel Labs) drives Chromium for discovery and any
  browser-mediated steps. Snapshots use stable `@e1`-style refs.
- `Scrapling` parses HAR/HTML responses where the wire format is needed.
- For upload.py the cheapest path is HTTP-direct (replay the POST body in §6.2)
  with `requests` + a session cookie obtained via the login flow. Browser
  automation only needed if web2py adds CSRF tokens not yet observed.
