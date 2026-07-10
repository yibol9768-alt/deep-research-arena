#!/usr/bin/env python3
"""E-7 Jury agreement panel (fully offline; zero judge cost).

Reads the usefulness-jury battle bank (one row per judge x battle x order):
  data/results/usefulness_jury/uj_v1/battles.jsonl

Schema per row: backbone, task, a, b, order in {ab,ba}, judge, winner in
{A,B,tie,None}, same_family, error, ...

An *item* is one presented ordering shown identically to all 3 judges:
key = (backbone, task, a, b, order). Each item carries exactly 3 judge rows.
An unordered *pair* = (backbone, task, {a,b}); ~11% of pairs were judged in
BOTH orders (the double-order audit set).

winner is coded by POSITION (A=first shown, B=second shown). Order-invariant
AGENT winner:
  order==ab: A->a, B->b ;  order==ba: A->b, B->a ;  tie->tie ; None->missing.

An errored vote (winner is None) is treated as MISSING and is NEVER folded to
tie.

Panels produced, per backbone:
  1. Krippendorff alpha (nominal {a,b,tie}) + weighted alpha (metric with
     tie halfway: d(a,b)=1, d(a,tie)=d(b,tie)=0.5, entering as delta^2) +
     Fleiss kappa on the clean all-3-voted subset + raw pairwise agreement +
     per-judge marginals (tie rate broken out).
  2. Double-order audit (3 tests): per-judge position-flip rate; directional
     binomial test on flip-only rounds; swap-combine alpha gap (within-order
     alpha minus order-pooled agent alpha) with bootstrap CI over pairs.
  3. same_family test: deepseek judge behaviour on deepseek-backbone (same
     family) vs qwen-backbone (cross), netted against the two control judges.
  4. System level: per-judge Bradley-Terry fit -> pairwise Spearman/Kendall.

Usage:
  python3 scripts/analyze_jury_agreement_v2.py \
      --battles /path/to/battles.jsonl --json out.json
"""

import argparse
import collections
import itertools
import json
from pathlib import Path

import numpy as np
from scipy import stats

JUDGES = ["deepseek-v4-flash", "glm-4.7", "MiniMax-M2.5"]
BACKBONES = ["qwen3-8b", "deepseek-v4-flash"]

# Panel 1 codes agreement on POSITION {A,B,tie}: within one item all 3 judges
# see the SAME order, so position agreement IS the substantive agreement, and
# it reproduces the canonical Fleiss (0.63/0.80). Order-invariant AGENT coding
# {win_a,win_b,tie} is used only in panels 2-4 where the two orderings are
# pooled/compared.
POS_CATS = ["A", "B", "tie"]
AG_CATS = ["win_a", "win_b", "tie"]

def _mk_delta(cats, mid):
    """Nominal delta (all off-diagonal=1) unless `mid` is the tie label, in
    which case tie sits halfway (d(win,win)=1, d(win,tie)=0.5)."""
    d = {}
    for c in cats:
        for k in cats:
            if c == k:
                d[(c, k)] = 0.0
            elif mid in (c, k):
                d[(c, k)] = 0.5
            else:
                d[(c, k)] = 1.0
    return d

POS_N = _mk_delta(POS_CATS, mid=None)      # nominal
POS_W = _mk_delta(POS_CATS, mid="tie")     # weighted, tie halfway
AG_N = _mk_delta(AG_CATS, mid=None)


def agent_winner(r):
    """Order-invariant winner as one of {win_a(=agent a), win_b(=agent b),
    tie}, or None if the vote errored. Coded relative to the stored a/b so it
    is comparable across the two orderings of the same pair."""
    w = r.get("winner")
    if w is None:
        return None
    if w == "tie":
        return "tie"
    if r["order"] == "ab":
        return "win_a" if w == "A" else "win_b"
    else:  # ba: position A shows agent b
        return "win_b" if w == "A" else "win_a"


