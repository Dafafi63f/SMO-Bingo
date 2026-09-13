"""Genera Catalog/zonas_revision.json — cola de revisión por 3 ejes.

Cada ítem aparece a la vez en 3 grupos (kind=kingdom|zone|source), todos en
un solo ``groups[]``. kind=zone no lleva kingdom (el slug de zone basta).

Ítems: id (= reino/source/nº) + name + status [+ method/zone/…] sin repetir
kingdom/source. Orden de ítems = el de build_zonas_reino() (moons → goal_lists
alfa + binoculars), no alfabético por id.

Cada ítem lleva ``status``: ``ok`` | ``pendiente``.
Un grupo solo se escribe si tiene ≥1 pendiente.
File sin grupos = todo revisado.

Preserva status al regenerar (por id). Migra ok[] / by_* legados → status=ok.

Uso:
  python Files/export_zona_revision.py
"""
from __future__ import annotations

import json
from collections import defaultdict

from catalog_lib import CATALOG_DIR, load_catalog, write_catalog_json
from export_zonas_reino import (
    BINOCULARS_SOURCE,
    MOON_SOURCE,
    _MOON_ZONE_FALLBACK,
    _TAG_ZONE_ALIAS,
    _build_moon_ref_zones,
    _item_display_name,
    _inventario_zone_label,
    _kingdom_from_lunas_row,
    build_zonas_reino,
    infer_moon_zone,
    load_sub_area_levels,
)
from goal_list_lib import load_goal_lists, load_zonas_zone_index

OUT_PATH = CATALOG_DIR / "zonas_revision.json"

STATUS_OK = "ok"
STATUS_PENDIENTE = "pendiente"

_LISTA_ALWAYS_REVIEW = frozenset(
    {
        "regionals",
        "checkpoints",
        "jaxi_stands",
        "levers",
        "ground_pound_switches",
        "p_switches",
        "sphynxes",
    }
)
_LISTA_HINT_ART = frozenset(
    {"pixel_luigis", "pixel_cat_marios", "pixel_cat_peaches"}
)
_LISTA_MERCH = frozenset(
    {"costume_sets", "hats", "souvenirs", "stickers", "boxer_shorts"}
)


def _kingdom_zones_from_map(
    zone_map: dict[tuple[str, str, str], str],
) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for kingdom, _source, _name in zone_map:
        z = zone_map[(kingdom, _source, _name)]
        if z:
            out[kingdom].add(z)
    return out


def _moon_method(
    *,
    kingdom: str,
    moon: int,
    name: str,
    tags: list[str],
    zone_actual: str | None,
    zone_infer: str | None,
    moon_refs: dict[tuple[str, int], list[tuple[str, str]]],
    kingdom_zones: dict[str, set[str]],
) -> tuple[str, str | None]:
    refs = moon_refs.get((kingdom, moon)) or []
    if not zone_actual:
        return "sin_zone", None

    if refs:
        sub = [z for src, z in refs if src == "sub_area_levels"]
        uniq = list(dict.fromkeys(z for _s, z in refs))
        if len(set(sub)) == 1 and zone_actual == sub[0]:
            return "listas_sub_area", None
        if len(uniq) == 1 and zone_actual == uniq[0]:
            return "listas_unica", None
        if len(uniq) > 1:
            return "listas_varias", f"refs ambiguas: {uniq}"

    tag_set = {str(t) for t in tags[1:]} if tags else set()
    k_zones = kingdom_zones.get(kingdom) or set()
    tag_hits = list(
        dict.fromkeys(
            _TAG_ZONE_ALIAS.get(t, t)
            for t in tag_set
            if _TAG_ZONE_ALIAS.get(t, t) in k_zones
        )
    )
    if len(tag_hits) == 1 and zone_actual == tag_hits[0]:
        return "tag_unico", f"tag={tag_hits[0]}"
    if len(tag_hits) > 1:
        return "tag_varios", f"tags→zones {tag_hits}"

    if "shop" in tag_set:
        return "heuristic_shop", None
    if "captain_toad" in tag_set:
        return "heuristic_toad", None
    nl = name.lower()
    if "talkatoo" in nl:
        return "heuristic_talkatoo", None
    if "found with" in nl and "art" in nl:
        return "heuristic_art", None
    if "moon rock" in nl:
        return "heuristic_moon_rock", None

    fb = _MOON_ZONE_FALLBACK.get((kingdom, moon))
    if fb and zone_actual == fb:
        return "fallback_curado", None
    if kingdom == "ruined" and zone_actual == "odyssey":
        return "ruined_default", None

    if zone_infer and zone_actual and zone_infer != zone_actual:
        return (
            "distinto_curado",
            f"inferido={zone_infer} curado={zone_actual}",
        )
    if zone_infer and zone_actual == zone_infer:
        return "curado", None
    return "fallback_curado", None


