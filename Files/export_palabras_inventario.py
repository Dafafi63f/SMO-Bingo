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
    lineas_path = CATALOG_DIR / "bingo_lineas.json"
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


def _grupo_has_lista_pool(group: dict) -> bool:
    """Pool lista curado (goal_lists), no ítems sueltos de goals."""
    n = group.get("n") if isinstance(group.get("n"), dict) else {}
    if int(n.get("lista") or 0) > 0:
        return True
    return bool(group_lista(group))


def _build_grupo_item_counts() -> dict[str, dict[str, int]]:
    """Id de grupo → {goal, luna, lista} = n.objectives / n.moons / n.lista."""
    out: dict[str, dict[str, int]] = {}
    for group in load_bingo_groups():
        if not isinstance(group, dict):
            continue
        word = _canon(group.get("id"), "grupo") or _slug(group.get("id"))
        if not word:
            continue
        n = group.get("n") if isinstance(group.get("n"), dict) else {}
        n_goal = int(n.get("objectives") or 0)
        if n_goal <= 0:
            n_goal = len(group.get("objectives") or [])
        n_luna = int(n.get("moons") or 0)
        if n_luna <= 0:
            n_luna = len(group.get("moons") or [])
        n_lista = int(n.get("lista") or 0)
        if n_lista <= 0 and _grupo_has_lista_pool(group):
            n_lista = len(group.get("lista") or [])
        # Si dos ids legacy caen en el mismo canónico, sumar (no debería).
        prev = out.get(word) or {"goal": 0, "luna": 0, "lista": 0}
        out[word] = {
            "goal": max(prev["goal"], n_goal),
            "luna": max(prev["luna"], n_luna),
            "lista": max(prev["lista"], n_lista),
        }
    return out


def _build_goal_list_counts() -> dict[str, int]:
    """Clave canónica de goal_lists → n ítems en lists[name]."""
    out: dict[str, int] = {}
    path = CATALOG_DIR / "goal_lists.json"
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


def _build_kingdom_n_items() -> dict[str, int]:
    """Reino → n_items de zonas_inventario (= goal_lists + binoculars por kingdom)."""
    out: dict[str, int] = {}
    path = CATALOG_DIR / "zonas_inventario.json"
    if not path.is_file():
        return out
    data = load_catalog(path)
    for block in data.get("zones") or []:
        if not isinstance(block, dict):
            continue
        default_k = str(block.get("kingdom") or "")
        for it in block.get("list") or []:
            if not isinstance(it, dict):
                continue
            kingdom = str(it.get("kingdom") or default_k)
            if not kingdom or str(it.get("source") or "") == "moon":
                continue
            out[kingdom] = out.get(kingdom, 0) + 1
    return out


def _build_capture_lista_counts() -> dict[str, int]:
    """Capturas con lista[] (p. ej. Binoculars) → n ubicaciones."""
    out: dict[str, int] = {}
    caps_path = CATALOG_DIR / "capturas_lunas.json"
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
        n = int((grupo_counts.get(word) or {}).get("lista") or 0)
        if n <= 0 and grupo_lista_computed:
            n = int(grupo_lista_computed.get(word) or 0)
        if n <= 0:
            n = int(goal_list_counts.get(word) or 0)
        if n <= 0 and word in capture_lista_counts:
            n = int(capture_lista_counts.get(word) or 0)
        return n
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


def _build_capture_sin_luna_captura_counts() -> dict[str, int]:
    """Capturas fuera del pool de 163 lunas: +1 por goal fija; binoculars → n_lista."""
    out: dict[str, int] = {}
    caps_path = CATALOG_DIR / "capturas_lunas.json"
    if not caps_path.is_file():
        return out
    for row in load_catalog(caps_path).get("captures") or []:
        if not isinstance(row, dict):
            continue
        word = _capture_row_palabra(row)
        if not word:
            continue
        n_moons = int(row.get("n_moons") or 0)
        if n_moons <= 0:
            n_moons = len(row.get("moons") or [])
        cap_id = int(row.get("id") or 0)
        n_obj = int(row.get("n_objectives") or 0)
        if n_obj <= 0:
            n_obj = len(row.get("objectives") or [])
        if n_moons > 0:
            continue
        n_lista = int(row.get("n_lista") or 0)
        if n_lista <= 0:
            n_lista = len(row.get("lista") or [])
        if n_lista > 0:
            out[word] = n_lista
            continue
        if n_obj > 0:
            out[word] = 1
    return out