def load(path):
    rows = [json.loads(l) for l in open(path)]
    items = collections.defaultdict(dict)  # key -> {judge: row}
    for r in rows:
        key = (r["backbone"], r["task"], r["a"], r["b"], r["order"])
        items[key][r["judge"]] = r
    return rows, items


# --------------------------------------------------------------------------
# Krippendorff's alpha via the coincidence matrix (handles missing + metric)
# --------------------------------------------------------------------------
def krippendorff_alpha(units, delta, cats):
    """units: list of lists of category labels (one list per unit, one entry
    per rater that produced a non-missing value). delta: dict (c,k)->distance;
    enters as delta**2. Returns alpha or None if <1 pairable unit."""
    o = collections.Counter()          # coincidence counts
    for vals in units:
        m = len(vals)
        if m < 2:
            continue
        # weighted pair counts within the unit, weight 1/(m-1)
        for i in range(m):
            for j in range(m):
                if i == j:
                    continue
                o[(vals[i], vals[j])] += 1.0 / (m - 1)
    if not o:
        return None
    n_c = collections.Counter()
    for (c, k), v in o.items():
        n_c[c] += v
    n = sum(n_c.values())
    if n < 2:
        return None
    d_o = sum(o[(c, k)] * (delta[(c, k)] ** 2) for c in cats for k in cats)
    d_e = sum(n_c[c] * n_c[k] * (delta[(c, k)] ** 2) for c in cats for k in cats)
    d_e /= (n - 1)
    if d_e == 0:
        return None
    return 1.0 - d_o / d_e


def fleiss_kappa(units):
    """Fleiss on the subset where every unit has the SAME rater count and no
    missing (clean, all-3). units: list of category lists (len==R each)."""
    units = [u for u in units if len(u) == 3]
    if not units:
        return None, 0
    n = len(units)
    R = 3
    marg = collections.Counter()
    p_i = []
    for u in units:
        cnt = collections.Counter(u)
        marg.update(cnt)
        p_i.append((sum(v * v for v in cnt.values()) - R) / (R * (R - 1)))
    tot = sum(marg.values())
    p_e = sum((marg[c] / tot) ** 2 for c in marg)
    p_bar = sum(p_i) / n
    if p_e == 1:
        return None, n
    return (p_bar - p_e) / (1 - p_e), n


def pos_winner(r):
    return r.get("winner")  # 'A'/'B'/'tie'/None (position coding)


def pairwise_agreement(item_map, keys, coder):
    """Average raw agreement over the 3 judge pairs, each on items both voted."""
    per = {}
    for j1, j2 in itertools.combinations(JUDGES, 2):
        agree = tot = 0
        for k in keys:
            d = item_map[k]
            v1 = coder(d[j1]) if j1 in d else None
            v2 = coder(d[j2]) if j2 in d else None
            if v1 is None or v2 is None:
                continue
            tot += 1
            agree += (v1 == v2)
        per[f"{j1}|{j2}"] = round(agree / tot, 4) if tot else None
    vals = [v for v in per.values() if v is not None]
    return per, (round(sum(vals) / len(vals), 4) if vals else None)


def marginals(rows_bb):
    """Per-judge POSITION marginals (A/B/tie) + missing, tie broken out."""
    out = {}
    for j in JUDGES:
        rr = [r for r in rows_bb if r["judge"] == j]
        c = collections.Counter(r["winner"] for r in rr)
        n = len(rr)
        voted = n - c[None]
        out[j] = {
            "n_items": n,
            "n_errored": c[None],
            "win_A_pos_rate": round(c["A"] / voted, 4) if voted else None,
            "win_B_pos_rate": round(c["B"] / voted, 4) if voted else None,
            "tie_rate": round(c["tie"] / voted, 4) if voted else None,
            "A_minus_B_pos": round((c["A"] - c["B"]) / voted, 4) if voted else None,
        }
    return out


