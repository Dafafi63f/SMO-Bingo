"""Export Catalog/palabras_inventario.json — slugs y sus usos en el proyecto.

Inventario alfabético de palabras (slugs) canónicas y sus usos:
  bingo (categoría board/line), grupo, tag, lista, captura, zona,
  goal (tags[] de goals_referencia), luna (tag en lunas-objetivos).

Alias duplicados (captaintoad/captain_toad, cascade_chain_chomp/chain_chomp,
etc.) se unifican vía catalog_lib.canonicalize_palabra.

Uso:
  python Files/export_palabras_inventario.py
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from catalog_lib import (
    CATALOG_DIR,
    KINGDOM_COLUMNS,
    TAG_KINGDOM,
    _resolve_bingo_group_moons_raw,
    canonicalize_palabra,
    canonicalize_tag,
    group_lista,
    load_bingo_groups,
    load_catalog,
    write_catalog_json,
)

OUT_JSON = CATALOG_DIR / "palabras_inventario.json"

_FN_BINGO_LINEAS = "bingo_lineas.json"
_FN_GOAL_LISTS = "goal_lists.json"
_FN_ZONAS_INVENTARIO = "zonas_inventario.json"
_FN_CAPTURAS_LUNAS = "capturas_lunas.json"

USO_ORDER = (
    "bingo",
    "captura",
    "goal",
    "grupo",
    "lista",
    "luna",
    "tag",
    "zona",
)

USO_FIJO = ("grupo", "zona")
USO_VARIABLE = ("bingo", "captura", "goal", "luna", "lista", "tag")
USO_IDENTITY = ("bingo", "captura", "grupo", "lista", "tag", "zona")
USO_FIJO_ZERO = ()
USO_FIJO_WORD_COUNT = ("grupo", "zona")
USO_SUM = ("bingo", "captura", "goal", "luna", "tag")

# Presencia del uso: conjunto fijo de palabras vs variable según catálogo.
# uso_fijo (valor n=1) + uso_palabra_fija cubren uso_order salvo goal/luna.
USO_PALABRA_FIJA = ("bingo", "captura", "grupo", "lista", "tag", "zona")
USO_PALABRA_VARIABLE = ("goal", "luna")
# Matriz presencia × valor (valor fijo = n=1 en cada palabra que lo tiene).
USO_PALABRA_FIJA_VALOR_FIJO = USO_FIJO
USO_PALABRA_FIJA_VALOR_VARIABLE = ("bingo", "captura", "lista", "tag")
USO_PALABRA_VARIABLE_VALOR_FIJO: tuple[str, ...] = ()
USO_PALABRA_VARIABLE_VALOR_VARIABLE = USO_PALABRA_VARIABLE

CAPTURA_GRUPO_ID = "captures"


def _build_bingo_individual_counts() -> dict[str, int]:
    """Categoría bingo_lineas (id canónico) → n_goals de esa board/line."""
    out: dict[str, int] = {}
    lineas_path = CATALOG_DIR / _FN_BINGO_LINEAS
    if not lineas_path.is_file():
        return out
    for group in load_catalog(lineas_path).get("groups") or []:
        if not isinstance(group, dict):
            continue
        canon = _canon(group.get("id"), "bingo") or _slug(group.get("id"))
        if not canon:
            continue
        n_goals = int(group.get("n_goals") or 0)
        if n_goals <= 0:
            n_goals = len(
                [
                    o
                    for o in group.get("objectives") or []
                    if isinstance(o, dict) and not o.get("disabled")
                ]
            )
        out[canon] = n_goals
    return out


def _group_n(group: dict) -> dict:
    """Cabecera ``n`` del grupo; vacío si falta o no es dict."""
    n_raw = group.get("n")
    return n_raw if isinstance(n_raw, dict) else {}


def _grupo_has_lista_pool(group: dict) -> bool:
    """Pool lista curado (goal_lists), no ítems sueltos de goals."""
    n = _group_n(group)
    if int(n.get("lista") or 0) > 0:
        return True
    return bool(group_lista(group))


def _grupo_item_counts_for_group(group: dict) -> tuple[str, dict[str, int]] | None:
    word = _canon(group.get("id"), "grupo") or _slug(group.get("id"))
    if not word:
        return None
    n = _group_n(group)
    n_goal = int(n.get("objectives") or 0)
    if n_goal <= 0:
        n_goal = len(group.get("objectives") or [])
    n_luna = int(n.get("moons") or 0)
    if n_luna <= 0:
        n_luna = len(group.get("moons") or [])
    n_lista = int(n.get("lista") or 0)
    if n_lista <= 0 and _grupo_has_lista_pool(group):
        n_lista = len(group.get("lista") or [])
    return word, {"goal": n_goal, "luna": n_luna, "lista": n_lista}


def _merge_grupo_item_counts(
    out: dict[str, dict[str, int]], word: str, counts: dict[str, int]
) -> None:
    prev = out.get(word) or {"goal": 0, "luna": 0, "lista": 0}
    out[word] = {
        "goal": max(prev["goal"], counts["goal"]),
        "luna": max(prev["luna"], counts["luna"]),
        "lista": max(prev["lista"], counts["lista"]),
    }


def _build_grupo_item_counts() -> dict[str, dict[str, int]]:
    """Id de grupo → {goal, luna, lista} = n.objectives / n.moons / n.lista."""
    out: dict[str, dict[str, int]] = {}
    for group in load_bingo_groups():
        if not isinstance(group, dict):
            continue
        parsed = _grupo_item_counts_for_group(group)
        if parsed:
            _merge_grupo_item_counts(out, parsed[0], parsed[1])
    return out


def _build_goal_list_counts() -> dict[str, int]:
    """Clave canónica de goal_lists → n ítems en lists[name]."""
    out: dict[str, int] = {}
    path = CATALOG_DIR / _FN_GOAL_LISTS
    if not path.is_file():
        return out
    lists = load_catalog(path).get("lists") or {}
    if not isinstance(lists, dict):
        return out
    for name, items in lists.items():
        if not isinstance(items, list):
            continue
        word = _canon(name, "lista") or _slug(name)
        if word:
            out[word] = out.get(word, 0) + len(items)
    return out


def _kingdom_items_from_zone_block(block: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    default_k = str(block.get("kingdom") or "")
    for it in block.get("list") or []:
        if not isinstance(it, dict):
            continue
        kingdom = str(it.get("kingdom") or default_k)
        if not kingdom or str(it.get("source") or "") == "moon":
            continue
        counts[kingdom] = counts.get(kingdom, 0) + 1
    return counts


def _build_kingdom_n_items() -> dict[str, int]:
    """Reino → n_items de zonas_inventario (= goal_lists + binoculars por kingdom)."""
    out: dict[str, int] = {}
    path = CATALOG_DIR / _FN_ZONAS_INVENTARIO
    if not path.is_file():
        return out
    data = load_catalog(path)
    for block in data.get("zones") or []:
        if not isinstance(block, dict):
            continue
        for kingdom, n in _kingdom_items_from_zone_block(block).items():
            out[kingdom] = out.get(kingdom, 0) + n
    return out


def _build_capture_lista_counts() -> dict[str, int]:
    """Capturas con lista[] (p. ej. Binoculars) → n ubicaciones."""
    out: dict[str, int] = {}
    caps_path = CATALOG_DIR / _FN_CAPTURAS_LUNAS
    if not caps_path.is_file():
        return out
    for row in load_catalog(caps_path).get("captures") or []:
        if not isinstance(row, dict):
            continue
        word = _capture_row_palabra(row)
        if not word:
            continue
        n_lista = int(row.get("n_lista") or 0)
        if n_lista <= 0:
            n_lista = len(row.get("lista") or [])
        if n_lista > 0:
            out[word] = n_lista
    return out


def _build_grupo_lista_computed_counts() -> dict[str, int]:
    """n.lista efectivo cuando bingo_groups omite lista[] (goals_only)."""
    from goal_list_lib import build_bingo_group_lista

    out: dict[str, int] = {}
    for group in load_bingo_groups():
        if not isinstance(group, dict):
            continue
        word = _canon(group.get("id"), "grupo") or _slug(group.get("id"))
        if not word:
            continue
        lista, _ = build_bingo_group_lista(group)
        if lista:
            out[word] = len(lista)
    return out


def _resolve_lista_n_from_grupo(
    word: str,
    *,
    grupo_counts: dict[str, dict[str, int]],
    goal_list_counts: dict[str, int],
    capture_lista_counts: dict[str, int],
    grupo_lista_computed: dict[str, int] | None,
) -> int:
    n = int((grupo_counts.get(word) or {}).get("lista") or 0)
    if n <= 0 and grupo_lista_computed:
        n = int(grupo_lista_computed.get(word) or 0)
    if n <= 0:
        n = int(goal_list_counts.get(word) or 0)
    if n <= 0 and word in capture_lista_counts:
        n = int(capture_lista_counts.get(word) or 0)
    return n


def _resolve_lista_n(
    word: str,
    usos: set[str],
    *,
    grupo_counts: dict[str, dict[str, int]],
    goal_list_counts: dict[str, int],
    capture_lista_counts: dict[str, int],
    grupo_lista_computed: dict[str, int] | None = None,
) -> int:
    """Lista: grupo → n.lista (o pool); si 0, capturas.lista[] o goal_lists."""
    if "grupo" in usos:
        return _resolve_lista_n_from_grupo(
            word,
            grupo_counts=grupo_counts,
            goal_list_counts=goal_list_counts,
            capture_lista_counts=capture_lista_counts,
            grupo_lista_computed=grupo_lista_computed,
        )
    if word in capture_lista_counts:
        return int(capture_lista_counts.get(word) or 0)
    return int(goal_list_counts.get(word) or 0)


def _moon_key(moon: dict) -> tuple[str, int]:
    return (str(moon.get("kingdom") or ""), int(moon.get("moon") or 0))


def _orphan_moon_capture_word(moon: dict) -> str | None:
    """Lunas del pool captures sin fila capturas_lunas → slug heurístico."""
    name = str(moon.get("name") or "").casefold()
    if "poison" in name and "swamp" in name:
        return "poison_piranha_plant"
    if "statue" in name and "bowser" in name:
        return "bowser_statue"
    return None


def _sin_luna_count_for_row(row: dict) -> tuple[str, int] | None:
    word = _capture_row_palabra(row)
    if not word:
        return None
    n_moons = int(row.get("n_moons") or 0)
    if n_moons <= 0:
        n_moons = len(row.get("moons") or [])
    if n_moons > 0:
        return None
    n_lista = int(row.get("n_lista") or 0)
    if n_lista <= 0:
        n_lista = len(row.get("lista") or [])
    if n_lista > 0:
        return word, n_lista
    n_obj = int(row.get("n_objectives") or 0)
    if n_obj <= 0:
        n_obj = len(row.get("objectives") or [])
    if n_obj > 0:
        return word, 1
    return None


def _build_capture_sin_luna_captura_counts() -> dict[str, int]:
    """Capturas fuera del pool de 163 lunas: +1 por goal fija; binoculars → n_lista."""
    out: dict[str, int] = {}
    caps_path = CATALOG_DIR / _FN_CAPTURAS_LUNAS
    if not caps_path.is_file():
        return out
    for row in load_catalog(caps_path).get("captures") or []:
        if not isinstance(row, dict):
            continue
        parsed = _sin_luna_count_for_row(row)
        if parsed:
            out[parsed[0]] = parsed[1]
    return out


def _load_capture_rows() -> list[dict]:
    caps_path = CATALOG_DIR / _FN_CAPTURAS_LUNAS
    return [
        r for r in load_catalog(caps_path).get("captures") or [] if isinstance(r, dict)
    ]


def _map_cap_rows_to_pool_moons(
    cap_rows: list[dict], pool: set[tuple[str, int]]
) -> dict[tuple[str, int], str]:
    moon_to_word: dict[tuple[str, int], str] = {}
    for row in cap_rows:
        word = _capture_row_palabra(row)
        if not word:
            continue
        for moon in row.get("moons") or []:
            key = _moon_key(moon)
            if key in pool and key not in moon_to_word:
                moon_to_word[key] = word
    return moon_to_word


def _map_grupo_slugs_to_pool_moons(
    capture_slugs: set[str | None],
    pool: set[tuple[str, int]],
    moon_to_word: dict[tuple[str, int], str],
) -> None:
    grupo_by_id = {g["id"]: g for g in load_bingo_groups()}
    for slug in capture_slugs:
        if not slug:
            continue
        gid = _canon(slug, "grupo") or slug
        group = grupo_by_id.get(gid)
        if not group or gid == CAPTURA_GRUPO_ID or gid in KINGDOM_COLUMNS:
            continue
        for moon in _resolve_bingo_group_moons_raw(group):
            key = _moon_key(moon)
            if key in pool and key not in moon_to_word:
                moon_to_word[key] = slug


def _map_orphan_pool_moons(
    pool_moons: list[dict],
    moon_to_word: dict[tuple[str, int], str],
) -> None:
    for moon in pool_moons:
        key = _moon_key(moon)
        if key in moon_to_word:
            continue
        orphan = _orphan_moon_capture_word(moon)
        if orphan:
            moon_to_word[key] = orphan


def _build_per_capture_captura_counts() -> dict[str, int]:
    """46 slugs capturas_lunas → lunas del pool captures (Σ = n.moons del grupo)."""
    captures_group = next(
        (g for g in load_bingo_groups() if g.get("id") == CAPTURA_GRUPO_ID), None
    )
    if not captures_group:
        return {}
    pool_moons = _resolve_bingo_group_moons_raw(captures_group)
    pool = {_moon_key(m) for m in pool_moons}
    cap_rows = _load_capture_rows()
    capture_slugs = {_capture_row_palabra(r) for r in cap_rows}
    capture_slugs.discard(None)
    moon_to_word = _map_cap_rows_to_pool_moons(cap_rows, pool)
    _map_grupo_slugs_to_pool_moons(capture_slugs, pool, moon_to_word)
    _map_orphan_pool_moons(pool_moons, moon_to_word)
    counts: dict[str, int] = defaultdict(int)
    for word in moon_to_word.values():
        counts[word] += 1
    for row in cap_rows:
        cap_word = _capture_row_palabra(row)
        if cap_word:
            counts.setdefault(cap_word, 0)
    return dict(counts)


def _build_standalone_capture_words() -> set[str]:
    """Slugs capturas_lunas sin id de grupo bingo propio (goal/luna vía capturas_lunas)."""
    grupo_ids = _build_grupo_ids()
    out: set[str] = set()
    caps_path = CATALOG_DIR / _FN_CAPTURAS_LUNAS
    if not caps_path.is_file():
        return out
    for row in load_catalog(caps_path).get("captures") or []:
        if not isinstance(row, dict):
            continue
        word = _capture_row_palabra(row)
        if word and not _capture_uso_redundant_with_grupo(word, grupo_ids):
            out.add(word)
    return out


def _build_captura_grupo_moon_count() -> int:
    """Grupo paraguas captures → n.moons (Σ uso captura)."""
    for group in load_bingo_groups():
        if not isinstance(group, dict) or group.get("id") != CAPTURA_GRUPO_ID:
            continue
        n = _group_n(group)
        n_m = int(n.get("moons") or 0)
        if n_m > 0:
            return n_m
        return len(group.get("moons") or [])
    return 0


def _lookup_bingo_count(word: str, bingo_counts: dict[str, int]) -> int:
    keys = {word, _canon(word, "bingo"), canonicalize_tag(word)}
    best = 0
    for key in keys:
        if key:
            best = max(best, int(bingo_counts.get(key) or 0))
    return best


def parse_usos(usos: dict[str, int]) -> dict[str, int]:
    """Normaliza usos {tipo: n} → enteros."""
    return {str(k): int(v) for k, v in usos.items()}


def _resolve_format_counts(
    usos: list[str],
    n_ind: dict[str, int],
    *,
    luna_for_tag: int,
    grupo_n: dict[str, int] | None,
    lista_n: int | None,
) -> tuple[int, int, int]:
    g = grupo_n or {}
    if g:
        return (
            int(g.get("luna") or 0),
            int(g.get("goal") or 0),
            int(lista_n if lista_n is not None else g.get("lista") or 0),
        )
    return (
        int(n_ind.get("luna") or luna_for_tag or 0),
        int(n_ind.get("goal") or 0),
        int(lista_n or 0),
    )


def _format_uso_value(
    uso: str,
    *,
    bingo_n: int,
    captura_n: int,
    n_goal: int,
    n_luna: int,
    n_lista: int,
) -> int:
    if uso == "bingo":
        return bingo_n
    if uso == "captura":
        return int(captura_n)
    if uso == "goal":
        return n_goal
    if uso == "luna":
        return n_luna
    if uso == "grupo":
        return 1
    if uso == "lista":
        return n_lista
    if uso == "tag":
        return n_luna
    if uso == "zona":
        return 1
    return 0


def _format_usos(
    usos: list[str],
    n_ind: dict[str, int],
    *,
    luna_for_tag: int = 0,
    bingo_n: int = 0,
    grupo_n: dict[str, int] | None = None,
    lista_n: int | None = None,
    captura_n: int = 0,
) -> dict[str, int]:
    n_luna, n_goal, n_lista = _resolve_format_counts(
        usos,
        n_ind,
        luna_for_tag=luna_for_tag,
        grupo_n=grupo_n,
        lista_n=lista_n,
    )
    return {
        uso: _format_uso_value(
            uso,
            bingo_n=bingo_n,
            captura_n=captura_n,
            n_goal=n_goal,
            n_luna=n_luna,
            n_lista=n_lista,
        )
        for uso in usos
    }

_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def _slug(raw: object) -> str | None:
    text = str(raw or "").strip().casefold()
    if not text:
        return None
    text = text.replace("-", "_").replace(" ", "_").replace("'", "")
    text = _SLUG_RE.sub("_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or None


def _add(bucket: dict[str, set[str]], word: str | None, uso: str) -> None:
    if not word or uso not in USO_ORDER:
        return
    bucket[word].add(uso)


def _canon(word: str | None, uso: str, moon_tag: str | None = None) -> str | None:
    slug = _slug(word)
    if not slug:
        return None
    return canonicalize_palabra(slug, uso=uso, moon_tag=moon_tag)


def _capture_row_palabra(row: dict) -> str | None:
    capture_name = str(row.get("capture") or "").strip()
    if capture_name:
        return _slug(capture_name)
    return _slug(row.get("moon_tag"))


def _build_grupo_ids() -> set[str]:
    out: set[str] = set()
    for group in load_bingo_groups():
        if not isinstance(group, dict):
            continue
        moon_tag = group.get("moon_tag") or group.get("tag")
        word = _canon(group.get("id"), "grupo", moon_tag=str(moon_tag) if moon_tag else None)
        if word:
            out.add(word)
    return out


def _capture_uso_redundant_with_grupo(capture_word: str | None, grupo_ids: set[str]) -> bool:
    """Captura cuyo slug ya es id de grupo bingo (grupo+tag cubren el pool)."""
    if not capture_word:
        return False
    canon = _canon(capture_word, "captura") or capture_word
    return capture_word in grupo_ids or canon in grupo_ids


def _zona_palabra(zone: str, kingdom: str | None, *, multi_kingdom: bool) -> str:
    if multi_kingdom:
        k = _slug(kingdom)
        return f"{k}_{zone}" if k else zone
    return zone


def _iter_field_values(obj: object):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_field_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_field_values(v)
    else:
        yield obj


def _slug_tokens_from_value(val: object) -> set[str]:
    if val is True or val is False or val is None:
        return set()
    s = _slug(val)
    if not s:
        return set()
    return set(s.split("_")) | {s}


def _tokens_in_record(record: dict) -> set[str]:
    tokens: set[str] = set()
    for val in _iter_field_values(record):
        tokens.update(_slug_tokens_from_value(val))
    return tokens


def _is_capture_only_usos(
    usos: set[str], word: str, standalone_capture_words: set[str]
) -> bool:
    """Fila capturas_lunas sin grupo/tag propio (goal/luna solo de capturas_lunas)."""
    return (
        word in standalone_capture_words
        and "grupo" not in usos
        and "tag" not in usos
    )


def _collect_goal_counts_from_referencia(
    goal_counts: dict[str, int],
) -> set[str]:
    ref_templates: set[str] = set()
    ref_path = CATALOG_DIR / "goals_referencia.json"
    if not ref_path.is_file():
        return ref_templates
    for goal in load_catalog(ref_path).get("goals") or []:
        if not isinstance(goal, dict):
            continue
        tmpl = str(goal.get("goal") or "").strip()
        if tmpl:
            ref_templates.add(tmpl)
        for token in _tokens_in_record(goal):
            goal_counts[token] += 1
    return ref_templates


def _collect_luna_counts_from_moons(luna_counts: dict[str, int]) -> None:
    lunas_path = CATALOG_DIR / "lunas-objetivos.json"
    if not lunas_path.is_file():
        return
    for moon in load_catalog(lunas_path).get("moons") or []:
        if not isinstance(moon, dict):
            continue
        for token in _tokens_in_record(moon):
            luna_counts[token] += 1


def _add_capture_luna_count_from_row(
    row: dict,
    word: str,
    capture_luna_counts: dict[str, int],
) -> None:
    n_m = int(row.get("n_moons") or 0) or len(row.get("moons") or [])
    if n_m > 0:
        capture_luna_counts[word] += n_m


def _add_capture_goal_counts_from_row(
    row: dict,
    word: str,
    ref_templates: set[str],
    captura_goal_counts: dict[str, int],
) -> None:
    for obj in row.get("objectives") or []:
        if not isinstance(obj, dict):
            continue
        tmpl = str(obj.get("goal") or "").strip()
        if tmpl in ref_templates:
            captura_goal_counts[word] += 1


def _collect_capture_referencia_row(
    row: dict,
    ref_templates: set[str],
    captura_goal_counts: dict[str, int],
    capture_luna_counts: dict[str, int],
) -> None:
    word = _capture_row_palabra(row)
    if not word:
        return
    _add_capture_luna_count_from_row(row, word, capture_luna_counts)
    _add_capture_goal_counts_from_row(row, word, ref_templates, captura_goal_counts)


def _collect_capture_referencia_counts(
    ref_templates: set[str],
    captura_goal_counts: dict[str, int],
    capture_luna_counts: dict[str, int],
) -> None:
    caps_path = CATALOG_DIR / _FN_CAPTURAS_LUNAS
    if not caps_path.is_file():
        return
    for row in load_catalog(caps_path).get("captures") or []:
        if not isinstance(row, dict):
            continue
        _collect_capture_referencia_row(
            row, ref_templates, captura_goal_counts, capture_luna_counts
        )


def _build_referencia_individual_counts() -> tuple[
    dict[str, int], dict[str, int], dict[str, int], dict[str, int]
]:
    """Por palabra: n goals / n lunas en referencia; captura→goals/lunas propias."""
    goal_counts: dict[str, int] = defaultdict(int)
    ref_templates = _collect_goal_counts_from_referencia(goal_counts)
    captura_goal_counts: dict[str, int] = defaultdict(int)
    capture_luna_counts: dict[str, int] = defaultdict(int)
    luna_counts: dict[str, int] = defaultdict(int)
    _collect_luna_counts_from_moons(luna_counts)
    _collect_capture_referencia_counts(
        ref_templates, captura_goal_counts, capture_luna_counts
    )
    return goal_counts, luna_counts, captura_goal_counts, capture_luna_counts


def _lookup_individual_count(
    word: str,
    usos: set[str],
    counts: dict[str, int],
) -> int:
    keys: set[str] = {word}
    if "tag" in usos:
        canon = _canon(word, "tag")
        if canon:
            keys.add(canon)
        keys.add(canonicalize_tag(word))
    if "captura" in usos:
        keys.add(word)
    if "bingo" in usos and word in TAG_KINGDOM:
        keys.add(word)
    best = 0
    for key in keys:
        best = max(best, int(counts.get(key) or 0))
    return best


def _collect_bingo_usos(out: dict[str, set[str]]) -> None:
    lineas_path = CATALOG_DIR / _FN_BINGO_LINEAS
    if not lineas_path.is_file():
        return
    for group in load_catalog(lineas_path).get("groups") or []:
        _add(out, _canon(group.get("id"), "bingo"), "bingo")


def _collect_grupo_usos(out: dict[str, set[str]]) -> None:
    for group in load_bingo_groups():
        if not isinstance(group, dict):
            continue
        moon_tag = group.get("moon_tag") or group.get("tag")
        word = _canon(group.get("id"), "grupo", moon_tag=str(moon_tag) if moon_tag else None)
        _add(out, word, "grupo")


def _collect_tag_usos(out: dict[str, set[str]]) -> None:
    tags_path = CATALOG_DIR / "tags_inventario.json"
    if not tags_path.is_file():
        return
    for row in load_catalog(tags_path).get("tags") or []:
        _add(out, _canon(row.get("tag"), "tag"), "tag")


def _collect_lista_usos(out: dict[str, set[str]]) -> None:
    lists_path = CATALOG_DIR / _FN_GOAL_LISTS
    if not lists_path.is_file():
        return
    lists = load_catalog(lists_path).get("lists") or {}
    if not isinstance(lists, dict):
        return
    for name in lists:
        _add(out, _canon(name, "lista"), "lista")


def _collect_zona_usos(out: dict[str, set[str]]) -> None:
    zonas_inv_path = CATALOG_DIR / _FN_ZONAS_INVENTARIO
    if not zonas_inv_path.is_file():
        return
    for row in load_catalog(zonas_inv_path).get("zones") or []:
        word = _canon(row.get("zone"), "zona") or _slug(row.get("zone"))
        if word:
            _add(out, word, "zona")


def _collect_captura_usos(out: dict[str, set[str]]) -> None:
    caps_path = CATALOG_DIR / _FN_CAPTURAS_LUNAS
    if not caps_path.is_file():
        return
    for row in load_catalog(caps_path).get("captures") or []:
        if not isinstance(row, dict):
            continue
        word = _capture_row_palabra(row)
        if not word:
            continue
        _add(out, word, "captura")
        n_lista = int(row.get("n_lista") or 0)
        if n_lista <= 0:
            n_lista = len(row.get("lista") or [])
        if n_lista > 0:
            _add(out, word, "lista")


def _collect_fixed_usos() -> dict[str, set[str]]:
    """Palabras y usos fijos 1:1 con catálogo fuente (sin goal/luna)."""
    out: dict[str, set[str]] = defaultdict(set)
    _collect_bingo_usos(out)
    _collect_grupo_usos(out)
    _collect_tag_usos(out)
    _collect_lista_usos(out)
    _collect_zona_usos(out)
    _collect_captura_usos(out)
    return out


def _collect_goal_tags() -> set[str]:
    goal_tags: set[str] = set()
    ref_path = CATALOG_DIR / "goals_referencia.json"
    if not ref_path.is_file():
        return goal_tags
    for goal in load_catalog(ref_path).get("goals") or []:
        if not isinstance(goal, dict):
            continue
        for t in goal.get("tags") or []:
            goal_tags.add(canonicalize_tag(str(t)))
    return goal_tags


def _collect_luna_tags() -> set[str]:
    luna_tags: set[str] = set()
    lunas_path = CATALOG_DIR / "lunas-objetivos.json"
    if not lunas_path.is_file():
        return luna_tags
    for moon in load_catalog(lunas_path).get("moons") or []:
        if not isinstance(moon, dict):
            continue
        for t in moon.get("tags") or []:
            luna_tags.add(canonicalize_tag(str(t)))
    return luna_tags


def _collect_captura_has_flags() -> tuple[dict[str, bool], dict[str, bool]]:
    captura_has_goal: dict[str, bool] = {}
    captura_has_luna: dict[str, bool] = {}
    caps_path = CATALOG_DIR / _FN_CAPTURAS_LUNAS
    if not caps_path.is_file():
        return captura_has_goal, captura_has_luna
    for row in load_catalog(caps_path).get("captures") or []:
        if not isinstance(row, dict):
            continue
        word = _capture_row_palabra(row)
        if not word:
            continue
        n_obj = int(row.get("n_objectives") or 0)
        if n_obj <= 0:
            n_obj = len(row.get("objectives") or [])
        n_moons = int(row.get("n_moons") or 0)
        if n_moons <= 0:
            n_moons = len(row.get("moons") or [])
        captura_has_goal[word] = n_obj > 0
        captura_has_luna[word] = n_moons > 0
    return captura_has_goal, captura_has_luna


def _build_variable_indexes() -> tuple[
    set[str],
    set[str],
    dict[str, bool],
    dict[str, bool],
    dict[str, int],
    dict[str, int],
    dict[str, int],
    dict[str, int],
]:
    goal_tags = _collect_goal_tags()
    luna_tags = _collect_luna_tags()
    captura_has_goal, captura_has_luna = _collect_captura_has_flags()
    goal_counts, luna_counts, captura_goal_counts, capture_luna_counts = (
        _build_referencia_individual_counts()
    )
    return (
        goal_tags,
        luna_tags,
        captura_has_goal,
        captura_has_luna,
        goal_counts,
        luna_counts,
        captura_goal_counts,
        capture_luna_counts,
    )


def _lookup_keys_for_variable(word: str, usos: set[str]) -> set[str]:
    """Slugs para goal/luna: tag/bingo-reino en la misma palabra (sin alias grupo/lista)."""
    keys: set[str] = set()
    if "tag" in usos:
        keys.add(word)
        canon = _canon(word, "tag")
        if canon:
            keys.add(canon)
        keys.add(canonicalize_tag(word))
    if "bingo" in usos and word in TAG_KINGDOM:
        keys.add(word)
    return keys


def _individual_counts_capture_only(
    word: str,
    usos: set[str],
    *,
    captura_goal_counts: dict[str, int],
    capture_luna_counts: dict[str, int],
) -> dict[str, int]:
    out: dict[str, int] = {}
    if "goal" in usos:
        n_goal = int(captura_goal_counts.get(word) or 0)
        if n_goal > 0:
            out["goal"] = n_goal
    if "luna" in usos:
        n_luna = int(capture_luna_counts.get(word) or 0)
        if n_luna > 0:
            out["luna"] = n_luna
    return out


def _individual_counts_regular(
    word: str,
    usos: set[str],
    *,
    goal_counts: dict[str, int],
    luna_counts: dict[str, int],
    captura_goal_counts: dict[str, int],
) -> dict[str, int]:
    out: dict[str, int] = {}
    if "goal" in usos:
        n_goal = _lookup_individual_count(word, usos, goal_counts)
        if "captura" in usos:
            n_goal = max(n_goal, int(captura_goal_counts.get(word) or 0))
        if n_goal > 0:
            out["goal"] = n_goal
    if "luna" in usos:
        n_luna = _lookup_individual_count(word, usos, luna_counts)
        if n_luna > 0:
            out["luna"] = n_luna
    return out


def _individual_counts_for_word(
    word: str,
    usos: set[str],
    *,
    standalone_capture_words: set[str],
    goal_counts: dict[str, int],
    luna_counts: dict[str, int],
    captura_goal_counts: dict[str, int],
    capture_luna_counts: dict[str, int],
) -> dict[str, int]:
    """Conteos concretos: +1 por goal/luna en referencia si algún campo contiene el slug."""
    if "grupo" in usos:
        return {}
    if _is_capture_only_usos(usos, word, standalone_capture_words):
        return _individual_counts_capture_only(
            word,
            usos,
            captura_goal_counts=captura_goal_counts,
            capture_luna_counts=capture_luna_counts,
        )
    return _individual_counts_regular(
        word,
        usos,
        goal_counts=goal_counts,
        luna_counts=luna_counts,
        captura_goal_counts=captura_goal_counts,
    )


def _should_add_goal_uso(
    word: str,
    usos: set[str],
    *,
    standalone_capture_words: set[str],
    captura_has_goal: dict[str, bool],
    goal_tags: set[str],
) -> bool:
    if "captura" in usos and captura_has_goal.get(word):
        return True
    if _is_capture_only_usos(usos, word, standalone_capture_words):
        return False
    keys = _lookup_keys_for_variable(word, usos)
    return bool(keys & goal_tags)


def _should_add_luna_uso(
    word: str,
    usos: set[str],
    *,
    standalone_capture_words: set[str],
    captura_has_luna: dict[str, bool],
    luna_tags: set[str],
) -> bool:
    if "captura" in usos and captura_has_luna.get(word):
        return True
    if _is_capture_only_usos(usos, word, standalone_capture_words):
        return False
    keys = _lookup_keys_for_variable(word, usos)
    return bool(keys & luna_tags)


def _apply_variable_usos_for_word(
    out: dict[str, set[str]],
    word: str,
    usos: set[str],
    *,
    standalone_capture_words: set[str],
    goal_tags: set[str],
    luna_tags: set[str],
    captura_has_goal: dict[str, bool],
    captura_has_luna: dict[str, bool],
) -> None:
    if not (usos & set(USO_IDENTITY) or word in standalone_capture_words):
        return
    if "grupo" in usos:
        return
    if word in standalone_capture_words:
        if captura_has_goal.get(word):
            _add(out, word, "goal")
        if captura_has_luna.get(word):
            _add(out, word, "luna")
        return
    if _should_add_goal_uso(
        word,
        usos,
        standalone_capture_words=standalone_capture_words,
        captura_has_goal=captura_has_goal,
        goal_tags=goal_tags,
    ):
        _add(out, word, "goal")
    if _should_add_luna_uso(
        word,
        usos,
        standalone_capture_words=standalone_capture_words,
        captura_has_luna=captura_has_luna,
        luna_tags=luna_tags,
    ):
        _add(out, word, "luna")


def _apply_variable_usos(
    out: dict[str, set[str]],
    *,
    standalone_capture_words: set[str],
    goal_tags: set[str],
    luna_tags: set[str],
    captura_has_goal: dict[str, bool],
    captura_has_luna: dict[str, bool],
) -> None:
    for word, usos in out.items():
        _apply_variable_usos_for_word(
            out,
            word,
            usos,
            standalone_capture_words=standalone_capture_words,
            goal_tags=goal_tags,
            luna_tags=luna_tags,
            captura_has_goal=captura_has_goal,
            captura_has_luna=captura_has_luna,
        )


def _apply_grupo_item_usos(
    out: dict[str, set[str]],
    grupo_counts: dict[str, dict[str, int]],
) -> None:
    """Si la palabra es grupo: goal/luna/lista según ítems del grupo."""
    for word, usos in out.items():
        if "grupo" not in usos:
            continue
        counts = grupo_counts.get(word) or {}
        if int(counts.get("goal") or 0) > 0:
            _add(out, word, "goal")
        if int(counts.get("luna") or 0) > 0:
            _add(out, word, "luna")
        if int(counts.get("lista") or 0) > 0:
            _add(out, word, "lista")


def collect_palabra_usos() -> tuple[
    dict[str, set[str]],
    dict[str, int],
    dict[str, int],
    dict[str, dict[str, int]],
    dict[str, int],
    dict[str, int],
    dict[str, int],
    dict[str, int],
    set[str],
]:
    out = _collect_fixed_usos()
    bingo_counts = _build_bingo_individual_counts()
    capture_lista_counts = _build_capture_lista_counts()
    grupo_counts = _build_grupo_item_counts()
    standalone_capture_words = _build_standalone_capture_words()
    (
        goal_tags,
        luna_tags,
        captura_has_goal,
        captura_has_luna,
        goal_counts,
        luna_counts,
        captura_goal_counts,
        capture_luna_counts,
    ) = _build_variable_indexes()
    _apply_variable_usos(
        out,
        standalone_capture_words=standalone_capture_words,
        goal_tags=goal_tags,
        luna_tags=luna_tags,
        captura_has_goal=captura_has_goal,
        captura_has_luna=captura_has_luna,
    )
    _apply_grupo_item_usos(out, grupo_counts)
    return (
        out,
        bingo_counts,
        capture_lista_counts,
        grupo_counts,
        goal_counts,
        luna_counts,
        captura_goal_counts,
        capture_luna_counts,
        standalone_capture_words,
    )


def _expected_fixed_uso_counts() -> dict[str, int]:
    zones = load_catalog(CATALOG_DIR / _FN_ZONAS_INVENTARIO)
    return {
        "grupo": len(load_bingo_groups()),
        "zona": len(zones.get("zones") or []),
    }


def _collect_lista_words_from_goal_lists(lista_words: set[str]) -> None:
    lists = load_catalog(CATALOG_DIR / _FN_GOAL_LISTS).get("lists") or {}
    if not isinstance(lists, dict):
        return
    for name in lists:
        word = _canon(name, "lista") or _slug(name)
        if word:
            lista_words.add(word)


def _collect_lista_words_from_grupos(lista_words: set[str]) -> None:
    for group in load_bingo_groups():
        if not isinstance(group, dict):
            continue
        word = _canon(group.get("id"), "grupo") or _slug(group.get("id"))
        if not word:
            continue
        n = _group_n(group)
        n_lista = int(n.get("lista") or 0)
        if n_lista <= 0 and _grupo_has_lista_pool(group):
            n_lista = len(group.get("lista") or [])
        if n_lista > 0:
            lista_words.add(word)


def _collect_lista_words_from_captures(caps: dict, lista_words: set[str]) -> None:
    for row in caps.get("captures") or []:
        if not isinstance(row, dict):
            continue
        word = _capture_row_palabra(row)
        if not word:
            continue
        n_lista = int(row.get("n_lista") or 0)
        if n_lista <= 0:
            n_lista = len(row.get("lista") or [])
        if n_lista > 0:
            lista_words.add(word)


def _count_captura_words_with_counts(
    captura_counts: dict[str, int],
    captura_sin_luna: dict[str, int],
) -> int:
    return sum(
        1
        for word in captura_counts
        if int(captura_counts.get(word) or 0) > 0
        or int(captura_sin_luna.get(word) or 0) > 0
    )


def _expected_palabra_fija_by_uso() -> dict[str, int]:
    """n_palabras esperado por uso de palabra fija (catálogo fuente)."""
    lineas = load_catalog(CATALOG_DIR / _FN_BINGO_LINEAS)
    tags = load_catalog(CATALOG_DIR / "tags_inventario.json")
    caps = load_catalog(CATALOG_DIR / _FN_CAPTURAS_LUNAS)
    lista_words: set[str] = set()
    _collect_lista_words_from_goal_lists(lista_words)
    _collect_lista_words_from_grupos(lista_words)
    _collect_lista_words_from_captures(caps, lista_words)
    captura_counts = _build_per_capture_captura_counts()
    captura_sin_luna = _build_capture_sin_luna_captura_counts()
    n_captura = _count_captura_words_with_counts(captura_counts, captura_sin_luna)
    return {
        "bingo": len(lineas.get("groups") or []),
        "captura": n_captura,
        "grupo": len(load_bingo_groups()),
        "lista": len(lista_words),
        "tag": len(tags.get("tags") or []),
        "zona": len(load_catalog(CATALOG_DIR / _FN_ZONAS_INVENTARIO).get("zones") or []),
    }


def _expected_lista_total(
    words: list[str],
    usos_by: dict[str, set[str]],
    *,
    grupo_counts: dict[str, dict[str, int]],
    goal_list_counts: dict[str, int],
    capture_lista_counts: dict[str, int],
    grupo_lista_computed: dict[str, int] | None = None,
) -> int:
    """Σ lista: grupos → n.lista efectivo; capturas → lista[]; goal_lists."""
    total = 0
    for word in words:
        usos = usos_by.get(word) or set()
        if "lista" not in usos:
            continue
        total += _resolve_lista_n(
            word,
            usos,
            grupo_counts=grupo_counts,
            goal_list_counts=goal_list_counts,
            capture_lista_counts=capture_lista_counts,
            grupo_lista_computed=grupo_lista_computed,
        )
    return total


def _expected_captura_total() -> int:
    """Σ captura: pool captures (163 lunas) + sin luna (goals fijas + binoculars)."""
    return _build_captura_grupo_moon_count() + sum(
        _build_capture_sin_luna_captura_counts().values()
    )


def _compute_luna_for_tag(
    word: str,
    usos: list[str],
    usos_by_word: set[str],
    n_ind: dict[str, int],
    luna_counts: dict[str, int],
) -> int:
    if "tag" not in usos or "luna" in n_ind or "grupo" in usos:
        return 0
    return _lookup_individual_count(word, usos_by_word, luna_counts)


def _compute_lista_n_for_word(
    word: str,
    usos_by_word: set[str],
    *,
    grupo_counts: dict[str, dict[str, int]],
    goal_list_counts: dict[str, int],
    capture_lista_counts: dict[str, int],
    grupo_lista_computed: dict[str, int],
) -> int | None:
    if "lista" not in usos_by_word:
        return None
    return _resolve_lista_n(
        word,
        usos_by_word,
        grupo_counts=grupo_counts,
        goal_list_counts=goal_list_counts,
        capture_lista_counts=capture_lista_counts,
        grupo_lista_computed=grupo_lista_computed,
    )


def _compute_captura_n_for_word(
    word: str,
    usos_by_word: set[str],
    *,
    captura_counts: dict[str, int],
    captura_sin_luna: dict[str, int],
) -> int:
    if "captura" not in usos_by_word:
        return 0
    return int(captura_counts.get(word) or 0) + int(captura_sin_luna.get(word) or 0)


def _accumulate_individual_totals(
    totals: dict[str, int],
    parsed: dict[str, int],
) -> None:
    for key in ("bingo", "captura", "goal", "luna", "lista", "tag"):
        totals[key] += parsed.get(key, 0)


def _try_build_palabra_row(
    *,
    row_id: int,
    word: str,
    usos: list[str],
    usos_by: dict[str, set[str]],
    uso_counts: dict[str, int],
    totals: dict[str, int],
    standalone_capture_words: set[str],
    goal_counts: dict[str, int],
    luna_counts: dict[str, int],
    captura_goal_counts: dict[str, int],
    capture_luna_counts: dict[str, int],
    bingo_counts: dict[str, int],
    grupo_counts: dict[str, dict[str, int]],
    goal_list_counts: dict[str, int],
    capture_lista_counts: dict[str, int],
    grupo_lista_computed: dict[str, int],
    captura_counts: dict[str, int],
    captura_sin_luna: dict[str, int],
) -> dict | None:
    for u in usos:
        if u in USO_FIJO_WORD_COUNT:
            uso_counts[u] += 1
    n_ind = _individual_counts_for_word(
        word,
        usos_by[word],
        standalone_capture_words=standalone_capture_words,
        goal_counts=goal_counts,
        luna_counts=luna_counts,
        captura_goal_counts=captura_goal_counts,
        capture_luna_counts=capture_luna_counts,
    )
    luna_for_tag = _compute_luna_for_tag(
        word, usos, usos_by[word], n_ind, luna_counts
    )
    bingo_n = _lookup_bingo_count(word, bingo_counts) if "bingo" in usos else 0
    grupo_n = grupo_counts.get(word) if "grupo" in usos else None
    lista_n = _compute_lista_n_for_word(
        word,
        usos_by[word],
        grupo_counts=grupo_counts,
        goal_list_counts=goal_list_counts,
        capture_lista_counts=capture_lista_counts,
        grupo_lista_computed=grupo_lista_computed,
    )
    captura_n = _compute_captura_n_for_word(
        word,
        usos_by[word],
        captura_counts=captura_counts,
        captura_sin_luna=captura_sin_luna,
    )
    usos_fmt = _format_usos(
        usos,
        n_ind,
        luna_for_tag=luna_for_tag,
        bingo_n=bingo_n,
        grupo_n=grupo_n,
        lista_n=lista_n,
        captura_n=captura_n,
    )
    usos_fmt = {u: n for u, n in usos_fmt.items() if n != 0}
    if not usos_fmt:
        return None
    usos_by[word] = set(usos_fmt)
    parsed = parse_usos(usos_fmt)
    _accumulate_individual_totals(totals, parsed)
    return {
        "id": row_id,
        "palabra": word,
        "n_usos": sum(parsed.values()),
        "usos": usos_fmt,
    }


def _build_palabras_rows(
    words: list[str],
    usos_by: dict[str, set[str]],
    *,
    standalone_capture_words: set[str],
    goal_counts: dict[str, int],
    luna_counts: dict[str, int],
    captura_goal_counts: dict[str, int],
    capture_luna_counts: dict[str, int],
    bingo_counts: dict[str, int],
    grupo_counts: dict[str, dict[str, int]],
    goal_list_counts: dict[str, int],
    capture_lista_counts: dict[str, int],
    grupo_lista_computed: dict[str, int],
    captura_counts: dict[str, int],
    captura_sin_luna: dict[str, int],
) -> tuple[list[dict], dict[str, int], dict[str, int]]:
    rows: list[dict] = []
    uso_counts: dict[str, int] = dict.fromkeys(USO_ORDER, 0)
    totals = dict.fromkeys(("bingo", "captura", "goal", "luna", "lista", "tag"), 0)
    for i, word in enumerate(words, 1):
        usos = [u for u in USO_ORDER if u in usos_by[word]]
        row = _try_build_palabra_row(
            row_id=i,
            word=word,
            usos=usos,
            usos_by=usos_by,
            uso_counts=uso_counts,
            totals=totals,
            standalone_capture_words=standalone_capture_words,
            goal_counts=goal_counts,
            luna_counts=luna_counts,
            captura_goal_counts=captura_goal_counts,
            capture_luna_counts=capture_luna_counts,
            bingo_counts=bingo_counts,
            grupo_counts=grupo_counts,
            goal_list_counts=goal_list_counts,
            capture_lista_counts=capture_lista_counts,
            grupo_lista_computed=grupo_lista_computed,
            captura_counts=captura_counts,
            captura_sin_luna=captura_sin_luna,
        )
        if row:
            rows.append(row)
    for key, value in totals.items():
        uso_counts[key] = value
    return rows, uso_counts, totals


def _validate_fixed_word_uso_counts(uso_counts: dict[str, int]) -> None:
    expected_fixed = _expected_fixed_uso_counts()
    for uso in USO_FIJO_WORD_COUNT:
        got = uso_counts[uso]
        want = expected_fixed[uso]
        if got != want:
            raise ValueError(
                f"n_by_uso[{uso!r}]={got} != {want} (catálogo fuente)"
            )


def _validate_bingo_total(n_individual_bingo: int) -> None:
    lineas = load_catalog(CATALOG_DIR / _FN_BINGO_LINEAS)
    want_bingo = sum(
        int(g.get("n_goals") or 0) for g in lineas.get("groups") or []
    )
    if n_individual_bingo != want_bingo:
        raise ValueError(
            f"n_by_uso['bingo']={n_individual_bingo} != bingo_lineas Σ n_goals ({want_bingo})"
        )


def _validate_lista_aggregate(
    n_individual_lista: int,
    words: list[str],
    usos_by: dict[str, set[str]],
    *,
    grupo_counts: dict[str, dict[str, int]],
    goal_list_counts: dict[str, int],
    capture_lista_counts: dict[str, int],
    grupo_lista_computed: dict[str, int],
) -> None:
    want_lista = _expected_lista_total(
        words,
        usos_by,
        grupo_counts=grupo_counts,
        goal_list_counts=goal_list_counts,
        capture_lista_counts=capture_lista_counts,
        grupo_lista_computed=grupo_lista_computed,
    )
    if n_individual_lista != want_lista:
        raise ValueError(
            f"n_by_uso['lista']={n_individual_lista} != Σ lista esperada "
            f"({want_lista})"
        )


def _validate_tag_luna_aggregate(n_individual_tag: int, rows: list[dict]) -> None:
    tag_luna_sum = sum(
        parse_usos(r["usos"]).get("luna", 0)
        for r in rows
        if "tag" in parse_usos(r["usos"])
    )
    if n_individual_tag != tag_luna_sum:
        raise ValueError(
            f"n_by_uso['tag']={n_individual_tag} != luna en filas con tag ({tag_luna_sum})"
        )


def _validate_captura_aggregate(n_individual_captura: int) -> None:
    want_captura = _expected_captura_total()
    if n_individual_captura != want_captura:
        moon_pool = _build_captura_grupo_moon_count()
        sin_luna = sum(_build_capture_sin_luna_captura_counts().values())
        raise ValueError(
            f"n_by_uso['captura']={n_individual_captura} != "
            f"pool captures ({moon_pool}) + sin luna ({sin_luna}) = {want_captura}"
        )


def _validate_captura_word_count(
    rows: list[dict],
    *,
    captura_counts: dict[str, int],
    captura_sin_luna: dict[str, int],
) -> None:
    captura_words = [r for r in rows if "captura" in parse_usos(r["usos"])]
    want_captura_words = sum(
        1
        for word, n in captura_counts.items()
        if int(n or 0) > 0 or int(captura_sin_luna.get(word) or 0) > 0
    )
    if len(captura_words) != want_captura_words:
        raise ValueError(
            f"palabras con captura={len(captura_words)} != "
            f"capturas con conteo >0 ({want_captura_words})"
        )


def _validate_uso_sum_positive(palabra: str, parsed: dict[str, int]) -> None:
    for var in USO_SUM:
        if var in parsed and parsed[var] <= 0:
            raise ValueError(
                f"{palabra!r}: uso {var!r} sin conteo individual"
            )


def _validate_non_tag_uso_value(palabra: str, uso: str, n: int) -> None:
    if uso in USO_FIJO_ZERO and n != 0:
        raise ValueError(
            f"{palabra!r}: uso fijo {uso!r} debe ser 0"
        )
    if uso == "grupo" and n != 1:
        raise ValueError(f"{palabra!r}: grupo debe ser 1")
    if uso == "zona" and n != 1:
        raise ValueError(f"{palabra!r}: zona debe ser 1")
    if uso == "lista" and n <= 0:
        raise ValueError(f"{palabra!r}: lista debe ser > 0")


def _validate_tag_uso_value(
    palabra: str, n: int, parsed: dict[str, int]
) -> None:
    if n <= 0:
        raise ValueError(f"{palabra!r}: tag debe ser > 0")
    if "luna" in parsed and n != parsed["luna"]:
        raise ValueError(f"{palabra!r}: tag debe igualar luna")


def _validate_parsed_uso_values(palabra: str, parsed: dict[str, int]) -> None:
    _validate_uso_sum_positive(palabra, parsed)
    for uso, n in parsed.items():
        if uso == "tag":
            _validate_tag_uso_value(palabra, n, parsed)
        else:
            _validate_non_tag_uso_value(palabra, uso, n)


def _validate_lista_in_row(
    row: dict,
    parsed: dict[str, int],
    *,
    grupo_counts: dict[str, dict[str, int]],
    goal_list_counts: dict[str, int],
    capture_lista_counts: dict[str, int],
    grupo_lista_computed: dict[str, int],
) -> None:
    if "lista" not in parsed:
        return
    palabra = row["palabra"]
    if "grupo" in parsed:
        want_lista_n = _resolve_lista_n(
            palabra,
            set(parsed),
            grupo_counts=grupo_counts,
            goal_list_counts=goal_list_counts,
            capture_lista_counts=capture_lista_counts,
            grupo_lista_computed=grupo_lista_computed,
        )
        if parsed["lista"] != want_lista_n:
            raise ValueError(
                f"{palabra!r}: lista de grupo debe ser {want_lista_n}"
            )
        return
    if palabra in capture_lista_counts:
        want_cap_lista = int(capture_lista_counts.get(palabra) or 0)
        if parsed["lista"] != want_cap_lista:
            raise ValueError(
                f"{palabra!r}: lista de captura debe ser "
                f"n_lista ({want_cap_lista})"
            )
        return
    if parsed["lista"] != int(goal_list_counts.get(palabra) or 0):
        raise ValueError(
            f"{palabra!r}: lista debe ser len(goal_lists)"
        )


def _validate_grupo_in_row(
    row: dict,
    parsed: dict[str, int],
    grupo_counts: dict[str, dict[str, int]],
) -> None:
    if "grupo" not in parsed:
        return
    g = grupo_counts.get(row["palabra"]) or {}
    if "goal" in parsed and parsed["goal"] != int(g.get("goal") or 0):
        raise ValueError(
            f"{row['palabra']!r}: goal de grupo debe ser n.objectives"
        )
    if "luna" in parsed and parsed["luna"] != int(g.get("luna") or 0):
        raise ValueError(
            f"{row['palabra']!r}: luna de grupo debe ser n.moons"
        )


def _validate_palabra_row(
    row: dict,
    *,
    grupo_counts: dict[str, dict[str, int]],
    goal_list_counts: dict[str, int],
    capture_lista_counts: dict[str, int],
    grupo_lista_computed: dict[str, int],
) -> None:
    parsed = parse_usos(row["usos"])
    if row["n_usos"] != sum(parsed.values()):
        raise ValueError(
            f"{row['palabra']!r}: n_usos={row['n_usos']} != sum(usos)"
        )
    _validate_parsed_uso_values(row["palabra"], parsed)
    _validate_lista_in_row(
        row,
        parsed,
        grupo_counts=grupo_counts,
        goal_list_counts=goal_list_counts,
        capture_lista_counts=capture_lista_counts,
        grupo_lista_computed=grupo_lista_computed,
    )
    _validate_grupo_in_row(row, parsed, grupo_counts)


def _validate_all_palabra_rows(
    rows: list[dict],
    *,
    grupo_counts: dict[str, dict[str, int]],
    goal_list_counts: dict[str, int],
    capture_lista_counts: dict[str, int],
    grupo_lista_computed: dict[str, int],
) -> None:
    for row in rows:
        _validate_palabra_row(
            row,
            grupo_counts=grupo_counts,
            goal_list_counts=goal_list_counts,
            capture_lista_counts=capture_lista_counts,
            grupo_lista_computed=grupo_lista_computed,
        )


def _count_palabras_by_uso(rows: list[dict]) -> dict[str, int]:
    n_palabras_by_uso = dict.fromkeys(USO_ORDER, 0)
    for row in rows:
        for u in parse_usos(row["usos"]):
            n_palabras_by_uso[u] += 1
    return n_palabras_by_uso


def _validate_uso_fijo_consistency(
    uso_counts: dict[str, int],
    n_palabras_by_uso: dict[str, int],
) -> None:
    for uso in USO_FIJO:
        if uso_counts[uso] != n_palabras_by_uso[uso]:
            raise ValueError(
                f"uso valor fijo {uso!r}: n_by_uso={uso_counts[uso]} != "
                f"n_palabras={n_palabras_by_uso[uso]}"
            )


def _validate_palabra_fija_counts(n_palabras_by_uso: dict[str, int]) -> None:
    expected_fija = _expected_palabra_fija_by_uso()
    for uso in USO_PALABRA_FIJA:
        got = n_palabras_by_uso[uso]
        want = expected_fija[uso]
        if got != want:
            raise ValueError(
                f"n_palabras_by_uso[{uso!r}]={got} != catálogo fuente ({want})"
            )


def _validate_uso_matrix_complete() -> None:
    matrix_usos = set(USO_ORDER)
    classified = set(
        USO_PALABRA_FIJA_VALOR_FIJO
        + USO_PALABRA_FIJA_VALOR_VARIABLE
        + USO_PALABRA_VARIABLE_VALOR_FIJO
        + USO_PALABRA_VARIABLE_VALOR_VARIABLE
    )
    if classified != matrix_usos:
        raise ValueError(
            f"matriz uso incompleta: falta {matrix_usos - classified}, "
            f"sobra {classified - matrix_usos}"
        )


def _palabras_inventario_payload(
    rows: list[dict],
    uso_counts: dict[str, int],
    n_palabras_by_uso: dict[str, int],
) -> dict:
    return {
        "_definition": (
            "Inventario alfabético de slugs canónicos del catálogo y sus usos. "
            "Cada fila: id, palabra, n_usos, usos {tipo: n}. Sin uso reino "
            "(los slugs de reino ya aparecen vía bingo/grupo/tag/…). "
            "uso_fijo: valor n=1 (grupo, zona). uso_palabra_fija: slugs "
            "predeterminados (bingo_lineas, capturas_lunas, bingo_groups, "
            "goal_lists, tags_inventario, zonas_inventario). Resto derivable "
            "de uso_order (goal, luna). n_palabras_by_uso: cuántas palabras "
            "tienen cada uso. n_by_uso: Σ valores por uso. captura: pool "
            "captures (163 lunas) + capturas sin luna (+1 goal fija; "
            "binoculars=n_lista); se omite si el conteo es 0. tag=luna. "
            "No editar."
        ),
        "_note": "Regenerar: python Files/export_palabras_inventario.py "
        "(o regenerate_all.py).",
        "uso_order": list(USO_ORDER),
        "uso_fijo": list(USO_FIJO),
        "uso_palabra_fija": list(USO_PALABRA_FIJA),
        "n_palabras": len(rows),
        "n_palabras_by_uso": n_palabras_by_uso,
        "n_by_uso": uso_counts,
        "palabras": rows,
    }


def _validate_palabras_inventario(
    rows: list[dict],
    words: list[str],
    usos_by: dict[str, set[str]],
    uso_counts: dict[str, int],
    totals: dict[str, int],
    *,
    grupo_counts: dict[str, dict[str, int]],
    goal_list_counts: dict[str, int],
    capture_lista_counts: dict[str, int],
    grupo_lista_computed: dict[str, int],
    captura_counts: dict[str, int],
    captura_sin_luna: dict[str, int],
) -> dict[str, int]:
    _validate_fixed_word_uso_counts(uso_counts)
    _validate_bingo_total(totals["bingo"])
    _validate_lista_aggregate(
        totals["lista"],
        words,
        usos_by,
        grupo_counts=grupo_counts,
        goal_list_counts=goal_list_counts,
        capture_lista_counts=capture_lista_counts,
        grupo_lista_computed=grupo_lista_computed,
    )
    _validate_tag_luna_aggregate(totals["tag"], rows)
    _validate_captura_aggregate(totals["captura"])
    _validate_captura_word_count(
        rows,
        captura_counts=captura_counts,
        captura_sin_luna=captura_sin_luna,
    )
    _validate_all_palabra_rows(
        rows,
        grupo_counts=grupo_counts,
        goal_list_counts=goal_list_counts,
        capture_lista_counts=capture_lista_counts,
        grupo_lista_computed=grupo_lista_computed,
    )
    n_palabras_by_uso = _count_palabras_by_uso(rows)
    _validate_uso_fijo_consistency(uso_counts, n_palabras_by_uso)
    _validate_palabra_fija_counts(n_palabras_by_uso)
    _validate_uso_matrix_complete()
    return n_palabras_by_uso


def build_palabras_inventario() -> dict:
    (
        usos_by,
        bingo_counts,
        capture_lista_counts,
        grupo_counts,
        goal_counts,
        luna_counts,
        captura_goal_counts,
        capture_luna_counts,
        standalone_capture_words,
    ) = collect_palabra_usos()
    goal_list_counts = _build_goal_list_counts()
    captura_counts = _build_per_capture_captura_counts()
    captura_sin_luna = _build_capture_sin_luna_captura_counts()
    grupo_lista_computed = _build_grupo_lista_computed_counts()
    words = sorted(
        (w for w in usos_by if usos_by[w]),
        key=lambda w: (w.casefold(), w),
    )
    rows, uso_counts, totals = _build_palabras_rows(
        words,
        usos_by,
        standalone_capture_words=standalone_capture_words,
        goal_counts=goal_counts,
        luna_counts=luna_counts,
        captura_goal_counts=captura_goal_counts,
        capture_luna_counts=capture_luna_counts,
        bingo_counts=bingo_counts,
        grupo_counts=grupo_counts,
        goal_list_counts=goal_list_counts,
        capture_lista_counts=capture_lista_counts,
        grupo_lista_computed=grupo_lista_computed,
        captura_counts=captura_counts,
        captura_sin_luna=captura_sin_luna,
    )
    n_palabras_by_uso = _validate_palabras_inventario(
        rows,
        words,
        usos_by,
        uso_counts,
        totals,
        grupo_counts=grupo_counts,
        goal_list_counts=goal_list_counts,
        capture_lista_counts=capture_lista_counts,
        grupo_lista_computed=grupo_lista_computed,
        captura_counts=captura_counts,
        captura_sin_luna=captura_sin_luna,
    )
    return _palabras_inventario_payload(rows, uso_counts, n_palabras_by_uso)


def main() -> int:
    payload = build_palabras_inventario()
    write_catalog_json(OUT_JSON, payload)
    print(
        f"palabras={payload['n_palabras']} "
        f"n_palabras_by_uso={payload['n_palabras_by_uso']} "
        f"n_by_uso={payload['n_by_uso']} -> {OUT_JSON.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
