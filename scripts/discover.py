#!/usr/bin/env python3
"""
discover.py — probe karakolas.net and emit a spec describing the wire shape.

Run on demand (NOT every pipeline run). Produces ``docs/karakolas-spec.json``
which captures the moving parts ``upload.py`` cares about: endpoints, form
fields, categoria id↔label map, app version, sample producers. On re-run, diffs
against the previous spec and reports drift in human-readable form.

Uses Scrapling's adaptive selectors (`find_similar`, `find_by_text`,
`find_by_regex`) so cosmetic UI changes (renamed CSS classes, restructured
DOM) don't silently break discovery. Compare with ``upload.py`` which uses
plain lxml because the wire protocol it touches is machine-stable.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from curl_cffi import requests as ccr
from scrapling.parser import Adaptor


def s(x: Any) -> str:
    """Coerce Scrapling TextHandler / None / anything → plain str.

    Scrapling returns TextHandler objects from .text and .attrib accessors;
    these compare not-equal to plain str when reloaded from JSON, breaking the
    drift diff. Always pass scraped strings through this before storing.
    """
    if x is None:
        return ""
    return str(x)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV = PROJECT_ROOT / ".env"
DEFAULT_SPEC = PROJECT_ROOT / "docs" / "karakolas-spec.json"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"

log = logging.getLogger("discover")


# ---------------------------------------------------------------------------
# env loader (kept local — discover.py is a standalone tool)


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# ---------------------------------------------------------------------------
# HTTP session (web2py auth needs cookies, curl_cffi handles them best)


class Session:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.s = ccr.Session(impersonate="chrome")

    def login(self, username: str, password: str) -> None:
        url = f"{self.base_url}/user.load/login"
        g = self.s.get(url, headers={"X-Requested-With": "XMLHttpRequest"})
        g.raise_for_status()
        # Adaptive: locate hidden form keys by name attr (web2py convention).
        a = Adaptor(g.text, url=url)
        fk = a.css('input[name="_formkey"]::attr(value)').extract_first()
        fn = a.css('input[name="_formname"]::attr(value)').extract_first()
        if not fk or not fn:
            raise RuntimeError("login form missing _formkey/_formname")
        self.s.post(
            url,
            data={
                "username": username,
                "password": password,
                "_formkey": fk,
                "_formname": fn,
                "_next": "/",
            },
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.base_url}/user.html/login",
            },
        )
        if "session_id_karakolas" not in self.s.cookies.keys():
            raise RuntimeError("login failed: no session cookie")
        log.info("logged in as %s", username)

    def adapt(self, path: str, params: dict | None = None) -> Adaptor:
        """GET an XHR partial and wrap it in a Scrapling Adaptor."""
        url = f"{self.base_url}{path}"
        r = self.s.get(
            url,
            params=params,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        r.raise_for_status()
        return Adaptor(r.text, url=url)

    def get_text(self, path: str, params: dict | None = None) -> str:
        url = f"{self.base_url}{path}"
        r = self.s.get(
            url,
            params=params,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        r.raise_for_status()
        return r.text


# ---------------------------------------------------------------------------
# Probes


def probe_version(sess: Session) -> dict[str, Any]:
    """Read /default/version.json — reveals frontend asset version path."""
    txt = sess.get_text("/default/version.json")
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        log.warning("version.json not parseable: %r", txt[:200])
        return {"raw": txt}


def probe_groups(sess: Session) -> list[dict[str, str]]:
    """Parse menu.load → list of (label, group_id).

    Adaptive strategy: walk top-level dropdowns, take labels that aren't system
    (Usuaria/Home/Ayuda/Admin <name>), pull their child links' grupo= param.
    """
    a = sess.adapt("/karakolas/default/menu.load")
    groups: dict[str, str] = {}
    skip = {"Usuaria", "Home", "Ayuda"}
    for li in a.css("li.dropdown"):
        links = li.css("a")
        if not links:
            continue
        label = s(links[0].text).strip()
        if label in skip or label.startswith("Admin "):
            continue
        for child in li.css("ul.dropdown-menu a"):
            href = s(child.attrib.get("href"))
            m = re.search(r"[?&]grupo=(\d+)", href)
            if m:
                groups.setdefault(label, m.group(1))
                break
    return [{"name": n, "grupo_id": gid} for n, gid in groups.items()]


def probe_propios(sess: Session, grupo: str) -> list[dict[str, str]]:
    """Parse vista_productores.load using adaptive selectors.

    Resilient to id rename: if `#tabla_productores` disappears, fall back to
    Scrapling's `find_similar` from any row that has an "Editar productos"
    link.
    """
    a = sess.adapt("/productores/vista_productores.load", {"grupo": grupo})
    tables = a.css("table#tabla_productores")
    rows = []
    if tables:
        rows = tables[0].css("tr")[1:]  # skip header
    else:
        log.warning("table#tabla_productores not found — falling back to find_similar")
        anchor = a.find_by_text("Editar productos", first_match=True)
        if anchor:
            row_el = anchor.find_ancestor(lambda e: e.tag == "tr")
            if row_el:
                rows = row_el.find_similar()

    out: list[dict[str, str]] = []
    for tr in rows:
        cells = tr.css("td")
        if not cells:
            continue
        name = s(cells[0].get_all_text(strip=True))
        edit = s(tr.css('a[href*="productos.html?productor="]::attr(href)').extract_first())
        export = s(tr.css('a[href*="exportar_productos.csv"]::attr(href)').extract_first())
        pid = re.search(r"productor=(\d+)", edit)
        auth = re.search(r"auth_code=([A-Za-z0-9]+)", export)
        if not pid:
            continue
        out.append(
            {
                "name": name,
                "id": pid.group(1),
                "auth_code_sample": auth.group(1) if auth else "",
            }
        )
    return out


def probe_editor(sess: Session, productor_id: str) -> dict[str, Any]:
    """Probe /productores/productos.load?productor=P; extract structural facts.

    Captures:
      - productoXpedido tid + columns + bool fields
      - campo_extra_pedido tid (if present)
      - hidden control field NAMES (templates, formula_*, _ultima_fila, etc.)
      - submit button label
      - categoria id↔label map
      - row count of real (named) products
    """
    a = sess.adapt("/productores/productos.load", {"productor": productor_id})

    # ertable tids
    productox_tid = ""
    campo_extra_tid = ""
    for inp in a.css('input[name^="_table_name_"]'):
        tid = s(inp.attrib["name"]).removeprefix("_table_name_")
        val = s(inp.attrib.get("value"))
        if val == "productoXpedido":
            productox_tid = tid
        elif val == "campo_extra_pedido":
            campo_extra_tid = tid
    if not productox_tid:
        raise RuntimeError("productoXpedido table not found in editor")

    # row column list (from hidden _fields field)
    fields_csv = s(
        a.css(
            f'input[name="_ertable_{productox_tid}_fields"]::attr(value)'
        ).extract_first()
    )
    row_columns = [c.strip() for c in fields_csv.split(",") if c.strip()]

    # bool fields = those rendered as <input type=checkbox class=ertable_field_X>
    bool_fields: list[str] = []
    for cb in a.css(
        f'input[type="checkbox"][name^="ertable_{productox_tid}_cell_"]'
    ):
        m = re.match(
            rf"^ertable_{productox_tid}_cell_([a-z_]+)_(\d+)$",
            s(cb.attrib["name"]),
        )
        if m and m.group(1) not in bool_fields:
            bool_fields.append(m.group(1))

    # hidden control field name templates (TID stripped, for cross-render compare)
    control_field_templates: list[str] = []
    for inp in a.css('input[type="hidden"]'):
        n = s(inp.attrib.get("name"))
        if not n or "cell_" in n:
            continue
        # collapse the random TID → "{TID}" so the template is stable
        templ = re.sub(r"\d{10,}", "{TID}", n)
        if templ not in control_field_templates:
            control_field_templates.append(templ)
    control_field_templates.sort()

    # submit button label (adaptive: locate via text "Grabar")
    submit_btn = a.find_by_regex(
        r"Grabar los cambios", first_match=True, clean_match=True
    )
    submit_label = s(submit_btn.attrib.get("value")) if submit_btn else "Grabar los cambios"

    # categoria id↔label map
    categorias: dict[str, str] = {}
    sels = a.css("select.ertable_field_categoria")
    sel = sels[0] if sels else None
    if sel is None:
        # fallback: any select whose option text matches a known category-like word
        for cand in a.css("select"):
            labels = [s(o.text).strip() for o in cand.css("option")]
            if any(lab in labels for lab in ("Verduras", "Bebidas", "Frutas")):
                sel = cand
                break
    if sel is not None:
        for opt in sel.css("option"):
            label = s(opt.text).strip()
            value = s(opt.attrib.get("value")).strip()
            if label and value:
                categorias[label] = value

    # count real product rows (non-empty nombre cell)
    real_rows = 0
    for ta in a.css(f'textarea[name^="ertable_{productox_tid}_cell_nombre_"]'):
        if s(ta.text).strip():
            real_rows += 1

    return {
        "productox_tid_pattern": "ertable_{TID}_cell_{field}_{N}",
        "campo_extra_tid_present": bool(campo_extra_tid),
        "row_columns": row_columns,
        "bool_fields": bool_fields,
        "control_field_templates": control_field_templates,
        "submit_button_label": submit_label,
        "categoria_label_to_id": dict(sorted(categorias.items())),
        "sample_real_row_count": real_rows,
    }


def build_spec(sess: Session, base_url: str, group_id: str) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "discovered_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "instance": base_url,
        "group_id": group_id,
        "endpoints": {
            "login_get": "/user.load/login",
            "login_post": "/user.load/login",
            "menu": "/karakolas/default/menu.load",
            "producers_propios": "/productores/vista_productores.load?grupo={grupo}",
            "producers_coordinados": "/productores/productores_coordinados.load?grupo={grupo}",
            "products_editor_get": "/productores/productos.load?productor={productor}",
            "products_editor_post": "/productores/productos.load?productor={productor}",
            "products_export_csv": "/gestion_pedidos/exportar_productos.csv?auth_code={code}&productor={productor}",
        },
        "auth": {
            "login_required_form_fields": ["username", "password", "_formkey", "_formname"],
            "session_cookie": "session_id_karakolas",
        },
        "ultima_fila_semantics": "row_count_not_max_index",
    }

    log.info("probing version.json")
    spec["version"] = probe_version(sess)

    log.info("probing groups via menu.load")
    spec["groups"] = probe_groups(sess)

    log.info("probing propios producers for group=%s", group_id)
    propios = probe_propios(sess, group_id)
    # don't persist auth_code samples (rotates per session)
    spec["propios_producers"] = [
        {"name": p["name"], "id": p["id"]} for p in propios
    ]

    if propios:
        first = propios[0]
        log.info("probing editor for productor=%s (%s)", first["id"], first["name"])
        spec["editor"] = probe_editor(sess, first["id"])
        spec["editor"]["sample_producer"] = {"id": first["id"], "name": first["name"]}
    else:
        log.warning("no propios producers — editor probe skipped")
        spec["editor"] = {}

    return spec


# ---------------------------------------------------------------------------
# Diff


def diff_specs(prev: dict[str, Any], curr: dict[str, Any]) -> list[str]:
    """Human-readable list of changes between two specs."""
    changes: list[str] = []

    def walk(path: str, a: Any, b: Any) -> None:
        if type(a) is not type(b):
            changes.append(f"{path}: type {type(a).__name__} → {type(b).__name__}")
            return
        if isinstance(a, dict):
            for k in sorted(set(a) | set(b)):
                if k in ("discovered_at",):
                    continue
                if k not in a:
                    changes.append(f"{path}.{k}: ADDED {b[k]!r}")
                elif k not in b:
                    changes.append(f"{path}.{k}: REMOVED")
                else:
                    walk(f"{path}.{k}" if path else k, a[k], b[k])
        elif isinstance(a, list):
            if a != b:
                # short-form for lists; deep diff would be noisy
                added = [x for x in b if x not in a]
                removed = [x for x in a if x not in b]
                if added:
                    changes.append(f"{path}: ADDED {added}")
                if removed:
                    changes.append(f"{path}: REMOVED {removed}")
        else:
            if a != b:
                changes.append(f"{path}: {a!r} → {b!r}")

    walk("", prev, curr)
    return changes


# ---------------------------------------------------------------------------
# CLI


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
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_SPEC,
        help="spec output path (default: docs/karakolas-spec.json)",
    )
    p.add_argument("--log", type=Path, default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = args.log or DEFAULT_LOG_DIR / f"discover-{ts}.log"
    setup_logging(log_path)

    env = {**load_env(args.env), **os.environ}
    base = env.get("KARAKOLAS_URL")
    user = env.get("KARAKOLAS_USER")
    pw = env.get("KARAKOLAS_PASS")
    grp = env.get("KARAKOLAS_GROUP_ID") or env.get("KARAKOLAS_GROUP")
    missing = [k for k, v in {
        "KARAKOLAS_URL": base, "KARAKOLAS_USER": user,
        "KARAKOLAS_PASS": pw, "KARAKOLAS_GROUP_ID": grp,
    }.items() if not v]
    if missing:
        log.error("missing env vars: %s", ", ".join(missing))
        return 2

    sess = Session(base)
    sess.login(user, pw)
    curr = build_spec(sess, base, grp)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        try:
            prev = json.loads(args.out.read_text(encoding="utf-8"))
            changes = diff_specs(prev, curr)
            if changes:
                log.warning("DRIFT vs prior spec (%d changes):", len(changes))
                for c in changes:
                    log.warning("  %s", c)
            else:
                log.info("no drift vs prior spec")
        except json.JSONDecodeError:
            log.warning("prior spec at %s not valid JSON — overwriting", args.out)

    args.out.write_text(
        json.dumps(curr, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    log.info("wrote spec to %s", args.out)
    log.info("log file: %s", log_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