def _lista_method(
    *,
    list_name: str,
    zone_actual: str | None,
    shop_zone: str | None,
    raw: dict | None,
) -> tuple[str, str | None]:
    if not zone_actual:
        return "sin_zone", None
    if list_name == "regionals":
        if raw and raw.get("sub_area") is True:
            return "lista_sub_area_regional", None
        return "lista_regional", None
    if list_name == "checkpoints":
        return "lista_checkpoint", None
    if list_name in _LISTA_HINT_ART:
        return "lista_hint_art", None
    if list_name == "shops":
        return "lista_tienda", None
    if list_name == "talkatoos":
        return "lista_talkatoo", None
    if list_name == "moon_rocks":
        return "lista_moon_rock", None
    if list_name in _LISTA_MERCH:
        if shop_zone and zone_actual == shop_zone:
            return "lista_merch_tienda", None
        if shop_zone and zone_actual != shop_zone:
            return "lista_tienda_distinto", f"merch en tienda → {shop_zone}"
        return "lista_merch_tienda", None
    if list_name in _LISTA_ALWAYS_REVIEW:
        return "lista_poi", None
    return "lista_curada", None


def _item_row_id(kingdom: str, item: dict) -> str:
    src = str(item.get("source") or "")
    if src == MOON_SOURCE:
        return f"{kingdom}/moon/{item.get('id_kingdom')}"
    return f"{kingdom}/{src}/{item.get('id_kingdom')}"


def _load_status_by_id() -> dict[str, str]:
    """id → status desde groups[] / ejes legados / ok[]."""
    if not OUT_PATH.is_file():
        return {}
    data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    out: dict[str, str] = {}

    def _ingest_rows(rows: list) -> None:
        for row in rows or []:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            st = str(row.get("status") or STATUS_PENDIENTE)
            if st not in (STATUS_OK, STATUS_PENDIENTE):
                st = STATUS_PENDIENTE
            rid = str(row["id"])
            if out.get(rid) == STATUS_OK:
                continue
            out[rid] = st

    for group in data.get("groups") or []:
        if isinstance(group, dict):
            _ingest_rows(group.get("items") or [])
    for axis in ("by_kingdom", "by_zone", "by_source"):
        for group in data.get(axis) or []:
            if isinstance(group, dict):
                _ingest_rows(group.get("items") or [])
    _ingest_rows(data.get("ok") or [])
    return out


def _compact_item(
    *,
    row_id: str,
    name: str,
    kingdom: str,
    source: str,
    zone: str | None,
    zone_label: str,
    status: str,
    method: str,
    detail: str | None,
    zone_sugerida: str | None,
) -> dict:
    """Fila interna: id ya lleva kingdom/source/nº; kingdom/source solo internos."""
    row: dict = {
        "id": row_id,
        "name": name,
        "status": status,
        "method": method,
        "_kingdom": kingdom,
        "_source": source,
        "_zone_key": zone_label if zone else "sin_zone",
    }
    if zone:
        row["zone"] = zone
    if zone_sugerida and zone_sugerida != zone:
        row["zone_sugerida"] = zone_sugerida
    if detail:
        row["detail"] = detail
    return row


def _public_item(row: dict, *, kind: str) -> dict:
    """Campos públicos: sin kingdom/source (van en id); zone solo fuera de kind=zone."""
    out: dict = {
        "id": row["id"],
        "name": row["name"],
        "status": row["status"],
        "method": row["method"],
    }
    if kind != "zone" and row.get("zone"):
        out["zone"] = row["zone"]
    if row.get("zone_sugerida"):
        out["zone_sugerida"] = row["zone_sugerida"]
    if row.get("detail"):
        out["detail"] = row["detail"]
    return out


