# Tier-0 Local Reward Probe

- Generated: 2026-06-02T07:45:26
- Mode: fast
- Mock judge: False
- V3_JUDGE_N_SAMPLES: 2
- Language: en
- Target words: 650

## Scores

| mode | variant         | composite | coverage | depth  | rigor  | style  | checklist | spec   | source_div | balance | longform | bilingual | nullify | health |
| ---- | --------------- | --------- | -------- | ------ | ------ | ------ | --------- | ------ | ---------- | ------- | -------- | --------- | ------- | ------ |
| fast | A_excellent     | 0.9635    | 1.0000   | 0.5000 | 0.5000 | 0.5000 | 0.5000    | 1.0000 | 1.0000     | 1.0000  | 0.7550   | 1.0000    | no      | ok     |
| fast | B_good          | 0.7684    | 0.7667   | 0.5000 | 0.5000 | 0.5000 | 0.5000    | 1.0000 | 0.9500     | 1.0000  | 0.4700   | 1.0000    | no      | ok     |
| fast | C_shallow       | 0.5987    | 0.3833   | 0.5000 | 0.5000 | 0.5000 | 0.5000    | 1.0000 | 0.7750     | 0.0000  | 0.4440   | 1.0000    | no      | ok     |
| fast | D_fabricated    | 0.0000    | 0.5389   | 0.5000 | 0.5000 | 0.5000 | 0.5000    | 1.0000 | 0.7111     | 0.0000  | 0.4770   | 1.0000    | yes     | ok     |
| fast | E_single_domain | 0.5929    | 0.2333   | 0.5000 | 0.5000 | 0.5000 | 0.5000    | 1.0000 | 0.0000     | 1.0000  | 0.4850   | 1.0000    | no      | ok     |
| fast | F_one_sided     | 0.6439    | 0.7667   | 0.5000 | 0.5000 | 0.5000 | 0.5000    | 1.0000 | 0.9500     | 0.0000  | 0.4530   | 1.0000    | no      | ok     |
| fast | G_padded_thin   | 0.4573    | 0.1556   | 0.5000 | 0.5000 | 0.5000 | 0.5000    | 0.8000 | 0.5000     | 0.0000  | 0.5000   | 1.0000    | no      | ok     |

## Ranking

fast ranking: A_excellent(0.9635) > B_good(0.7684) > F_one_sided(0.6439) > C_shallow(0.5987) > E_single_domain(0.5929) > G_padded_thin(0.4573) > D_fabricated(0.0000)

full ranking: not run

## Checks

| status | check                                                     | detail                                                                                                                              |
| ------ | --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| SKIP   | A_excellent highest full composite                        | full mode not run                                                                                                                   |
| SKIP   | full depth separates A_excellent from C_shallow           | full mode not run                                                                                                                   |
| PASS   | D_fabricated nullified                                    | mode=fast, composite=0.0000, nullify=True, source=proof_of_fetch, n_resolved=0                                                      |
| PASS   | E_single_domain below A on source_diversity and composite | mode=fast, E_single_domain source_diversity=0.0000, A source_diversity=1.0000, E_single_domain composite=0.5929, A composite=0.9635 |
| PASS   | F_one_sided below A on perspective_balance and composite  | mode=fast, F_one_sided perspective_balance=0.0000, A perspective_balance=1.0000, F_one_sided composite=0.6439, A composite=0.9635   |
| PASS   | G_padded_thin below A on longform_quality and composite   | mode=fast, G_padded_thin longform_quality=0.5000, A longform_quality=0.7550, G_padded_thin composite=0.4573, A composite=0.9635     |

PROBE: PASS
