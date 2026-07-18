#!/usr/bin/env python3
"""Checked property: neither a fabricator (C1) nor a format-compliant empty
shell (C2) can outrank an honest report with substance.

Imports the composition from src.eval.decidable_scorer (single source of
truth; compose_truth returns (truth, quality, floors)) and verifies the
claim three ways:

  1. linear gate (C1): the default is exactly truth = reach * quality. A zero
     gate collapses any quality to zero, and the score is monotone in both
     inputs. Alternative exponents are sensitivity settings, not headline
     operating points.

  3. shell assertion (C2, FORMULA_LOCK K6): a zero-substance shell
     (fact=pof=comp=0) with one real reachable citation (reach=1) and perfect
     format compliance (spec=1) must score truth=0 -- strictly below every
     honest reference with any substance. Under K6 (spec out of truth,
     floor-if-active) quality collapses to 0; the old four-axis K0 gave the
     shell truth 0.145 and FAILED this check.

Exits nonzero listing violations, so this file doubles as a regression test.

Run:  python3 scripts/verify_gate_theorem.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.decidable_scorer import (  # noqa: E402
    EPS_FLOOR, GAMMA_DEFAULT, QUALITY_WEIGHTS, compose_truth,
)

Q_FLOOR_MIN = EPS_FLOOR * sum(QUALITY_WEIGHTS.values())  # all axes at floor


def truth(reach, fact, pof, comp, spec, gamma=GAMMA_DEFAULT) -> float:
    t, _quality, _floors = compose_truth(reach, fact, pof, comp, spec,
                                         gamma=gamma)
    return t


def analytic_frontier() -> None:
    print("== analytic sensitivity bound (formula imported, not mirrored) ==")
    print(f"truth = reach**gamma * quality; quality in "
          f"[{Q_FLOOR_MIN:.3f}, 1.0] (axes floored at {EPS_FLOOR}, "
          f"weights {QUALITY_WEIGHTS})")
    print("fabricator ceiling: truth_f <= Rf**gamma      (quality <= 1)")
    print("honest floor:       truth_h >= Rh**gamma * Qh")
    print("gate holds iff      Rf < Rh * Qh**(1/gamma)\n")
    print(f"{'gamma':>6s} {'Rh':>5s} {'Qh':>5s} {'max tolerable Rf':>17s}")
    for gamma in (1.0, 1.5, 2.0):
        for rh in (0.7, 0.8, 0.9):
            for qh in (0.3, 0.5, 0.7):
                rf_max = rh * qh ** (1.0 / gamma)
                print(f"{gamma:6.1f} {rh:5.2f} {qh:5.2f} {rf_max:17.3f}")
    print("\nheadline reading: gamma=1.0 is direct multiplication. The other "
          "rows disclose how an optional nonlinear sensitivity setting would "
          "move the comparison frontier; they do not select a default.")


def linear_gate_assertion() -> list[str]:
    """Lock the properties actually guaranteed by the headline formula."""
    print("\n== C1 linear-gate assertion ==")
    violations: list[str] = []
    if GAMMA_DEFAULT != 1.0:
        violations.append(f"headline gamma is {GAMMA_DEFAULT}, expected 1.0")
    grid = (0.0, 0.01, 0.2, 0.5, 0.9, 1.0)
    previous_by_quality = {q: -1.0 for q in grid}
    for reach in grid:
        for quality in grid:
            # Equal axes make the weighted quality exactly `quality` because
            # the declared weights sum to one.
            actual = truth(reach, quality, quality, quality, 0.0)
            expected = reach * quality
            if abs(actual - expected) > 1e-12:
                violations.append(
                    f"reach={reach}, quality={quality}: {actual} != {expected}")
            if actual + 1e-12 < previous_by_quality[quality]:
                violations.append(
                    f"non-monotone in reach at quality={quality}: {actual}")
            previous_by_quality[quality] = actual
    for reach in grid:
        values = [truth(reach, q, q, q, 0.0) for q in grid]
        if any(b + 1e-12 < a for a, b in zip(values, values[1:])):
            violations.append(f"non-monotone in quality at reach={reach}")
    return violations


def shell_assertion() -> list[str]:
    """C2 (FORMULA_LOCK K6): a format-compliant zero-substance shell must score
    truth=0 and fall strictly below every honest reference with substance."""
    print("== C2 empty-shell assertion (FORMULA_LOCK K6) ==")
    honest_refs = [
        (0.90, 0.60, 0.60, 0.30, 1.00),
        (0.80, 0.50, 0.50, 0.25, 0.50),
        (0.70, 0.40, 0.45, 0.20, 1.00),
        # thin-but-real: the honest champion profile (fact=0 but pof/comp>0)
        (0.99, 0.00, 0.12, 0.05, 0.62),
    ]
    violations: list[str] = []
    for gamma in (1.0, 1.5, 2.0):
        # shell: zero substance, one real reachable citation, perfect format
        shell = truth(1.00, 0.00, 0.00, 0.00, 1.00, gamma=gamma)
        print(f"  gamma={gamma}: shell(reach=1,fact=pof=comp=0,spec=1) "
              f"truth={shell:.6f}")
        if shell != 0.0:
            violations.append(
                f"gamma={gamma}: empty shell truth={shell:.6f} != 0 (C2)")
        for ref in honest_refs:
            th = truth(*ref, gamma=gamma)
            if th > 0 and shell >= th:
                violations.append(
                    f"gamma={gamma}: shell {shell:.6f} >= honest-with-"
                    f"substance {th:.6f} {ref} (C2)")
    return violations


# Panel honest medians (macro truth of substantive honest agents) on the
# D4-cleaned v22 boards (boards_fixed/truth_board_{backbone}_v22.json,
# PYTHONHASHSEED=0). The mini-shell corner is checked against the TIGHTER
# (qwen) median so the assertion binds on both panels.
PANEL_HONEST_MEDIANS = {"deepseek-v4-flash": 0.0378, "qwen3-8b": 0.0146}


def mini_shell_assertion() -> list[str]:
    """C2-strengthened (D1): a MINI-SHELL that only grazes each quality axis
    (raw 0.001-0.01) with one real reachable citation (reach=1) must NOT outrank
    the panel's honest median. Under the abolished FLOOR-IF-ACTIVE (eps=0.05)
    every such graze was lifted to 0.05, giving truth=0.05 -- above both panels'
    honest medians and beating 9-10/12 real systems. With no floor (EPS_FLOOR=0)
    the cheap mini-shell scores its earned value (<=0.01) and falls below the
    median. The all-0.05 corner (a report that genuinely earned 0.05 on every
    axis) is floor-independent and a reach-gaming question, out of D1 scope."""
    print("\n== C2-strengthened mini-shell assertion (D1, floor abolished) ==")
    graze = (0.001, 0.01)
    tight_median = min(PANEL_HONEST_MEDIANS.values())
    violations: list[str] = []
    print(f"  EPS_FLOOR={EPS_FLOOR}; tightest panel honest median={tight_median} "
          f"(qwen v22)")
    for gamma in (1.0, 1.5, 2.0):
        worst = 0.0
        for f in graze:
            for p in graze:
                for c in graze:
                    t = compose_truth(1.0, f, p, c, 0.0, gamma=gamma, eps=0.0)[0]
                    worst = max(worst, t)
        floored = compose_truth(1.0, 0.01, 0.01, 0.01, 0.0,
                                gamma=gamma, eps=0.05)[0]
        print(f"  gamma={gamma}: worst cheap mini-shell truth={worst:.4f} "
              f"(vs {floored:.4f} under the old eps=0.05 floor)")
        if worst >= tight_median:
            violations.append(
                f"gamma={gamma}: cheap mini-shell {worst:.4f} >= panel honest "
                f"median {tight_median} (D1)")
    return violations


def main() -> int:
    analytic_frontier()
    violations = linear_gate_assertion()
    print()
    violations += shell_assertion()
    violations += mini_shell_assertion()
    if violations:
        print(f"GATE VIOLATIONS ({len(violations)}):")
        for v in violations[:20]:
            print("  !", v)
        return 1
    print("PASS: the default score is exactly gate * quality, is monotone in "
          "both inputs, and preserves the zero-gate and zero-substance gates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