def panel1(item_map, rows):
    res = {}
    for bb in BACKBONES:
        keys = [k for k in item_map if k[0] == bb]
        units_all, units_clean = [], []
        for k in keys:
            d = item_map[k]
            vals = [pos_winner(d[j]) for j in JUDGES if j in d]
            vals = [v for v in vals if v is not None]
            units_all.append(vals)
            if len(vals) == 3:
                units_clean.append(vals)
        fk, nclean = fleiss_kappa(units_clean)
        per, avg = pairwise_agreement(item_map, keys, pos_winner)
        res[bb] = {
            "n_items": len(keys),
            "n_clean_all3": nclean,
            "krippendorff_alpha_nominal_all": _r(krippendorff_alpha(units_all, POS_N, POS_CATS)),
            "krippendorff_alpha_weighted_all": _r(krippendorff_alpha(units_all, POS_W, POS_CATS)),
            "krippendorff_alpha_nominal_clean": _r(krippendorff_alpha(units_clean, POS_N, POS_CATS)),
            "fleiss_kappa_clean": _r(fk),
            "raw_pairwise_agreement_avg": avg,
            "raw_pairwise_agreement_by_pair": per,
            "marginals": marginals([r for r in rows if r["backbone"] == bb]),
        }
    return res


# --------------------------------------------------------------------------
# Part 2: double-order audit
# --------------------------------------------------------------------------
def both_order_pairs(item_map):
    pairs = collections.defaultdict(dict)  # (bb,task,frozenset{a,b}) -> {order:key}
    for k in item_map:
        bb, task, a, b, order = k
        pairs[(bb, task, frozenset((a, b)))][order] = k
    return {p: o for p, o in pairs.items() if set(o) == {"ab", "ba"}}


def panel2(item_map):
    bop = both_order_pairs(item_map)
    res = {}
    for bb in BACKBONES:
        pkeys = [p for p in bop if p[0] == bb]
        # ---- per-judge flip + directional ----
        judge_flip = {}
        for j in JUDGES:
            flips = consistent = 0
            first_pos = second_pos = 0  # among flips: chose position A twice / B twice
            for p in pkeys:
                kab, kba = bop[p]["ab"], bop[p]["ba"]
                rab, rba = item_map[kab].get(j), item_map[kba].get(j)
                if rab is None or rba is None:
                    continue
                wab, wba = rab["winner"], rba["winner"]
                if wab is None or wba is None:
                    continue
                if wab == "tie" or wba == "tie":
                    continue  # decisive-both only for flip metric
                aw_ab = agent_winner(rab)
                aw_ba = agent_winner(rba)
                if aw_ab == aw_ba:
                    consistent += 1
                else:
                    flips += 1
                    # flip => same POSITION chosen both times
                    if wab == "A":  # then wba must also be A (see docstring)
                        first_pos += 1
                    else:
                        second_pos += 1
            tot = flips + consistent
            bt = stats.binomtest(first_pos, first_pos + second_pos, 0.5) if (first_pos + second_pos) else None
            judge_flip[j] = {
                "n_decisive_both": tot,
                "flip_rate": round(flips / tot, 4) if tot else None,
                "material_gt5pct": (flips / tot > 0.05) if tot else None,
                "flip_first_pos": first_pos,   # always chose the first-shown report
                "flip_second_pos": second_pos, # always chose the second-shown report
                "directional_binom_p": round(bt.pvalue, 4) if bt else None,
            }
        # ---- swap-combine alpha gap ----
        # within-order alpha: each ordered item (agent-coded) is a unit, 3 raters
        within_units = []
        for p in pkeys:
            for order in ("ab", "ba"):
                d = item_map[bop[p][order]]
                vals = [agent_winner(d[jj]) for jj in JUDGES if jj in d]
                within_units.append([v for v in vals if v is not None])
        # pooled alpha: unordered pair is the unit; pool all 6 agent-coded votes
        pooled_units = []
        for p in pkeys:
            vals = []
            for order in ("ab", "ba"):
                d = item_map[bop[p][order]]
                for jj in JUDGES:
                    if jj in d:
                        v = agent_winner(d[jj])
                        if v is not None:
                            vals.append(v)
            pooled_units.append(vals)
        a_within = krippendorff_alpha(within_units, AG_N, AG_CATS)
        a_pooled = krippendorff_alpha(pooled_units, AG_N, AG_CATS)
        gap = (a_within - a_pooled) if (a_within is not None and a_pooled is not None) else None
        # bootstrap CI over pairs
        boot = []
        rng = np.random.default_rng(20260708)
        idx = np.arange(len(pkeys))
        for _ in range(2000):
            samp = rng.choice(idx, size=len(idx), replace=True)
            wu, pu = [], []
            for si in samp:
                p = pkeys[si]
                pv = []
                for order in ("ab", "ba"):
                    d = item_map[bop[p][order]]
                    uv = [agent_winner(d[jj]) for jj in JUDGES if jj in d]
                    uv = [v for v in uv if v is not None]
                    wu.append(uv)
                    for v in uv:
                        pv.append(v)
                pu.append(pv)
            aw = krippendorff_alpha(wu, AG_N, AG_CATS)
            ap = krippendorff_alpha(pu, AG_N, AG_CATS)
            if aw is not None and ap is not None:
                boot.append(aw - ap)
        ci = (round(float(np.percentile(boot, 2.5)), 4),
              round(float(np.percentile(boot, 97.5)), 4)) if boot else None
        res[bb] = {
            "n_both_order_pairs": len(pkeys),
            "per_judge_flip": judge_flip,
            "alpha_within_order": _r(a_within),
            "alpha_order_pooled": _r(a_pooled),
            "position_bias_alpha_gap": _r(gap),
            "gap_bootstrap_ci95": ci,
        }
    return res


