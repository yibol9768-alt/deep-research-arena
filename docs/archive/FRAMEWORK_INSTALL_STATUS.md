# Deep Research Frameworks Install Status (remote: westd / WSL Ubuntu)

Target: `/opt/deep_reserch` on WSL Ubuntu (Ubuntu 22.04, Python 3.10.12, Node 22.22.2).
Each Python framework in its own venv (`/opt/deep_reserch/.venv-<name>`), Node / clone-only frameworks in `/opt/deep_reserch/third_party/<name>`.
Proxy used for all network I/O: `http_proxy=http://172.30.48.1:7890` (Mihomo on Windows host).

## Result table

| # | name                        | status   | path                                                             | size  | notes |
|---|-----------------------------|----------|------------------------------------------------------------------|-------|-------|
| 1 | local-deep-research         | OK       | /opt/deep_reserch/.venv-ldr                                      | 6.1G  | `pip install local-deep-research`; pulls full CUDA/torch; `import local_deep_research` OK |
| 2 | knowledge-storm (stanford)  | OK       | /opt/deep_reserch/.venv-storm                                    | 5.4G  | `pip install knowledge-storm`; `import knowledge_storm` OK; pulls torch |
| 3 | smolagents (+ examples/ODR) | OK       | /opt/deep_reserch/.venv-smol                                     | 105M  | `pip install smolagents[toolkit]`; `import smolagents` OK; examples at `/opt/deep_reserch/third_party/smolagents/examples/open_deep_research` (sparse-checkout) |
| 4 | ii-researcher               | OK       | /opt/deep_reserch/.venv-ii                                       | 784M  | `pip install -e third_party/ii-researcher`; `import ii_researcher` OK |
| 5 | agents-deep-research (qx)   | OK       | /opt/deep_reserch/.venv-qx + third_party/agents-deep-research    | 187M  | `pip install -r requirements.txt`; `deep_researcher` importable when cwd is repo root |
| 6 | node-DeepResearch (jina-ai) | OK       | /opt/deep_reserch/third_party/node-DeepResearch                  | 234M  | `npm install` OK; 19 deps; `node_modules/.bin` populated |
| 7 | btahir/open-deep-research   | OK       | /opt/deep_reserch/third_party/btahir-open-deep-research          | 781M  | `npm install` OK; 34 deps |
| 8 | nickscamara/open-deep-research | OK    | /opt/deep_reserch/third_party/nicks-open-deep-research           | 657M  | `npm install --legacy-peer-deps` (drizzle-orm vs react peer conflict needed flag); 66 deps |
| 9 | CopilotKit/open-research-ANA | CLONED  | /opt/deep_reserch/third_party/open-research-ANA                  | 1.3M  | No docker-compose.yml present; clone-only, no build |
| 10 | Tencent/CognitiveKernel-Pro | CLONED  | /opt/deep_reserch/third_party/CognitiveKernel-Pro                | 2.9M  | Repo has no `requirements.txt` / `pyproject.toml` / `setup.py`; source only |
| 11 | InternLM/MindSearch         | OK       | /opt/deep_reserch/.venv-mindsearch + third_party/MindSearch     | 903M  | `pip install -r requirements.txt`; `import mindsearch` OK (from repo path) |
| 12 | kortix-ai/suna              | CLONED  | /opt/deep_reserch/third_party/suna                               | 211M  | Per spec: clone-only (heavy) |
| 13 | microsoft/magentic-ui       | OK       | /opt/deep_reserch/.venv-magentic                                 | 881M  | `pip install magentic-ui`; `import magentic_ui` OK |
| 14 | mshumer/OpenDeepResearcher  | CLONED  | /opt/deep_reserch/third_party/OpenDeepResearcher                 | 252K  | Per spec: clone-only (Jupyter notebook) |
| 15 | HarshJ23/Deeper-Seeker      | CLONED  | /opt/deep_reserch/third_party/Deeper-Seeker                      | 67M   | Per spec: clone-only (small baseline) |

## Summary

- 15/15 frameworks handled, 0 hard failures.
  - **Installed + import smoke OK**: 11 (#1,2,3,4,5,6,7,8,11,13 + #5 via cwd)
  - **Cloned only (per spec or no build script)**: 4 (#9,10,12,14,15 — #9 missing compose; #10 has no setup)
- Total disk under `/opt/deep_reserch`: **19 GB** (includes pre-existing `.venv-gptr`, `.venv-camel`, `.venv-odr`, `.venv` from earlier; venvs from this batch total ~15 GB, dominated by local-deep-research 6.1G and knowledge-storm 5.4G which bundle torch+CUDA).
- Remote disk free after: **615 GB** (of 1007 GB). Threshold of 20 GB never breached.

## How to use

Each Python venv is self-contained:
```bash
ssh westd
wsl -d Ubuntu
source /opt/deep_reserch/.venv-<name>/bin/activate
```

Node frameworks:
```bash
cd /opt/deep_reserch/third_party/<name>
# read README for exact run cmd; npm deps already installed
```

Logs of each install are in `/tmp/install-<name>.log` on the WSL side; raw TSV at `/tmp/install-STATUS.tsv`; combined stdout at `/tmp/install-ALL.log`.