def _build_per_capture_captura_counts() -> dict[str, int]:
    """46 slugs capturas_lunas → lunas del pool captures (Σ = n.moons del grupo)."""
    captures_group = next(
        (g for g in load_bingo_groups() if g.get("id") == CAPTURA_GRUPO_ID), None
    )
    if not captures_group:
        return {}
    pool_moons = _resolve_bingo_group_moons_raw(captures_group)
    pool = {_moon_key(m) for m in pool_moons}

    caps_path = CATALOG_DIR / "capturas_lunas.json"
    cap_rows = [
        r for r in load_catalog(caps_path).get("captures") or [] if isinstance(r, dict)
    ]
    capture_slugs = {_capture_row_palabra(r) for r in cap_rows}
    capture_slugs.discard(None)

    moon_to_word: dict[tuple[str, int], str] = {}
    for row in cap_rows:
        word = _capture_row_palabra(row)
        if not word:
            continue
        for moon in row.get("moons") or []:
            key = _moon_key(moon)
            if key in pool and key not in moon_to_word:
                moon_to_word[key] = word

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

    for moon in pool_moons:
        key = _moon_key(moon)
        if key in moon_to_word:
            continue
        orphan = _orphan_moon_capture_word(moon)
        if orphan:
            moon_to_word[key] = orphan

    counts: dict[str, int] = defaultdict(int)
    for word in moon_to_word.values():
        counts[word] += 1
    for row in cap_rows:
        word = _capture_row_palabra(row)
        if word:
            counts.setdefault(word, 0)
    return dict(counts)


def _build_standalone_capture_words() -> set[str]:
    """Slugs capturas_lunas sin id de grupo bingo propio (goal/luna vía capturas_lunas)."""
    grupo_ids = _build_grupo_ids()
    out: set[str] = set()
    caps_path = CATALOG_DIR / "capturas_lunas.json"
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
        n = group.get("n") if isinstance(group.get("n"), dict) else {}
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
    g = grupo_n or {}
    if g:
        n_luna = int(g.get("luna") or 0)
        n_goal = int(g.get("goal") or 0)
        n_lista = int(lista_n if lista_n is not None else g.get("lista") or 0)
    else:
        n_luna = int(n_ind.get("luna") or luna_for_tag or 0)
        n_goal = int(n_ind.get("goal") or 0)
        n_lista = int(lista_n or 0)
    out: dict[str, int] = {}
    for uso in usos:
        if uso == "bingo":
            out[uso] = bingo_n
        elif uso == "captura":
            out[uso] = int(captura_n)
        elif uso == "goal":
            out[uso] = n_goal
        elif uso == "luna":
            out[uso] = n_luna
        elif uso == "grupo":
            out[uso] = 1
        elif uso == "lista":
            out[uso] = n_lista
        elif uso == "tag":
            out[uso] = n_luna
        elif uso == "zona":
            out[uso] = 1
        else:
            out[uso] = 0
    return out

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


