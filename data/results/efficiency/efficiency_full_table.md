# Qwen efficiency vs quality vs grounding (GLM-5.1 judge)

All models grounded_frac = 1.0 (every cited URL live; fixed protocol passes real URLs to the writer).
Quality = GLM-5.1 pairwise win-rate across model-vs-model battles on the same tasks.

| model | mean tokens | mean words | quality win-rate | quality Elo |
| --- | --: | --: | --: | --: |
| qwen3-30b-a3b-instruct-2507 | 4280 | 1489 | 0.33 | n/a |
| qwen3-32b | 3100 | 668 | 0.22 | n/a |
| qwen3-max | 3870 | 914 | 0.22 | n/a |
| qwen-flash | 4810 | 1640 | 0.11 | n/a |
