"""Helpers de rangos progresivos (e/m/l/n) para goals numericas.

Solo expone funciones reutilizables (reasonable_range, format_step,
list_candidates, SINGLE_VALUE_OK) que importan otros scripts del repo
(fix_bingo_group_ranges.py, etc.). No es un CLI: no escribe nada en catalog/.

Si en el futuro hace falta re-analizar rangos contra catalogos por reino o
contra Combined oficial, reconstruir aqui un subcomando puntual — evitar
dejar ese analisis corriendo por defecto (sus salidas no son catalogo activo).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# reasonable_ranges: valores progresivos con paso uniforme y sensato.
# ---------------------------------------------------------------------------

NICE_STEPS = {1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20}

STEP_SCORE = {
    4: 12,
    2: 11,
    3: 10,
    5: 9,
    6: 7,
    8: 6,
    10: 5,
    12: 4,
    1: 2,
}


def is_reasonable(values: list[int]) -> bool:
    if len(values) < 2:
        return True
    if values != sorted(values) or len(set(values)) < len(values):
        return False
    steps = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    return len(set(steps)) == 1 and steps[0] > 0


def harmony_score(start: int, step: int, values: list[int]) -> int:
    """Score how well the step fits the starting value and resulting sequence."""
    score = 0

    if step > 0 and start % step == 0 and all(v % step == 0 for v in values):
        score += 35

    if step == 4 and start % 4 != 0:
        score -= 40

    if step == 5 and start % 5 != 0:
        score -= 25

    if start % 2 == 1:
        if step in (2, 3):
            score += 18
        if step in (4, 6, 8):
            score -= 12
    else:
        if step in (2, 4):
            score += 12

    if start == step:
        score += 15

    if step > 0 and start % step == 0:
        score += 8

    if all(v % 2 == start % 2 for v in values):
        score += 4

    if start % 2 == 0 and all(v % 2 == 0 for v in values):
        score += 4

    return score


def option_key(start: int, step: int, values: list[int], lo_cap: int) -> tuple:
    anchored = (
        start == lo_cap
        and step > 0
        and start % step == 0
        and all(v % step == 0 for v in values)
    )
    return (
        1 if anchored else 0,
        harmony_score(start, step, values),
        start,
        STEP_SCORE.get(step, 0),
        values[-1],
    )


def iter_valid_options(maxima: list[int]) -> list[tuple[list[int], int, int]]:
    n = len(maxima)
    if n < 2:
        return []

    lo_cap, hi_cap = maxima[0], maxima[-1]
    options: list[tuple[tuple, list[int], int, int]] = []
    seen: set[tuple[int, ...]] = set()

    for start in range(lo_cap, 0, -1):
        max_step = max(1, (hi_cap - start) // (n - 1))
        for step in range(1, max_step + 1):
            values = [start + i * step for i in range(n)]
            if values[-1] > hi_cap:
                continue
            if any(values[i] > maxima[i] for i in range(n)):
                continue
            if len(set(values)) < n:
                continue
            key = tuple(values)
            if key in seen:
                continue
            seen.add(key)
            options.append((option_key(start, step, values, lo_cap), values, start, step))

    options.sort(reverse=True)
    return [(values, start, step) for _, values, start, step in options]


def reasonable_range(maxima: list[int]) -> list[int]:
    """Derive ascending values with a constant step from per-tier cumulative caps."""
    if not maxima:
        return []
    if any(m < 0 for m in maxima):
        raise ValueError(f"maxima must be non-negative: {maxima}")

    n = len(maxima)
    if n == 1:
        return [maxima[0]] if maxima[0] > 0 else []

    options = iter_valid_options(maxima)
    if options:
        return options[0][0]

    lo_cap, hi_cap = maxima[0], maxima[-1]
    if lo_cap == hi_cap:
        return [lo_cap]
    step = max(1, round((hi_cap - lo_cap) / (n - 1)))
    values = [min(maxima[i], lo_cap + i * step) for i in range(n)]
    for i in range(1, n):
        values[i] = max(values[i], values[i - 1] + 1)
        values[i] = min(values[i], maxima[i])
    return values


def list_candidates(maxima: list[int], limit: int = 5) -> list[tuple[list[int], int]]:
    options = iter_valid_options(maxima)
    return [(values, step) for values, _start, step in options[:limit]]


def format_step(values: list[int]) -> str:
    if len(values) < 2:
        return ""
    step = values[1] - values[0]
    if all(values[i + 1] - values[i] == step for i in range(len(values) - 1)):
        return f"+{step}"
    return "irregular"


SINGLE_VALUE_OK = {
    # Goals con umbral fijo: un valor en range[] (p. ej. [1]) o pocos escalones
    # distintos (checkpoints). No interpolar a 4 umbrales distintos.
    "{{X}} Dog Moon[[s]]",
    "{{X}} Luncheon Volbonan Moons",
    "{{X}} Metro Taxi Moons",
    "{{X}} Metro RC Car Moons",
    "{{X}} Snow Bitefrost Moons",
    "{{X}} Cap Checkpoints",
    "{{X}} Cascade Checkpoints",
    "{{X}} Lake Checkpoints",
    "{{X}} Seed Moon (No Time Travel)",
    "{{X}} Metro Outfit Door Moons",
    "{{X}} Snow Outfit Door Moons",
    "{{X}} Luncheon Outfit Door Moons",
    "{{X}} Bowser's Outfit Door Moons",
    "{{X}} Moon Checkpoints",
    "{{X}} Lost Checkpoints",
    "{{X}} Lost Butterfly Moons",
    "{{X}} Wooded Flower Road Moons",
    "All Regional Coins in {{X}} Large Kingdom",
}