def _make_group(
    *,
    kind: str,
    kingdom: str = "",
    zone: str = "",
    source: str = "",
    rows_raw: list[dict],
) -> dict | None:
    n_ok = sum(1 for r in rows_raw if r.get("status") == STATUS_OK)
    n_pend = len(rows_raw) - n_ok
    if n_pend <= 0:
        return None
    # Orden de aparición (= moons → lists → binoculars); no reordenar alfa.
    rows = [_public_item(r, kind=kind) for r in rows_raw]
    group: dict = {"kind": kind}
    if kind == "kingdom" and kingdom:
        group["kingdom"] = kingdom
    elif kind == "zone" and zone:
        group["zone"] = zone
    elif kind == "source" and source:
        group["source"] = source
    group["n"] = len(rows)
    group["n_ok"] = n_ok
    group["n_pendiente"] = n_pend
    group["items"] = rows
    return group


def _group_sort_key(group: dict) -> tuple:
    """Alfa por el nombre del eje (kingdom|zone|source)."""
    kind = str(group.get("kind") or "")
    if kind == "zone":
        primary = str(group.get("zone") or "")
    elif kind == "source":
        primary = str(group.get("source") or "")
    else:
        primary = str(group.get("kingdom") or "")
    return (primary.casefold(), kind.casefold())


def _build_unified_groups(items: list[dict]) -> list[dict]:
    by_kingdom: dict[str, list[dict]] = defaultdict(list)
    by_zone: dict[str, list[dict]] = defaultdict(list)
    by_source: dict[str, list[dict]] = defaultdict(list)

    for it in items:
        k = str(it["_kingdom"])
        src = str(it["_source"])
        zlabel = str(it.get("_zone_key") or "sin_zone")
        by_kingdom[k].append(it)
        by_zone[zlabel].append(it)
        by_source[src].append(it)

    groups: list[dict] = []
    for k, rows in by_kingdom.items():
        g = _make_group(kind="kingdom", kingdom=k, rows_raw=rows)
        if g:
            groups.append(g)
    for zlabel, rows in by_zone.items():
        g = _make_group(kind="zone", zone=zlabel, rows_raw=rows)
        if g:
            groups.append(g)
    for src, rows in by_source.items():
        g = _make_group(kind="source", source=src, rows_raw=rows)
        if g:
            groups.append(g)

    groups.sort(key=_group_sort_key)
    return groups