def _build_referencia_individual_counts() -> tuple[
    dict[str, int], dict[str, int], dict[str, int], dict[str, int]
]:
    """Por palabra: n goals / n lunas en referencia; captura→goals/lunas propias."""
    goal_counts: dict[str, int] = defaultdict(int)
    ref_path = CATALOG_DIR / "goals_referencia.json"
    ref_templates: set[str] = set()
    if ref_path.is_file():
        for goal in load_catalog(ref_path).get("goals") or []:
            if not isinstance(goal, dict):
                continue
            tmpl = str(goal.get("goal") or "").strip()
            if tmpl:
                ref_templates.add(tmpl)
            for token in _tokens_in_record(goal):
                goal_counts[token] += 1

    captura_goal_counts: dict[str, int] = defaultdict(int)
    capture_luna_counts: dict[str, int] = defaultdict(int)
    luna_counts: dict[str, int] = defaultdict(int)
    lunas_path = CATALOG_DIR / "lunas-objetivos.json"
    if lunas_path.is_file():
        for moon in load_catalog(lunas_path).get("moons") or []:
            if not isinstance(moon, dict):
                continue
            for token in _tokens_in_record(moon):
                luna_counts[token] += 1

    caps_path = CATALOG_DIR / "capturas_lunas.json"
    if caps_path.is_file():
        for row in load_catalog(caps_path).get("captures") or []:
            if not isinstance(row, dict):
                continue
            word = _capture_row_palabra(row)
            if not word:
                continue
            n_m = int(row.get("n_moons") or 0) or len(row.get("moons") or [])
            if n_m > 0:
                capture_luna_counts[word] += n_m
            for obj in row.get("objectives") or []:
                if not isinstance(obj, dict):
                    continue
                tmpl = str(obj.get("goal") or "").strip()
                if tmpl in ref_templates:
                    captura_goal_counts[word] += 1

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


def _collect_fixed_usos() -> dict[str, set[str]]:
    """Palabras y usos fijos 1:1 con catálogo fuente (sin goal/luna)."""
    out: dict[str, set[str]] = defaultdict(set)

    lineas_path = CATALOG_DIR / "bingo_lineas.json"
    if lineas_path.is_file():
        for group in load_catalog(lineas_path).get("groups") or []:
            _add(out, _canon(group.get("id"), "bingo"), "bingo")

    for group in load_bingo_groups():
        if not isinstance(group, dict):
            continue
        moon_tag = group.get("moon_tag") or group.get("tag")
        word = _canon(group.get("id"), "grupo", moon_tag=str(moon_tag) if moon_tag else None)
        _add(out, word, "grupo")

    tags_path = CATALOG_DIR / "tags_inventario.json"
    if tags_path.is_file():
        for row in load_catalog(tags_path).get("tags") or []:
            _add(out, _canon(row.get("tag"), "tag"), "tag")

    lists_path = CATALOG_DIR / "goal_lists.json"
    if lists_path.is_file():
        lists = load_catalog(lists_path).get("lists") or {}
        if isinstance(lists, dict):
            for name in lists:
                _add(out, _canon(name, "lista"), "lista")

    zonas_inv_path = CATALOG_DIR / "zonas_inventario.json"
    if zonas_inv_path.is_file():
        for row in load_catalog(zonas_inv_path).get("zones") or []:
            word = _canon(row.get("zone"), "zona") or _slug(row.get("zone"))
            if word:
                _add(out, word, "zona")

    grupo_ids = _build_grupo_ids()
    caps_path = CATALOG_DIR / "capturas_lunas.json"
    if caps_path.is_file():
        for row in load_catalog(caps_path).get("captures") or []:
            if isinstance(row, dict):
                word = _capture_row_palabra(row)
                if not word:
                    continue
                _add(out, word, "captura")
                n_lista = int(row.get("n_lista") or 0)
                if n_lista <= 0:
                    n_lista = len(row.get("lista") or [])
                if n_lista > 0:
                    _add(out, word, "lista")

    return out


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
    goal_tags: set[str] = set()
    ref_path = CATALOG_DIR / "goals_referencia.json"
    if ref_path.is_file():
        for goal in load_catalog(ref_path).get("goals") or []:
            if not isinstance(goal, dict):
                continue
            for t in goal.get("tags") or []:
                goal_tags.add(canonicalize_tag(str(t)))

    luna_tags: set[str] = set()
    lunas_path = CATALOG_DIR / "lunas-objetivos.json"
    if lunas_path.is_file():
        for moon in load_catalog(lunas_path).get("moons") or []:
            if not isinstance(moon, dict):
                continue
            for t in moon.get("tags") or []:
                luna_tags.add(canonicalize_tag(str(t)))

    captura_has_goal: dict[str, bool] = {}
    captura_has_luna: dict[str, bool] = {}
    caps_path = CATALOG_DIR / "capturas_lunas.json"
    if caps_path.is_file():
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
    out: dict[str, int] = {}
    if "grupo" in usos:
        return out
    if _is_capture_only_usos(usos, word, standalone_capture_words):
        if "goal" in usos:
            n_goal = int(captura_goal_counts.get(word) or 0)
            if n_goal > 0:
                out["goal"] = n_goal
        if "luna" in usos:
            n_luna = int(capture_luna_counts.get(word) or 0)
            if n_luna > 0:
                out["luna"] = n_luna
        return out
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
        if not (usos & set(USO_IDENTITY) or word in standalone_capture_words):
            continue
        if "grupo" in usos:
            continue
        if word in standalone_capture_words:
            if captura_has_goal.get(word):
                _add(out, word, "goal")
            if captura_has_luna.get(word):
                _add(out, word, "luna")
            continue
        keys = _lookup_keys_for_variable(word, usos)
        if "captura" in usos and captura_has_goal.get(word):
            _add(out, word, "goal")
        elif not _is_capture_only_usos(usos, word, standalone_capture_words) and keys & goal_tags:
            _add(out, word, "goal")
        if "captura" in usos and captura_has_luna.get(word):
            _add(out, word, "luna")
        elif not _is_capture_only_usos(usos, word, standalone_capture_words) and keys & luna_tags:
            _add(out, word, "luna")


