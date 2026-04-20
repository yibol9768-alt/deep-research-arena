# Length-Controlled Ablation

**n** = 80 runs across 14 agents × 8 tasks.

Goal: check whether any scoring pillar rewards verbosity. Spearman ρ > 0.4 = SUSPECT, > 0.6 = STRONG (needs length-normalized variant).

## Per-pillar correlation with answer word count

| Pillar | Spearman ρ | p | Δscore per +1000 words | Flag |
|---|---:|---:|---:|:---:|
| markdown_structure | +0.390 | 0.000 | +0.1172 | **OK** |
| citation | +0.187 | 0.097 | +0.2532 | **OK** |
| fact_kg | +0.045 | 0.692 | +0.0029 | **OK** |
| llm_judge | -0.289 | 0.009 | -0.0626 | **OK** |
| checklist | -0.143 | 0.205 | -0.0854 | **OK** |
| evidence_density | +0.240 | 0.032 | +0.1689 | **OK** |
| efficiency | — | — | — | zero variance |
| composite | +0.201 | 0.073 | +0.0713 | **OK** |

## Avg word count per agent (longer-writing agents get a length advantage if ρ>0)

- **deerflow-glm46**: 3162 words
- **deerflow-glm46-shim**: 2457 words
- **deerflow-glm46-new**: 2431 words
- **gpt-researcher-ds**: 1941 words
- **gpt-researcher**: 1936 words
- **odr-ds**: 1816 words
- **react-glm5**: 1742 words
- **camel-ai-ds**: 1711 words
- **deerflow-ds**: 1590 words
- **camel-ai**: 1478 words
- **gpt5chat**: 1390 words
- **react-qwen35plus**: 1382 words
- **smolagents**: 991 words
- **smolagents-ds**: 492 words

## Interpretation

- Flag=OK → pillar is length-robust, keep as-is.
- Flag=SUSPECT → report both raw and length-normalized in paper; add length as a covariate in regression tables.
- Flag=STRONG → replace the pillar with a length-controlled variant OR cap per-answer word count at e.g. 1500 before scoring.