def build_zona_revision() -> dict:
    zone_map = load_zonas_zone_index()
    payload = build_zonas_reino(zone_map=zone_map)
    data = load_goal_lists()
    lists = data.get("lists") or {}

    lists_for_moon_refs = {**lists, "sub_area_levels": load_sub_area_levels()}
    moon_refs = _build_moon_ref_zones(lists_for_moon_refs, zone_map)
    k_zones = _kingdom_zones_from_map(zone_map)

    lunas_by_key: dict[tuple[str, int], dict] = {}
    for raw in load_catalog(CATALOG_DIR / "lunas-objetivos.json").get("moons") or []:
        kingdom = _kingdom_from_lunas_row(raw)
        if kingdom and raw.get("moon") is not None:
            lunas_by_key[(kingdom, int(raw["moon"]))] = raw

    goal_raw_by_key: dict[tuple[str, str, str], dict] = {}
    for list_name, rows in lists.items():
        for raw in rows or []:
            if not isinstance(raw, dict):
                continue
            kingdom_raw = str(raw.get("kingdom") or "")
            nm = _item_display_name(raw)
            if kingdom_raw and nm:
                goal_raw_by_key[(kingdom_raw, str(list_name), nm)] = raw

    shop_zone_by_kingdom: dict[str, str] = {}
    for (k, src, _n), z in zone_map.items():
        if src == "shops" and z and k not in shop_zone_by_kingdom:
            shop_zone_by_kingdom[k] = z

    zone_kingdoms: dict[str, set[str]] = defaultdict(set)
    flat_rows: list[tuple[str, dict]] = []
    for block in payload.get("kingdoms") or []:
        kdom = str(block.get("kingdom") or "")
        for it in block.get("list") or []:
            if not isinstance(it, dict):
                continue
            flat_rows.append((kdom, it))
            z = it.get("zone")
            if z:
                zone_kingdoms[str(z)].add(kdom)

    status_by_id = _load_status_by_id()
    items: list[dict] = []
    by_method: dict[str, int] = defaultdict(int)

    for kingdom, item in flat_rows:
        source = str(item.get("source") or "")
        name = str(item.get("name") or "")
        zone = str(item["zone"]) if item.get("zone") else None
        row_id = _item_row_id(kingdom, item)
        detail: str | None = None
        zone_sugerida: str | None = None

        if source == MOON_SOURCE:
            moon_num = int(item.get("id_kingdom") or 0)
            raw = lunas_by_key.get((kingdom, moon_num), {})
            tags = list(raw.get("tags") or [])
            zone_infer = infer_moon_zone(
                kingdom=kingdom,
                moon=moon_num,
                name=name,
                tags=tags,
                lists=lists_for_moon_refs,
                zone_map=zone_map,
                moon_refs=moon_refs,
                kingdom_zones=k_zones,
            )
            method, detail = _moon_method(
                kingdom=kingdom,
                moon=moon_num,
                name=name,
                tags=tags,
                zone_actual=zone,
                zone_infer=zone_infer,
                moon_refs=moon_refs,
                kingdom_zones=k_zones,
            )
            if zone_infer and zone_infer != zone:
                zone_sugerida = zone_infer
        elif source == BINOCULARS_SOURCE:
            method = "sin_zone"
        else:
            raw_gl = goal_raw_by_key.get((kingdom, source, name))
            method, detail = _lista_method(
                list_name=source,
                zone_actual=zone,
                shop_zone=shop_zone_by_kingdom.get(kingdom),
                raw=raw_gl,
            )

        shared = len(zone_kingdoms.get(zone or "", ())) > 1
        zone_label = (
            _inventario_zone_label(kingdom, zone, shared=shared)
            if zone
            else "sin_zone"
        )
        status = status_by_id.get(row_id, STATUS_PENDIENTE)
        row = _compact_item(
            row_id=row_id,
            name=name,
            kingdom=kingdom,
            source=source,
            zone=zone,
            zone_label=zone_label,
            status=status,
            method=method,
            detail=detail,
            zone_sugerida=zone_sugerida,
        )
        items.append(row)
        by_method[method] += 1

    groups = _build_unified_groups(items)
    n_ok = sum(1 for r in items if r["status"] == STATUS_OK)
    n_pendiente = len(items) - n_ok

    return {
        "_definition": (
            "Cola de revisión de zones. groups[] mezcla kind=kingdom|zone|source "
            "(cada ítem en 3 grupos). kind=zone no incluye kingdom. Ítems: id "
            "(reino/source/nº) + name + status + method; zone solo en grupos "
            "kingdom/source. Orden de ítems = moons → goal_lists + binoculars "
            "(mismo que zonas_inventario). status=ok|pendiente; un grupo "
            "desaparece cuando todos sus ítems están ok. File sin grupos = todo "
            "revisado. Curar zone en zonas_inventario y marcar status=ok aquí. "
            "Zone compartida → slug reino_zona."
        ),
        "_note": "Regenerar: python Files/export_zona_revision.py",
        "n_total_items": len(items),
        "n_ok": n_ok,
        "n_pendiente": n_pendiente,
        "n_groups": len(groups),
        "by_method": dict(sorted(by_method.items())),
        "groups": groups,
    }


def main() -> None:
    payload = build_zona_revision()
    write_catalog_json(OUT_PATH, payload)
    print(f"Exportado: {OUT_PATH.relative_to(CATALOG_DIR.parent).as_posix()}")
    print(
        f"  ok={payload['n_ok']}  pendiente={payload['n_pendiente']}  "
        f"total={payload['n_total_items']}  groups={payload['n_groups']}"
    )
    for method, n in payload.get("by_method", {}).items():
        print(f"    {method}: {n}")


if __name__ == "__main__":
    main()