# --------------------------------------------------------------------------
# Part 3: same_family
# --------------------------------------------------------------------------
def agrees_with_panel(item_map, key, judge):
    """Does `judge` match the majority agent-winner of the OTHER two judges?
    Returns None if the other two disagree with each other or any missing."""
    d = item_map[key]
    others = [agent_winner(d[j]) for j in JUDGES if j != judge and j in d]
    others = [o for o in others if o is not None]
    me = agent_winner(d[judge]) if judge in d else None
    if me is None or len(others) < 2 or others[0] != others[1]:
        return None
    return me == others[0]


def judge_behaviour(item_map, keys, judge):
    ties = voted = agree = agree_tot = 0
    for k in keys:
        d = item_map[k]
        if judge not in d:
            continue
        w = agent_winner(d[judge])
        if w is None:
            continue
        voted += 1
        ties += (w == "tie")
        a = agrees_with_panel(item_map, k, judge)
        if a is not None:
            agree_tot += 1
            agree += a
    return {
        "n_voted": voted,
        "tie_rate": round(ties / voted, 4) if voted else None,
        "agree_with_other2_rate": round(agree / agree_tot, 4) if agree_tot else None,
        "n_agree_denom": agree_tot,
    }


def panel3(item_map):
    ds_keys = [k for k in item_map if k[0] == "deepseek-v4-flash"]
    qw_keys = [k for k in item_map if k[0] == "qwen3-8b"]
    out = {}
    for j in JUDGES:
        same = judge_behaviour(item_map, ds_keys, j)   # deepseek backbone
        cross = judge_behaviour(item_map, qw_keys, j)   # qwen backbone
        out[j] = {
            "same_family_deepseek_bb": same,
            "cross_qwen_bb": cross,
            "tie_rate_delta": _sub(same["tie_rate"], cross["tie_rate"]),
            "agree_rate_delta": _sub(same["agree_with_other2_rate"],
                                     cross["agree_with_other2_rate"]),
        }
    # net the deepseek judge's deltas against the mean of the two controls
    ctrl = [j for j in JUDGES if j != "deepseek-v4-flash"]
    def _mean(field):
        vs = [out[j][field] for j in ctrl if out[j][field] is not None]
        return round(sum(vs) / len(vs), 4) if vs else None
    out["_netted_deepseek_vs_controls"] = {
        "tie_rate_delta_net": _sub(out["deepseek-v4-flash"]["tie_rate_delta"], _mean("tie_rate_delta")),
        "agree_rate_delta_net": _sub(out["deepseek-v4-flash"]["agree_rate_delta"], _mean("agree_rate_delta")),
        "note": "same_family is battle-level (BOTH reports use the deepseek backbone), "
                "so this measures whether the deepseek judge behaves differently on its "
                "own family's outputs, NOT per-report favouritism.",
    }
    return out


