# Length-Controlled Ablation

**n** = 52 runs across 13 agents × 4 tasks.

Goal: check whether any scoring pillar rewards verbosity. Spearman ρ > 0.4 = SUSPECT, > 0.6 = STRONG (needs length-normalized variant).

## Per-pillar correlation with answer word count

| Pillar | Spearman ρ | p | Δscore per +1000 words | Flag |
|---|---:|---:|---:|:---:|
| markdown_structure | +0.321 | 0.020 | +0.0983 | **OK** |
| citation | +0.176 | 0.213 | +0.2701 | **OK** |
| fact_kg | -0.015 | 0.914 | -0.0055 | **OK** |
| llm_judge | -0.303 | 0.029 | -0.0634 | **OK** |
| checklist | -0.366 | 0.008 | -0.1654 | **OK** |
| evidence_density | +0.169 | 0.230 | +0.1327 | **OK** |
| efficiency | — | — | — | zero variance |
| composite | +0.165 | 0.243 | +0.0495 | **OK** |

## Avg word count per agent (longer-writing agents get a length advantage if ρ>0)

- **deerflow-glm46**: 3162 words
- **deerflow-glm46-shim**: 2457 words
- **deerflow-glm46-new**: 2431 words
- **gpt-researcher**: 2050 words
- **gpt-researcher-ds**: 1990 words
- **odr-ds**: 1924 words
- **react-glm5**: 1742 words
- **camel-ai-ds**: 1670 words
- **deerflow-ds**: 1590 words
- **camel-ai**: 1478 words
- **react-qwen35plus**: 1382 words
- **smolagents**: 991 words
- **smolagents-ds**: 512 words

## Interpretation

- Flag=OK → pillar is length-robust, keep as-is.
- Flag=SUSPECT → report both raw and length-normalized in paper; add length as a covariate in regression tables.
- Flag=STRONG → replace the pillar with a length-controlled variant OR cap per-answer word count at e.g. 1500 before scoring.
