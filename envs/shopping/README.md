# Shopping Environment (Magento 2, WebArena `shopping_final_0712`)

Real Magento storefront used as the sandbox for deep-research tasks on
e-commerce data. One container, seeded DB, pinned to port 7770.

## Start / Reset

```bash
cd envs/shopping
./reset.sh               # down -v → up -d → wait healthy → rewrite base_url
```

`reset.sh` rewrites the Magento `base_url` config on every reset, because
the seed DB ships with it pinned to the upstream CMU host
(`metis.lti.cs.cmu.edu:7770`), which makes every homepage request 302-redirect
away from our local container.

## Site map (environment variables)

The runner (`src.runner.PlaywrightRunner`) substitutes `__SHOPPING__` and
friends in task configs using this env-var fallback chain:

| Variable         | Default                          | Purpose                                       |
|------------------|----------------------------------|-----------------------------------------------|
| `SHOPPING`       | `http://localhost:7770`          | Customer-facing Magento storefront            |
| `SHOPPING_ADMIN` | `http://localhost:7780/admin`    | Magento admin panel (not yet deployed)        |
| `REDDIT`         | `http://localhost:9999`          | WebArena reddit (Stage C)                     |
| `GITLAB`         | `http://localhost:8023`          | WebArena gitlab (Stage C)                     |
| `MAP`            | `http://localhost:3000`          | WebArena OSM (Stage C)                        |
| `WIKIPEDIA`      | `http://localhost:8888`          | WebArena wikipedia mirror (Stage C)           |

Placeholders like `__SHOPPING__/some/path.html` in a task JSON are
resolved at runtime. This keeps task files portable across deployments.

## Remote deployment (westd + WSL)

The container runs in Ubuntu WSL on the `westd` Windows host:

```
westd (Windows) ─┬─ Docker Desktop (WSL distro: docker-desktop) [unused]
                 └─ WSL: Ubuntu 22.04 ─ Docker CE 29.4 ─ webarena_shopping
```

Paths inside WSL:

- tar image: `/root/webarena/shopping_final_0712.tar` (63 GB, can delete after load)
- compose dir: `/root/deep_reserch/envs/shopping/`

## Accessing from the Mac

Option 1 — SSH port forward:

```bash
ssh -f -N -L 7770:localhost:7770 westd
curl http://localhost:7770/         # 200, One Stop Market
SHOPPING=http://localhost:7770 pytest tests/test_runner_e2e.py -v
```

(Windows localhost forwards to WSL via the default WSL2 localhostForwarding.)

Option 2 — run pytest inside WSL on westd (not set up yet; requires
installing python3-playwright + chromium in WSL).

## Health probe

```bash
docker ps --filter name=webarena_shopping
curl -sS -o /dev/null -w 'HTTP=%{http_code}\n' http://localhost:7770/
```

## Auth / logged-in state

Many WebArena tasks expect `storage_state: "./.auth/shopping_state.json"`
(logged in as a seeded customer). Task 21's reviews are publicly visible
so no auth is required. For deep-research tasks that touch account-only
pages (orders, addresses), we'll need to regenerate an auth storage state
via `playwright codegen` against the customer login
(`emma.lopez@gmail.com` / `Password.1` per the WebArena seed).

## References

- WebArena docker README:
  https://github.com/web-arena-x/webarena/blob/main/environment_docker/README.md
- Original 187 shopping tasks: `data/tasks/webarena/shopping/*.json`
- Evaluator reference: `webarena_ref/evaluation_harness/evaluators.py`
