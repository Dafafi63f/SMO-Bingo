"""Regeneración incremental del pipeline de Catalog/.

Guarda huellas (blake2b) de entradas/salidas por paso en Files/.regenerate_state.json.
Si nada relevante cambió desde la última corrida, se omiten pasos (y sus dependientes).
``stamp_combined`` corre siempre (fecha del nombre); solo ensucia el pipeline si renombra.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FILES_DIR = Path(__file__).resolve().parent
ROOT = FILES_DIR.parent
STATE_PATH = FILES_DIR / ".regenerate_state.json"
STATE_VERSION = 1

# Glob relativo a ROOT (forward slashes).
_COMBINED_GLOB = "Bingos/Super Mario Odyssey-Combined-*.json"
_CATALOG_GOAL_LISTS = "Catalog/goal_lists.json"
_CATALOG_GOALS_REFERENCIA = "Catalog/goals_referencia.json"
_CATALOG_ZONAS_INVENTARIO = "Catalog/zonas_inventario.json"
_EXPORT_LUNAS_TAGS = "Files/export_lunas_tags.py"

_SHARED_LIBS = (
    "Files/catalog_lib.py",
    "Files/goal_list_lib.py",
    "Files/mariowiki_guides.py",
    "Files/ranges_tools.py",
    "Catalog/project.json",
    _CATALOG_GOAL_LISTS,
    "Catalog/mariowiki_capture_guides.json",
)


def _file_digest(path: Path) -> str:
    h = hashlib.blake2b(digest_size=16)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _expand_input_pattern(pattern: str) -> list[Path]:
    if any(ch in pattern for ch in "*?[]"):
        return sorted(p for p in ROOT.glob(pattern) if p.is_file())
    path = ROOT / pattern
    return [path] if path.is_file() else []


def fingerprint_paths(
    patterns: tuple[str, ...],
    cache: dict[str, str] | None = None,
) -> dict[str, str]:
    """{ruta_relativa_posix: digest} para todos los paths que existen."""
    out: dict[str, str] = {}
    for pattern in patterns:
        for path in _expand_input_pattern(pattern):
            rel = path.relative_to(ROOT).as_posix()
            if cache is not None and rel in cache:
                digest = cache[rel]
            else:
                digest = _file_digest(path)
                if cache is not None:
                    cache[rel] = digest
            out[rel] = digest
    return dict(sorted(out.items()))


def outputs_ready(outputs: tuple[str, ...]) -> bool:
    for pattern in outputs:
        if not _expand_input_pattern(pattern):
            return False
    return True


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"version": STATE_VERSION, "steps": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": STATE_VERSION, "steps": {}}
    if data.get("version") != STATE_VERSION:
        return {"version": STATE_VERSION, "steps": {}}
    data.setdefault("steps", {})
    return data


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


@dataclass(frozen=True)
class RegenerateStep:
    id: str
    label: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    run: Callable[[], int]
    always: bool = False


def step_input_fingerprint(
    step: RegenerateStep, cache: dict[str, str] | None = None
) -> dict[str, str]:
    fps = fingerprint_paths(step.inputs, cache)
    for out in step.outputs:
        fps.pop(out, None)
    return fps


def step_needs_run(
    step: RegenerateStep,
    *,
    state: dict[str, Any],
    force: bool,
    upstream_dirty: bool,
    fp_cache: dict[str, str] | None = None,
) -> tuple[bool, str]:
    if step.always:
        return True, "always"
    if force:
        return True, "--force"
    if upstream_dirty:
        return True, "upstream"
    if not outputs_ready(step.outputs):
        return True, "missing output"
    prev = (state.get("steps") or {}).get(step.id) or {}
    prev_inputs = prev.get("inputs") or {}
    current_inputs = step_input_fingerprint(step, fp_cache)
    if not prev_inputs:
        return True, "no prior state"
    if current_inputs != prev_inputs:
        # Diff mínimo para el log.
        changed = [
            k
            for k in sorted(set(current_inputs) | set(prev_inputs))
            if current_inputs.get(k) != prev_inputs.get(k)
        ]
        hint = changed[0] if len(changed) == 1 else f"{len(changed)} files"
        return True, f"inputs changed ({hint})"
    return False, "up to date"


def record_step_success(
    step: RegenerateStep,
    state: dict[str, Any],
    fp_cache: dict[str, str] | None = None,
) -> None:
    steps = state.setdefault("steps", {})
    steps[step.id] = {
        "inputs": step_input_fingerprint(step, fp_cache),
        "outputs": fingerprint_paths(step.outputs, fp_cache),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _run_stamp_combined() -> int:
    from catalog_lib import stamp_combined_filename_today

    print(stamp_combined_filename_today().name)
    return 0


def _run_sync_objective_moon_groups() -> int:
    from sync_objective_moon_groups import sync_objective_moon_groups

    counts = sync_objective_moon_groups()
    print(f"Grupos actualizados: {len(counts)}")
    return 0


def _run_sync_kingdom_groups() -> int:
    from catalog_lib import sync_kingdom_groups

    print(f"kingdom groups: {sync_kingdom_groups()}")
    return 0


def _run_progression() -> int:
    from apply_progression_accessibility import main as progression_main

    progression_main()
    return 0


def _run_combined_meta() -> int:
    from export_combined_meta import export_icons, export_lineas, export_tooltips

    export_lineas()
    export_icons()
    export_tooltips()
    return 0


def _run_capturas_lunas() -> int:
    from export_capturas_lunas import main as capturas_main

    capturas_main()
    return 0


def _run_lunas_only() -> int:
    from export_lunas_tags import export_lunas

    export_lunas()
    return 0


def _run_goals_referencia() -> int:
    from export_goals_referencia import main as ref_main

    ref_main()
    return 0


def _run_goals_individuales() -> int:
    from export_goals_individuales import main as ind_main

    ind_main()
    return 0


def _run_zonas_inventario() -> int:
    from export_zonas_inventario import main as zonas_main

    return zonas_main()


def _run_tags_only() -> int:
    from export_lunas_tags import export_tags

    export_tags()
    return 0


def _run_enrich_goals_referencia() -> int:
    from enrich_goals_referencia import enrich_referencia_with_individuales

    n = enrich_referencia_with_individuales()
    print(f"Enriquecido goals_referencia.json: individuales[] en {n} templates")
    return 0


def _run_palabras_inventario() -> int:
    from export_palabras_inventario import main as palabras_main

    return palabras_main()


def _run_items_goals() -> int:
    from export_items_goals import main as items_goals_main

    return items_goals_main()


def _run_clear_caches() -> int:
    from catalog_lib import clear_runtime_caches

    clear_runtime_caches()
    print("ok")
    return 0


def build_steps() -> list[RegenerateStep]:
    libs = _SHARED_LIBS
    combined = (_COMBINED_GLOB,)
    bingo = ("Catalog/bingo_groups.json",)
    capturas = ("Catalog/capturas_lunas.json",)
    lunas = ("Catalog/lunas-objetivos.json", "Catalog/lunas-objetivos.csv")
    ref = (_CATALOG_GOALS_REFERENCIA,)
    ind = ("Catalog/goals_individuales.json",)
    tags = ("Catalog/tags_inventario.json",)
    palabras = ("Catalog/palabras_inventario.json",)
    meta_out = (
        "Catalog/bingo_lineas.json",
        "Catalog/goal_icons.json",
        "Catalog/goal_tooltips.json",
    )
    zonas_out = (_CATALOG_ZONAS_INVENTARIO,)
    items_goals_out = ("Catalog/items_goals.json",)
    palabras_inputs = (
        "Catalog/bingo_groups.json",
        "Catalog/bingo_lineas.json",
        "Catalog/capturas_lunas.json",
        _CATALOG_GOALS_REFERENCIA,
        "Catalog/goals_individuales.json",
        _CATALOG_GOAL_LISTS,
        "Catalog/lunas-objetivos.json",
        "Catalog/tags_inventario.json",
        _CATALOG_ZONAS_INVENTARIO,
        "Files/export_palabras_inventario.py",
    ) + libs

    return [
        RegenerateStep(
            "stamp_combined",
            "stamp Combined filename (fecha hoy)",
            combined,
            combined,
            _run_stamp_combined,
            always=True,
        ),
        RegenerateStep(
            "sync_objective_moon_groups",
            "sync objective moon groups",
            combined + bingo + ("Files/sync_objective_moon_groups.py",) + libs,
            bingo,
            _run_sync_objective_moon_groups,
        ),
        RegenerateStep(
            "sync_kingdom_groups",
            "sync kingdom groups",
            combined + bingo + libs,
            bingo,
            _run_sync_kingdom_groups,
        ),
        RegenerateStep(
            "progression",
            "progression + bingo_groups + sort Combined",
            combined
            + bingo
            + ("Files/apply_progression_accessibility.py",)
            + libs,
            combined + bingo,
            _run_progression,
        ),
        RegenerateStep(
            "combined_meta",
            "combined meta (lineas/icons/tooltips)",
            combined + ("Files/export_combined_meta.py",) + libs,
            meta_out,
            _run_combined_meta,
        ),
        RegenerateStep(
            "capturas_lunas",
            "capturas_lunas",
            bingo + ("Files/export_capturas_lunas.py", "Files/fill_captures_cappy.py")
            + libs,
            capturas,
            _run_capturas_lunas,
        ),
        RegenerateStep(
            "lunas_objetivos",
            "lunas-objetivos",
            bingo + capturas + tags + (_EXPORT_LUNAS_TAGS,) + libs,
            lunas,
            _run_lunas_only,
        ),
        RegenerateStep(
            "goals_referencia",
            "goals_referencia",
            combined + bingo + ("Files/export_goals_referencia.py",) + libs,
            ref,
            _run_goals_referencia,
        ),
        RegenerateStep(
            "goals_individuales",
            "goals_individuales",
            combined + ref + ("Files/export_goals_individuales.py",) + libs,
            ind,
            _run_goals_individuales,
        ),
        RegenerateStep(
            "zonas_inventario",
            "zonas_inventario",
            bingo + ref + ("Files/export_zonas_inventario.py",) + libs,
            zonas_out,
            _run_zonas_inventario,
        ),
        RegenerateStep(
            "items_goals",
            "items_goals",
            (
                _CATALOG_GOALS_REFERENCIA,
                _CATALOG_GOAL_LISTS,
                _CATALOG_ZONAS_INVENTARIO,
                "Files/export_items_goals.py",
                "Files/export_zonas_inventario.py",
            )
            + libs,
            items_goals_out,
            _run_items_goals,
        ),
        RegenerateStep(
            "tags_inventario",
            "tags_inventario",
            bingo + ref + (_EXPORT_LUNAS_TAGS,) + libs,
            tags,
            _run_tags_only,
        ),
        RegenerateStep(
            "lunas_retag",
            "lunas-objetivos (retag)",
            bingo + capturas + tags + (_EXPORT_LUNAS_TAGS,) + libs,
            lunas,
            _run_lunas_only,
        ),
        RegenerateStep(
            "goals_referencia_retag",
            "goals_referencia (retag)",
            combined + bingo + tags + ("Files/export_goals_referencia.py",) + libs,
            ref,
            _run_goals_referencia,
        ),
        RegenerateStep(
            "goals_individuales_retag",
            "goals_individuales (retag)",
            combined + ref + tags + ("Files/export_goals_individuales.py",) + libs,
            ind,
            _run_goals_individuales,
        ),
        RegenerateStep(
            "enrich_goals_referencia",
            "enrich goals_referencia hub",
            ref + ind + ("Files/enrich_goals_referencia.py",) + libs,
            ref,
            _run_enrich_goals_referencia,
        ),
        RegenerateStep(
            "palabras_inventario",
            "palabras_inventario",
            palabras_inputs,
            palabras,
            _run_palabras_inventario,
        ),
        RegenerateStep(
            "clear_caches",
            "clear caches",
            (),
            (),
            _run_clear_caches,
            always=False,
        ),
    ]


def is_first_run(state: dict[str, Any]) -> bool:
    """True si no hay estado de pasos previo (primera corrida → todo el pipeline)."""
    return not (state.get("steps") or {})


def _maybe_print_first_run(state: dict[str, Any], *, force: bool, dry_run: bool) -> None:
    if is_first_run(state) and not force and not dry_run:
        print(
            "Primera corrida (sin .regenerate_state.json): "
            "pipeline completo; las siguientes serán incrementales."
        )


def _step_run_needs(
    step: RegenerateStep,
    *,
    state: dict[str, Any],
    force: bool,
    dirty: bool,
    fp_cache: dict[str, str],
) -> tuple[bool, str]:
    needs, reason = step_needs_run(
        step,
        state=state,
        force=force,
        upstream_dirty=dirty,
        fp_cache=fp_cache,
    )
    if step.id == "clear_caches" and not dirty and not force:
        return False, "nothing changed"
    return needs, reason


def _dry_run_would_dirty(step: RegenerateStep) -> bool:
    if step.id != "stamp_combined":
        return True
    from datetime import date

    from catalog_lib import COMBINED_NAME_PREFIX, discover_combined_path

    today_name = f"{COMBINED_NAME_PREFIX}{date.today().isoformat()}.json"
    return discover_combined_path().name != today_name


def _combined_path_before_step(step: RegenerateStep) -> Path | None:
    if step.id != "stamp_combined":
        return None
    from catalog_lib import discover_combined_path

    return discover_combined_path().resolve()


def _step_success_marks_dirty(step: RegenerateStep, before_combined: Path | None) -> bool:
    if step.id != "stamp_combined":
        return True
    from catalog_lib import discover_combined_path

    after_combined = discover_combined_path().resolve()
    return before_combined is None or before_combined != after_combined


def _execute_pipeline_step(
    step: RegenerateStep,
    *,
    state: dict[str, Any],
    fp_cache: dict[str, str],
) -> tuple[int | None, bool]:
    """Ejecuta un paso. Devuelve (exit_code si falla, marca dirty)."""
    t0 = time.perf_counter()
    before_combined = _combined_path_before_step(step)
    try:
        code = int(step.run() or 0)
    except Exception as exc:
        print(f"  ERROR: {exc}", flush=True)
        return 1, False
    elapsed = time.perf_counter() - t0
    if code != 0:
        print(f"  FALLO ({code}) tras {elapsed:.1f}s")
        return code, False
    record_step_success(step, state, fp_cache)
    save_state(state)
    print(f"  ok ({elapsed:.1f}s)")
    return None, _step_success_marks_dirty(step, before_combined)


def run_pipeline(
    *,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[int, int, int, int]:
    """Ejecuta el pipeline. Devuelve (exit_code, ran, skipped, total)."""
    steps = build_steps()
    state = load_state()
    fp_cache: dict[str, str] = {}
    dirty = False
    ran = 0
    skipped = 0
    total = len(steps)

    _maybe_print_first_run(state, force=force, dry_run=dry_run)

    for step in steps:
        needs, reason = _step_run_needs(
            step, state=state, force=force, dirty=dirty, fp_cache=fp_cache
        )

        if not needs:
            skipped += 1
            print(f"\n=== {step.label} ===")
            print(f"  omitido ({reason})")
            continue

        print(f"\n=== {step.label} ===")
        if dry_run:
            print(f"  ejecutaría ({reason})")
            dirty = dirty or _dry_run_would_dirty(step)
            ran += 1
            continue

        exit_code, step_dirty = _execute_pipeline_step(
            step, state=state, fp_cache=fp_cache
        )
        if exit_code is not None:
            return exit_code, ran, skipped, total
        dirty = dirty or step_dirty
        ran += 1

    if not dry_run and ran:
        save_state(state)
    return 0, ran, skipped, total
