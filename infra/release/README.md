# Deep Research Arena Docker Release Bundle

This bundle is intended to be copied to another Linux/x86_64 machine with
Docker Engine and Docker Compose v2. It contains the offline sandbox services
needed to run the Deep Research Arena evaluation:

- Magento shopping corpus on port 7770
- Postmill forum corpus on port 9999
- Kiwix Wikipedia snapshot on port 8090
- Search/LLM gateway on port 8081
- DeepSeek proxy behind the gateway

## Expected Bundle Layout

```text
dr-eval-release-YYYYMMDD/
  README.md
  .env.example
  compose.yml
  bin/
    load_images.sh
    start_sandbox.sh
    smoke_test.sh
  deep_reserch/
  images/
    shopping_final_0712.tar
    postmill-populated-exposed-withimg.tar
    dr-bench-gateway.tar
    dr-bench-ds-proxy.tar
    kiwix-serve.tar
  wiki/
    wikipedia_en_all_nopic.zim
```

## Requirements

- Linux x86_64 host
- Docker Engine with the `docker compose` plugin
- At least 220 GB free disk for loading images plus the wiki snapshot
- Ports 7770, 9999, 8090, and 8081 available

## Quickstart

```bash
cd dr-eval-release-YYYYMMDD
cp .env.example .env
# Edit .env if you want the gateway to proxy LLM calls.

bash bin/load_images.sh
bash bin/start_sandbox.sh
bash bin/smoke_test.sh
```

Agents should point at:

```bash
export TAVILY_API_URL=http://localhost:8081
export OPENAI_BASE_URL=http://localhost:8081/llm/v1
export OPENAI_API_KEY=anything
```

If you use the bundled DeepSeek proxy, set `DEEPSEEK_API_KEY` in `.env`.
The sandbox/search routes work without an LLM key; only proxied LLM calls fail.

## Scoring

The source tree is bundled under `deep_reserch/`. From there, create a Python
environment and use the existing scoring scripts:

```bash
cd deep_reserch
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

python3 scripts/score_deep_answer.py \
  --task dr_cross_deep_0001 \
  --answer path/to/report.md
```

## Reset / Stop

```bash
docker compose -f compose.yml down -v --remove-orphans
bash bin/start_sandbox.sh
```