def _apply_grupo_item_usos(
    out: dict[str, set[str]],
    grupo_counts: dict[str, dict[str, int]],
) -> None:
    """Si la palabra es grupo: goal/luna/lista según ítems del grupo."""
    for word, usos in list(out.items()):
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
    zones = load_catalog(CATALOG_DIR / "zonas_inventario.json")
    return {
        "grupo": len(load_bingo_groups()),
        "zona": len(zones.get("zones") or []),
    }


def _expected_palabra_fija_by_uso() -> dict[str, int]:
    """n_palabras esperado por uso de palabra fija (catálogo fuente)."""
    lineas = load_catalog(CATALOG_DIR / "bingo_lineas.json")
    tags = load_catalog(CATALOG_DIR / "tags_inventario.json")
    caps = load_catalog(CATALOG_DIR / "capturas_lunas.json")
    lists = load_catalog(CATALOG_DIR / "goal_lists.json").get("lists") or {}
    lista_words: set[str] = set()
    if isinstance(lists, dict):
        for name in lists:
            word = _canon(name, "lista") or _slug(name)
            if word:
                lista_words.add(word)
    for group in load_bingo_groups():
        if not isinstance(group, dict):
            continue
        word = _canon(group.get("id"), "grupo") or _slug(group.get("id"))
        if not word:
            continue
        n = group.get("n") if isinstance(group.get("n"), dict) else {}
        n_lista = int(n.get("lista") or 0)
        if n_lista <= 0 and _grupo_has_lista_pool(group):
            n_lista = len(group.get("lista") or [])
        if n_lista > 0:
            lista_words.add(word)
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
    captura_counts = _build_per_capture_captura_counts()
    captura_sin_luna = _build_capture_sin_luna_captura_counts()
    n_captura = sum(
        1
        for word in captura_counts
        if int(captura_counts.get(word) or 0) > 0
        or int(captura_sin_luna.get(word) or 0) > 0
    )
    return {
        "bingo": len(lineas.get("groups") or []),
        "captura": n_captura,
        "grupo": len(load_bingo_groups()),
        "lista": len(lista_words),
        "tag": len(tags.get("tags") or []),
        "zona": len(load_catalog(CATALOG_DIR / "zonas_inventario.json").get("zones") or []),
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
    rows: list[dict] = []
    uso_counts: dict[str, int] = {u: 0 for u in USO_ORDER}
    n_individual_bingo = 0
    n_individual_captura = 0
    n_individual_goal = 0
    n_individual_luna = 0
    n_individual_lista = 0
    n_individual_tag = 0
    for i, word in enumerate(words, 1):
        usos = [u for u in USO_ORDER if u in usos_by[word]]
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
        luna_for_tag = 0
        if "tag" in usos and "luna" not in n_ind and "grupo" not in usos:
            luna_for_tag = _lookup_individual_count(
                word, usos_by[word], luna_counts
            )
        bingo_n = _lookup_bingo_count(word, bingo_counts) if "bingo" in usos else 0
        grupo_n = grupo_counts.get(word) if "grupo" in usos else None
        lista_n: int | None = None
        if "lista" in usos_by[word]:
            lista_n = _resolve_lista_n(
                word,
                usos_by[word],
                grupo_counts=grupo_counts,
                goal_list_counts=goal_list_counts,
                capture_lista_counts=capture_lista_counts,
                grupo_lista_computed=grupo_lista_computed,
            )
        captura_n = 0
        if "captura" in usos_by[word]:
            captura_n = int(captura_counts.get(word) or 0) + int(
                captura_sin_luna.get(word) or 0
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
        # No emitir usos con n=0 (p. ej. captura huérfana de pool / lista vacía).
        usos_fmt = {u: n for u, n in usos_fmt.items() if n != 0}
        if not usos_fmt:
            continue
        # Si se omitió captura/lista a 0, alinear usos_by para validaciones.
        usos_by[word] = set(usos_fmt)
        parsed = parse_usos(usos_fmt)
        n_usos = sum(parsed.values())
        n_individual_bingo += parsed.get("bingo", 0)
        n_individual_captura += parsed.get("captura", 0)
        n_individual_goal += parsed.get("goal", 0)
        n_individual_luna += parsed.get("luna", 0)
        n_individual_lista += parsed.get("lista", 0)
        n_individual_tag += parsed.get("tag", 0)
        rows.append(
            {
                "id": i,
                "palabra": word,
                "n_usos": n_usos,
                "usos": usos_fmt,
            }
        )
    uso_counts["bingo"] = n_individual_bingo
    uso_counts["captura"] = n_individual_captura
    uso_counts["goal"] = n_individual_goal
    uso_counts["luna"] = n_individual_luna
    uso_counts["lista"] = n_individual_lista
    uso_counts["tag"] = n_individual_tag
    expected_fixed = _expected_fixed_uso_counts()
    for uso in USO_FIJO_WORD_COUNT:
        got = uso_counts[uso]
        want = expected_fixed[uso]
        if got != want:
            raise ValueError(
                f"n_by_uso[{uso!r}]={got} != {want} (catálogo fuente)"
            )
    lineas = load_catalog(CATALOG_DIR / "bingo_lineas.json")
    want_bingo = sum(
        int(g.get("n_goals") or 0) for g in lineas.get("groups") or []
    )
    if n_individual_bingo != want_bingo:
        raise ValueError(
            f"n_by_uso['bingo']={n_individual_bingo} != bingo_lineas Σ n_goals ({want_bingo})"
        )
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
    tag_luna_sum = sum(
        parse_usos(r["usos"]).get("luna", 0)
        for r in rows
        if "tag" in parse_usos(r["usos"])
    )
    if n_individual_tag != tag_luna_sum:
        raise ValueError(
            f"n_by_uso['tag']={n_individual_tag} != luna en filas con tag ({tag_luna_sum})"
        )
    want_captura = _expected_captura_total()
    if n_individual_captura != want_captura:
        moon_pool = _build_captura_grupo_moon_count()
        sin_luna = sum(_build_capture_sin_luna_captura_counts().values())
        raise ValueError(
            f"n_by_uso['captura']={n_individual_captura} != "
            f"pool captures ({moon_pool}) + sin luna ({sin_luna}) = {want_captura}"
        )
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
    for row in rows:
        parsed = parse_usos(row["usos"])
        if row["n_usos"] != sum(parsed.values()):
            raise ValueError(
                f"{row['palabra']!r}: n_usos={row['n_usos']} != sum(usos)"
            )
        for var in USO_SUM:
            if var in parsed and parsed[var] <= 0:
                raise ValueError(
                    f"{row['palabra']!r}: uso {var!r} sin conteo individual"
                )
        for uso, n in parsed.items():
            if uso in USO_FIJO_ZERO and n != 0:
                raise ValueError(
                    f"{row['palabra']!r}: uso fijo {uso!r} debe ser 0"
                )
            if uso == "grupo" and n != 1:
                raise ValueError(f"{row['palabra']!r}: grupo debe ser 1")
            if uso == "zona" and n != 1:
                raise ValueError(f"{row['palabra']!r}: zona debe ser 1")
            if uso == "lista" and n <= 0:
                raise ValueError(f"{row['palabra']!r}: lista debe ser > 0")
            if uso == "tag" and n <= 0:
                raise ValueError(f"{row['palabra']!r}: tag debe ser > 0")
            if uso == "tag" and "luna" in parsed and n != parsed["luna"]:
                raise ValueError(f"{row['palabra']!r}: tag debe igualar luna")
        if "lista" in parsed:
            if "grupo" in parsed:
                want_lista_n = _resolve_lista_n(
                    row["palabra"],
                    set(parsed),
                    grupo_counts=grupo_counts,
                    goal_list_counts=goal_list_counts,
                    capture_lista_counts=capture_lista_counts,
                    grupo_lista_computed=grupo_lista_computed,
                )
                if parsed["lista"] != want_lista_n:
                    raise ValueError(
                        f"{row['palabra']!r}: lista de grupo debe ser {want_lista_n}"
                    )
            elif row["palabra"] in capture_lista_counts:
                want_cap_lista = int(capture_lista_counts.get(row["palabra"]) or 0)
                if parsed["lista"] != want_cap_lista:
                    raise ValueError(
                        f"{row['palabra']!r}: lista de captura debe ser "
                        f"n_lista ({want_cap_lista})"
                    )
            elif parsed["lista"] != int(
                goal_list_counts.get(row["palabra"]) or 0
            ):
                raise ValueError(
                    f"{row['palabra']!r}: lista debe ser len(goal_lists)"
                )
        if "grupo" in parsed:
            g = grupo_counts.get(row["palabra"]) or {}
            if "goal" in parsed and parsed["goal"] != int(g.get("goal") or 0):
                raise ValueError(
                    f"{row['palabra']!r}: goal de grupo debe ser n.objectives"
                )
            if "luna" in parsed and parsed["luna"] != int(g.get("luna") or 0):
                raise ValueError(
                    f"{row['palabra']!r}: luna de grupo debe ser n.moons"
                )
    n_palabras_by_uso = {u: 0 for u in USO_ORDER}
    for row in rows:
        for u in parse_usos(row["usos"]):
            n_palabras_by_uso[u] += 1
    for uso in USO_FIJO:
        if uso_counts[uso] != n_palabras_by_uso[uso]:
            raise ValueError(
                f"uso valor fijo {uso!r}: n_by_uso={uso_counts[uso]} != "
                f"n_palabras={n_palabras_by_uso[uso]}"
            )
    expected_fija = _expected_palabra_fija_by_uso()
    for uso in USO_PALABRA_FIJA:
        got = n_palabras_by_uso[uso]
        want = expected_fija[uso]
        if got != want:
            raise ValueError(
                f"n_palabras_by_uso[{uso!r}]={got} != catálogo fuente ({want})"
            )
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