# --------------------------------------------------------------------------
# Part 4: per-judge Bradley-Terry -> rank correlation
# --------------------------------------------------------------------------
def bt_fit(win_matrix, agents, iters=1000, tol=1e-9):
    """MM algorithm for Bradley-Terry. win_matrix[i][j] = wins of i over j
    (ties count 0.5 each). Returns dict agent->strength."""
    n = len(agents)
    W = np.array(win_matrix, float)
    wins = W.sum(axis=1)
    N = W + W.T  # games between i and j
    p = np.ones(n)
    for _ in range(iters):
        pnew = np.zeros(n)
        for i in range(n):
            denom = 0.0
            for j in range(n):
                if i == j:
                    continue
                denom += N[i, j] / (p[i] + p[j])
            pnew[i] = wins[i] / denom if denom > 0 else p[i]
        pnew *= n / pnew.sum()
        if np.max(np.abs(pnew - p)) < tol:
            p = pnew
            break
        p = pnew
    return {a: p[i] for i, a in enumerate(agents)}


def panel4(item_map):
    out = {}
    for bb in BACKBONES:
        keys = [k for k in item_map if k[0] == bb]
        agents = sorted({a for k in keys for a in (k[2], k[3])})
        aidx = {a: i for i, a in enumerate(agents)}
        # per-judge win matrices (agent-level, decisive + ties split)
        strengths = {}
        for j in JUDGES:
            M = np.zeros((len(agents), len(agents)))
            for k in keys:
                d = item_map[k]
                if j not in d:
                    continue
                w = agent_winner(d[j])
                a, b = k[2], k[3]
                if w == "win_a":
                    M[aidx[a], aidx[b]] += 1
                elif w == "win_b":
                    M[aidx[b], aidx[a]] += 1
                elif w == "tie":
                    M[aidx[a], aidx[b]] += 0.5
                    M[aidx[b], aidx[a]] += 0.5
            strengths[j] = bt_fit(M, agents)
        ranks = {j: [strengths[j][a] for a in agents] for j in JUDGES}
        corr = {}
        for j1, j2 in itertools.combinations(JUDGES, 2):
            sp = stats.spearmanr(ranks[j1], ranks[j2])
            kt = stats.kendalltau(ranks[j1], ranks[j2])
            corr[f"{j1}|{j2}"] = {
                "spearman": round(float(sp.statistic), 4),
                "kendall_tau_b": round(float(kt.statistic), 4),
            }
        # ordering per judge (best->worst)
        order = {j: [a for a, _ in sorted(strengths[j].items(), key=lambda x: -x[1])]
                 for j in JUDGES}
        out[bb] = {
            "agents": agents,
            "per_judge_order_best_to_worst": order,
            "log_strength": {j: {a: round(float(np.log(strengths[j][a])), 4) for a in agents}
                             for j in JUDGES},
            "pairwise_rank_corr": corr,
        }
    return out


def _r(x):
    return round(float(x), 4) if x is not None else None


def _sub(a, b):
    return round(a - b, 4) if (a is not None and b is not None) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--battles", required=True)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    rows, item_map = load(args.battles)
    report = {
        "n_rows": len(rows),
        "n_items": len(item_map),
        "judges": JUDGES,
        "panel1_agreement": panel1(item_map, rows),
        "panel2_double_order": panel2(item_map),
        "panel3_same_family": panel3(item_map),
        "panel4_system_rank": panel4(item_map),
    }
    txt = json.dumps(report, indent=2, ensure_ascii=False)
    print(txt)
    if args.json:
        Path(args.json).write_text(txt)


if __name__ == "__main__":
    main()
