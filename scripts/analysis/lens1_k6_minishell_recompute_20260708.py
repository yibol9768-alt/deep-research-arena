import sys, json
sys.path.insert(0, "/root/Desktop/lyb/deep_reserch")
from src.eval.decidable_scorer import compose_truth, QUALITY_WEIGHTS, GAMMA_DEFAULT, EPS_FLOOR

print("K6 weights", QUALITY_WEIGHTS, "gamma", GAMMA_DEFAULT, "eps", EPS_FLOOR)

def T(reach, fact, pof, comp, spec=0.0):
    t,q,fl = compose_truth(reach, fact, pof, comp, spec)
    return t,q

# --- mini-shell variants (reach=1 via ONE real reachable citation) ---
print("\n== mini-shell (reach=1.0) ==")
variants = {
 "pure zero shell (all axes 0)":      (1.0, 0.0,   0.0,   0.0),
 "fact-only (one trivial true claim)":(1.0, 0.001, 0.0,   0.0),
 "comp-only (one vital keyword)":     (1.0, 0.0,   0.0,   0.001),
 "pof-only (quote one sentence)":     (1.0, 0.0,   0.001, 0.0),
 "all-three barely>0":                (1.0, 0.001, 0.001, 0.001),
}
for k,(r,f,p,c) in variants.items():
    t,q = T(r,f,p,c)
    print(f"  {k:<38} quality={q:.4f} truth={t:.4f}")

# --- the shell_assertion's own 'honest champion' reference ---
print("\n== gate test's honest-champion reference vs all-three mini-shell ==")
t_ref,q_ref = T(0.99, 0.00, 0.12, 0.05)   # (0.99,0,0.12,0.05,0.62) from verify_gate_theorem
t_ms, q_ms  = T(1.0, 0.001, 0.001, 0.001)
print(f"  honest-champion ref (0.99,0,0.12,0.05): truth={t_ref:.4f}")
print(f"  all-three mini-shell:                    truth={t_ms:.4f}")
print(f"  mini-shell beats honest-champion ref?  {t_ms > t_ref}")

# --- rank the all-three mini-shell against the real v21 panels ---
BASE="/tmp/claude-0/-root-Desktop/93ed2111-a32d-447e-aba8-7da9bb527cc9/scratchpad/boards_fixed"
for bk in ["qwen3-8b","deepseek-v4-flash"]:
    b=json.load(open(f"{BASE}/truth_board_{bk}_v21.json"))
    rows=b["rows"]
    for shell_name, shell_truth in [("all-three shell",0.05),("fact-only shell",T(1,0.001,0,0)[0])]:
        beaten=[r["agent"] for r in rows if r["truth_macro"] < shell_truth]
        better=[r["agent"] for r in rows if r["truth_macro"] >= shell_truth]
        print(f"\n{bk} v21: {shell_name} truth={shell_truth:.4f}  beats {len(beaten)}/12 real agents")
        print(f"   only above shell: {better}")

# --- how much of the panel's quality is floor-driven? ---
print("\n== floor dominance: per (agent,axis) cells at/below eps in v21 ==")
for bk in ["qwen3-8b","deepseek-v4-flash"]:
    b=json.load(open(f"{BASE}/truth_board_{bk}_v21.json"))
    cells=0; floored=0; zero=0
    for r in b["rows"]:
        ax=r["axes_mean"]
        for key in ("correctness_fact_support","grounding_proof_of_fetch","completeness"):
            v=ax[key]; cells+=1
            if v==0: zero+=1
            elif v<EPS_FLOOR: floored+=1
    print(f"  {bk}: {cells} axis-cells  zero={zero}  0<v<eps(floored up)={floored}  -> {100*(zero+floored)/cells:.0f}% at-or-below floor")
