#!/usr/bin/env python3
"""
upload.py — drive product uploads to karakolas.net producers from a CSV.

See docs/karakolas-template.csv for the input shape and docs/discovery.md for
the underlying wire format. Idempotent: re-running with the same input
converges to the same on-server state.
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any

from curl_cffi import CurlMime
from curl_cffi import requests as ccr
from lxml import html

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV = PROJECT_ROOT / ".env"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"

PRODUCT_FIELDS = (
    "nombre",
    "precio_base",
    "precio_final",
    "precio_productor",
    "descripcion",
    "categoria",
    "granel",
    "pesar",
    "destacado",
    "temporada",
)
BOOL_FIELDS = ("granel", "pesar", "destacado", "temporada")
TRUTHY = {"true", "1", "yes", "y", "on", "sí", "si"}
FALSY = {"false", "0", "no", "n", "off", ""}

log = logging.getLogger("upload")


# ---------------------------------------------------------------------------
# Helpers


def parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    s = str(value).strip().lower()
    if s in TRUTHY:
        return True
    if s in FALSY:
        return False
    raise ValueError(f"unrecognised boolean: {value!r}")


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# ---------------------------------------------------------------------------
# Editor state parsing


@dataclass
class EditorState:
    """Snapshot of /productores/productos.load?productor=P GET response."""

    raw_form_fields: dict[str, str] = field(default_factory=dict)
    productox_tid: str = ""
    campo_extra_tid: str = ""
    current_rows: list[dict[str, Any]] = field(default_factory=list)
    categoria_label_to_id: dict[str, str] = field(default_factory=dict)


def parse_editor(html_text: str) -> EditorState:
    doc = html.fromstring(html_text)
    state = EditorState()

    # Discover the two ertables by their _table_name_{TID} hidden input.
    for inp in doc.xpath("//input[starts-with(@name,'_table_name_')]"):
        tid = inp.get("name").removeprefix("_table_name_")
        if inp.get("value") == "productoXpedido":
            state.productox_tid = tid
        elif inp.get("value") == "campo_extra_pedido":
            state.campo_extra_tid = tid
    if not state.productox_tid:
        raise RuntimeError("productoXpedido ertable not found in editor HTML")

    # Snapshot every named form field so we can echo non-cell hidden inputs back.
    form = doc.xpath("//form")[0]
    for el in form.xpath(".//input[@name] | .//textarea[@name] | .//select[@name]"):
        name = el.get("name")
        tag = el.tag
        if tag == "input":
            itype = (el.get("type") or "text").lower()
            if itype == "checkbox":
                # only include if checked at render-time — server treats absence as unchecked
                if el.get("checked") is not None:
                    state.raw_form_fields[name] = el.get("value", "on")
                # leave unchecked rows out of raw_form_fields entirely
            else:
                state.raw_form_fields[name] = el.get("value", "")
        elif tag == "textarea":
            state.raw_form_fields[name] = el.text or ""
        elif tag == "select":
            sel = el.xpath(".//option[@selected]")
            state.raw_form_fields[name] = sel[0].get("value", "") if sel else ""

    # Extract current productoXpedido rows in order.
    cell_re = re.compile(
        rf"^ertable_{re.escape(state.productox_tid)}_cell_([a-z_]+)_(\d+)$"
    )
    rows: dict[int, dict[str, Any]] = {}
    for name, value in state.raw_form_fields.items():
        m = cell_re.match(name)
        if not m:
            continue
        field_name, idx = m.group(1), int(m.group(2))
        rows.setdefault(idx, {})[field_name] = value
    # Also include checkbox cells that were unchecked (absent from raw_form_fields)
    # by inspecting all cell-named inputs in the form.
    for el in form.xpath(".//input[contains(@name,'_cell_')]"):
        name = el.get("name")
        m = cell_re.match(name)
        if not m:
            continue
        field_name, idx = m.group(1), int(m.group(2))
        rows.setdefault(idx, {}).setdefault(field_name, "")

    for idx in sorted(rows):
        row = rows[idx]
        # only count "real" rows that have a non-empty nombre
        if (row.get("nombre") or "").strip():
            row["_idx"] = idx
            state.current_rows.append(row)

    # Categoria label → id map.
    cat_select = form.xpath(
        ".//select[contains(@class,'ertable_field_categoria')]"
    )
    if cat_select:
        for opt in cat_select[0].xpath(".//option"):
            label = (opt.text or "").strip()
            value = opt.get("value", "").strip()
            if value:
                state.categoria_label_to_id[label] = value
    return state


# ---------------------------------------------------------------------------
# Karakolas client


class KarakolasClient:
    def __init__(self, base_url: str, group_id: str):
        self.base_url = base_url.rstrip("/")
        self.group_id = group_id
        self.session = ccr.Session(impersonate="chrome")

    def _xhr(self, **kwargs) -> dict[str, str]:
        h = {"X-Requested-With": "XMLHttpRequest"}
        h.update(kwargs.pop("headers", {}))
        return h

    def login(self, username: str, password: str) -> None:
        url = f"{self.base_url}/user.load/login"
        g = self.session.get(url, headers=self._xhr())
        g.raise_for_status()
        fk = re.search(r'name="_formkey"[^>]*value="([^"]+)"', g.text)
        fn = re.search(r'name="_formname"[^>]*value="([^"]+)"', g.text)
        if not fk or not fn:
            raise RuntimeError("could not locate _formkey/_formname on login page")
        post = self.session.post(
            url,
            data={
                "username": username,
                "password": password,
                "_formkey": fk.group(1),
                "_formname": fn.group(1),
                "_next": "/",
            },
            headers=self._xhr(headers={"Referer": f"{self.base_url}/user.html/login"}),
        )
        post.raise_for_status()
        if "session_id_karakolas" not in self.session.cookies.keys():
            raise RuntimeError("login failed: no session cookie issued")
        log.info("logged in as %s", username)

    def list_propios(self) -> dict[str, dict[str, str]]:
        """Return {producer_name: {'id': str, 'auth_code': str}} for own producers."""
        r = self.session.get(
            f"{self.base_url}/productores/vista_productores.load",
            params={"grupo": self.group_id},
            headers=self._xhr(),
        )
        r.raise_for_status()
        doc = html.fromstring(r.text)
        out: dict[str, dict[str, str]] = {}
        for tr in doc.xpath("//table[@id='tabla_productores']//tr[td]"):
            cells = tr.xpath("./td")
            name = (cells[0].text_content() or "").strip()
            edit_link = tr.xpath(".//a[contains(@href,'productos.html?productor=')]")
            export_link = tr.xpath(".//a[contains(@href,'exportar_productos.csv')]")
            if not edit_link:
                continue
            pid = re.search(r"productor=(\d+)", edit_link[0].get("href")).group(1)
            auth = ""
            if export_link:
                m = re.search(r"auth_code=([A-Za-z0-9]+)", export_link[0].get("href"))
                if m:
                    auth = m.group(1)
            out[name] = {"id": pid, "auth_code": auth}
        log.info("found %d propios producers in group %s", len(out), self.group_id)
        return out

    def fetch_editor(self, productor_id: str) -> EditorState:
        """Fetch editor and merge all pages into a single state.

        karakolas paginates the editor at ~20 rows/page via
        ``?page={N}&productor={P}`` links. The HTML structure (tids, hidden
        templates, categoria <select>) is identical across pages — only the
        per-row cell fields differ. We walk pages 0..K, accumulate
        ``current_rows`` (re-indexed contiguously), and keep page-0's
        non-cell fields as the baseline for the eventual POST.
        """
        page0 = self._fetch_editor_page(productor_id, 0)
        state = parse_editor(page0)

        # Discover other page indices linked from page 0.
        # The response may contain `&` or `&amp;` depending on how the
        # XHR partial was emitted — accept either.
        page_ids = sorted(
            {int(m.group(1)) for m in re.finditer(
                r"productos\.html\?page=(\d+)(?:&amp;|&)productor="
                + re.escape(productor_id),
                page0,
            )}
        )
        for pid in page_ids:
            if pid == 0:
                continue
            html_text = self._fetch_editor_page(productor_id, pid)
            extra = parse_editor(html_text)
            # Re-index appended rows so cell field names stay contiguous in the
            # diff stage. _idx is replaced when we build the POST anyway.
            for row in extra.current_rows:
                row["_idx"] = len(state.current_rows)
                state.current_rows.append(row)
        return state

    def _fetch_editor_page(self, productor_id: str, page: int) -> str:
        params = {"productor": productor_id}
        if page:
            params["page"] = str(page)
        r = self.session.get(
            f"{self.base_url}/productores/productos.load",
            params=params,
            headers=self._xhr(),
        )
        r.raise_for_status()
        return r.text

    def fetch_export_csv(self, productor_id: str, auth_code: str) -> str:
        r = self.session.get(
            f"{self.base_url}/gestion_pedidos/exportar_productos.csv",
            params={"auth_code": auth_code, "productor": productor_id},
        )
        r.raise_for_status()
        return r.text

    def post_save(
        self,
        productor_id: str,
        fields: list[tuple[str, str]],
    ) -> ccr.Response:
        url = f"{self.base_url}/productores/productos.load?productor={productor_id}"
        mp = CurlMime()
        for name, value in fields:
            mp.addpart(name=name, data=value.encode("utf-8"))
        r = self.session.post(
            url,
            multipart=mp,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.base_url}/productores/productos.html?productor={productor_id}",
            },
        )
        r.raise_for_status()
        return r


# ---------------------------------------------------------------------------
# CSV → desired rows


@dataclass
class DesiredRow:
    nombre: str
    precio_base: str
    categoria_label: str
    descripcion: str = ""
    granel: bool = False
    pesar: bool = False
    destacado: bool = False
    temporada: bool = True
    precio_final: str = ""
    precio_productor: str = ""

    @classmethod
    def from_csv(cls, raw: dict[str, str]) -> "DesiredRow":
        def get(k: str, default: str = "") -> str:
            return (raw.get(k) or default).strip()

        nombre = get("nombre")
        if not nombre:
            raise ValueError("nombre is required")
        precio_base = get("precio_base")
        if not precio_base:
            raise ValueError(f"precio_base required for {nombre!r}")
        categoria_label = get("categoria")
        if not categoria_label:
            raise ValueError(f"categoria required for {nombre!r}")
        return cls(
            nombre=nombre,
            precio_base=precio_base,
            categoria_label=categoria_label,
            descripcion=get("descripcion"),
            granel=parse_bool(get("granel"), False),
            pesar=parse_bool(get("pesar"), False),
            destacado=parse_bool(get("destacado"), False),
            temporada=parse_bool(get("temporada", "True"), True),
            precio_final=get("precio_final"),
            precio_productor=get("precio_productor"),
        )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = [row for row in reader if any((v or "").strip() for v in row.values())]
    return rows


# ---------------------------------------------------------------------------
# Diff + multipart build


@dataclass
class RowOutcome:
    productor: str
    nombre: str
    action: str  # created | updated | unchanged | deleted | skipped | error
    detail: str = ""


def _row_signature(
    desired: DesiredRow, categoria_id: str
) -> dict[str, str]:
    """Field values as they would appear in the form, for compare-to-current."""
    return {
        "nombre": desired.nombre,
        "precio_base": desired.precio_base,
        "precio_final": desired.precio_final or desired.precio_base,
        "precio_productor": desired.precio_productor or desired.precio_base,
        "descripcion": desired.descripcion,
        "categoria": categoria_id,
        "granel": "on" if desired.granel else "",
        "pesar": "on" if desired.pesar else "",
        "destacado": "on" if desired.destacado else "",
        "temporada": "on" if desired.temporada else "",
    }


def _row_eq(current: dict[str, Any], target: dict[str, str]) -> bool:
    for k, v in target.items():
        cur = (current.get(k) or "").strip()
        if cur != v.strip():
            return False
    return True


def diff_and_build(
    state: EditorState,
    desired_rows: list[DesiredRow],
) -> tuple[list[tuple[str, str]], list[RowOutcome]]:
    """
    Build the multipart field list and per-row outcomes.

    Strategy: replay every non-cell field from raw_form_fields. Replace all
    productoXpedido cell fields with our computed row set:
      - kept rows (current name still in desired) are emitted at their existing
        position with desired field values
      - new rows (desired but not current) are appended at the next free index
      - deleted rows (current but not desired) are omitted

    Field order in the multipart body does not matter to web2py.
    """
    if not state.productox_tid:
        raise RuntimeError("productoXpedido tid missing")
    pid_tid = state.productox_tid

    # Resolve categoria labels to ids up-front.
    desired_by_name: dict[str, DesiredRow] = {}
    cat_ids: dict[str, str] = {}
    outcomes: list[RowOutcome] = []
    label_map = state.categoria_label_to_id
    for d in desired_rows:
        if d.categoria_label not in label_map:
            outcomes.append(
                RowOutcome(
                    productor="",
                    nombre=d.nombre,
                    action="error",
                    detail=f"unknown categoria label: {d.categoria_label!r}",
                )
            )
            continue
        desired_by_name[d.nombre.strip()] = d
        cat_ids[d.nombre.strip()] = label_map[d.categoria_label]

    # Build kept + new emission list.
    emit: list[tuple[DesiredRow, str | None]] = []  # (desired, current_dict_or_None)
    seen_desired: set[str] = set()
    for cur in state.current_rows:
        cur_name = (cur.get("nombre") or "").strip()
        if cur_name in desired_by_name:
            d = desired_by_name[cur_name]
            sig = _row_signature(d, cat_ids[cur_name])
            outcomes.append(
                RowOutcome(
                    productor="",
                    nombre=d.nombre,
                    action="unchanged" if _row_eq(cur, sig) else "updated",
                )
            )
            emit.append((d, cur))
            seen_desired.add(cur_name)
        else:
            outcomes.append(
                RowOutcome(productor="", nombre=cur_name, action="deleted")
            )
    for name, d in desired_by_name.items():
        if name in seen_desired:
            continue
        outcomes.append(
            RowOutcome(productor="", nombre=name, action="created")
        )
        emit.append((d, None))

    # Compose form fields. Start from raw_form_fields but DROP all cell fields
    # for productoXpedido — we will rewrite them from `emit`.
    cell_re = re.compile(rf"^ertable_{re.escape(pid_tid)}_cell_")
    fields: list[tuple[str, str]] = []
    for k, v in state.raw_form_fields.items():
        if cell_re.match(k):
            continue
        if k in ("submit", "submit_and_go"):
            continue  # we re-emit below
        fields.append((k, v))

    # Update _ultima_fila for productoXpedido. Empirically this is total row
    # count (highest_index + 1), not max-index — server only iterates rows
    # 0..N-1 where N == _ultima_fila.
    new_count = len(emit)
    fields = [
        (k, str(new_count) if k == f"_ultima_fila_{pid_tid}" else v)
        for k, v in fields
    ]

    # Emit cell fields per row.
    for i, (d, _cur) in enumerate(emit):
        sig = _row_signature(d, cat_ids[d.nombre.strip()])
        for fname in PRODUCT_FIELDS:
            v = sig[fname]
            if fname in BOOL_FIELDS and v != "on":
                # omit unchecked checkboxes entirely
                continue
            fields.append((f"ertable_{pid_tid}_cell_{fname}_{i}", v))

    # Click "Grabar los cambios" (submit, not submit_and_go).
    fields.append(("submit", "Grabar los cambios"))
    return fields, outcomes


# ---------------------------------------------------------------------------
# CLI / orchestration


def setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--csv", required=True, type=Path, help="input CSV path")
    p.add_argument(
        "--env",
        type=Path,
        default=DEFAULT_ENV,
        help="path to .env (default: project root .env)",
    )
    p.add_argument(
        "--producer",
        action="append",
        default=[],
        help="only process this producer name (repeatable)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="parse + diff but do not POST",
    )
    p.add_argument(
        "--log",
        type=Path,
        default=None,
        help="log file path (default: logs/upload-YYYYMMDD-HHMMSS.log)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = args.log or DEFAULT_LOG_DIR / f"upload-{ts}.log"
    setup_logging(log_path)

    env = {**load_env(args.env), **os.environ}
    base_url = env.get("KARAKOLAS_URL")
    user = env.get("KARAKOLAS_USER")
    password = env.get("KARAKOLAS_PASS")
    group_id = env.get("KARAKOLAS_GROUP_ID") or env.get("KARAKOLAS_GROUP")
    log.info("base_url = %s" % base_url)
    log.info("user = %s" % user)
    log.info("group_id = %s" % group_id)
    missing = [
        k
        for k, v in {
            "KARAKOLAS_URL": base_url,
            "KARAKOLAS_USER": user,
            "KARAKOLAS_PASS": password,
            "KARAKOLAS_GROUP_ID": group_id,
        }.items()
        if not v
    ]
    if missing:
        log.error("missing required env vars: %s", ", ".join(missing))
        return 2

    rows = read_csv(args.csv)
    if not rows:
        log.error("no data rows in %s", args.csv)
        return 2

    # Group desired rows by producer.
    by_producer: dict[str, list[DesiredRow]] = {}
    producer_id_hint: dict[str, str] = {}
    parse_errors: list[RowOutcome] = []
    for raw in rows:
        producer = (raw.get("productor") or "").strip()
        if not producer:
            parse_errors.append(
                RowOutcome(
                    productor="",
                    nombre=(raw.get("nombre") or "").strip(),
                    action="error",
                    detail="empty productor",
                )
            )
            continue
        if args.producer and producer not in args.producer:
            continue
        try:
            d = DesiredRow.from_csv(raw)
        except ValueError as exc:
            parse_errors.append(
                RowOutcome(
                    productor=producer,
                    nombre=(raw.get("nombre") or "").strip(),
                    action="error",
                    detail=str(exc),
                )
            )
            continue
        by_producer.setdefault(producer, []).append(d)
        pid = (raw.get("productor_id") or "").strip()
        if pid:
            producer_id_hint.setdefault(producer, pid)

    if not by_producer:
        log.error("no rows to process after filtering")
        for o in parse_errors:
            log.error("  %s: %s", o.nombre, o.detail)
        return 2

    client = KarakolasClient(base_url, group_id)
    client.login(user, password)
    propios = client.list_propios()

    all_outcomes: list[RowOutcome] = list(parse_errors)
    for producer, desired in by_producer.items():
        if producer not in propios:
            for d in desired:
                all_outcomes.append(
                    RowOutcome(
                        productor=producer,
                        nombre=d.nombre,
                        action="skipped",
                        detail=f"producer {producer!r} not found among propios for group {group_id}",
                    )
                )
            log.warning("skip producer %r: not a propio of group %s", producer, group_id)
            continue
        pid = propios[producer]["id"]
        if producer in producer_id_hint and producer_id_hint[producer] != pid:
            for d in desired:
                all_outcomes.append(
                    RowOutcome(
                        productor=producer,
                        nombre=d.nombre,
                        action="skipped",
                        detail=(
                            f"productor_id mismatch: csv={producer_id_hint[producer]} "
                            f"resolved={pid}"
                        ),
                    )
                )
            log.error(
                "skip producer %r: csv productor_id %s != resolved %s",
                producer,
                producer_id_hint[producer],
                pid,
            )
            continue

        log.info("processing producer %r (id=%s) with %d rows", producer, pid, len(desired))
        state = client.fetch_editor(pid)
        fields, outcomes = diff_and_build(state, desired)
        for o in outcomes:
            o.productor = producer
            log.info("  %-9s %s%s", o.action, o.nombre, f"  -- {o.detail}" if o.detail else "")
            all_outcomes.append(o)

        non_op = all(o.action in ("unchanged", "error") for o in outcomes)
        if args.dry_run:
            log.info("  [dry-run] would POST %d fields", len(fields))
        elif non_op:
            log.info("  no changes — skipping POST")
        else:
            client.post_save(pid, fields)
            # Verify by re-fetching and re-parsing.
            new_state = client.fetch_editor(pid)
            verify_outcomes = _verify(new_state, desired)
            for o in verify_outcomes:
                o.productor = producer
                if o.action == "error":
                    log.error("  verify FAIL %s: %s", o.nombre, o.detail)
                    all_outcomes.append(o)

    # Summary.
    counts: dict[str, int] = {}
    for o in all_outcomes:
        counts[o.action] = counts.get(o.action, 0) + 1
    log.info("done: %s", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    log.info("log file: %s", log_path)
    return 0 if counts.get("error", 0) == 0 else 1


def _verify(state: EditorState, desired_rows: list[DesiredRow]) -> list[RowOutcome]:
    """After POST, confirm each desired row exists with matching fields."""
    out: list[RowOutcome] = []
    by_name = {(r.get("nombre") or "").strip(): r for r in state.current_rows}
    for d in desired_rows:
        cur = by_name.get(d.nombre.strip())
        if not cur:
            out.append(
                RowOutcome(productor="", nombre=d.nombre, action="error", detail="missing after save")
            )
            continue
        cat_id = state.categoria_label_to_id.get(d.categoria_label, "")
        sig = _row_signature(d, cat_id)
        if not _row_eq(cur, sig):
            diffs = {
                k: (cur.get(k, ""), sig[k])
                for k in sig
                if (cur.get(k, "") or "").strip() != sig[k].strip()
            }
            out.append(
                RowOutcome(
                    productor="",
                    nombre=d.nombre,
                    action="error",
                    detail=f"field mismatch after save: {diffs}",
                )
            )
    return out


if __name__ == "__main__":
    raise SystemExit(main())
