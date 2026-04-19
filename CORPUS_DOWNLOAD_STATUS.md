# Corpus Download Status (remote: westd / WSL Ubuntu)

Last updated: 2026-04-17 (Mac local) / 2026-04-19 ~01:36 (WSL clock)

## Summary

| # | Corpus | URL | Size (expected) | Status | Local path | Kiwix book name |
|---|--------|-----|-----------------|--------|------------|-----------------|
| 1 | Simple English Wikipedia (maxi) | https://download.kiwix.org/zim/wikipedia/wikipedia_en_simple_all_maxi_2026-02.zim | 3.41 GB (actual; spec said ~1 GB) | **done** (sha content-length exact match 3413847238 B) | `/opt/corpus/wiki/wikipedia_en_simple_all_maxi.zim` | `wikipedia_en_simple_all` |
| 2 | English Wikipedia no-pic | https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_nopic_2026-03.zim | 51.93 GB (51927559581 B) | **downloading** (background wget, pid 703971, ~1.3 GB / 52 GB at 1 MB/s, ETA ~13 h) | `/opt/corpus/wiki/wikipedia_en_all_nopic.zim` | _(after download)_ `wikipedia_en_all_nopic` |
| 3 | ArXiv metadata dump (Kaggle) | https://www.kaggle.com/datasets/Cornell-University/arxiv | ~4 GB | **skipped** — Kaggle API token not configured on remote (per task "if no token skip") | - | - |
| 4 | Stack Overflow posts dump | archive.org `stackexchange` stackoverflow.com-Posts.7z | ~50 GB | **deferred** — waits for #2 to complete; will reassess once D: free > 60 GB | - | - |

## Kiwix serving

- Docker image: `ghcr.io/kiwix/kiwix-serve:latest` (pulled)
- Container: `kiwix` (running, `--restart unless-stopped`)
- Host port: `8090` → container `8080`
- Volume: `/opt/corpus/wiki:/data`
- Launch args (positional only — the image's `start.sh` prepends `--port=8080`):
  ```
  docker run -d --name kiwix --restart unless-stopped -p 8090:8080 \
    -v /opt/corpus/wiki:/data \
    ghcr.io/kiwix/kiwix-serve \
    /data/wikipedia_en_simple_all_maxi.zim
  ```
- Verification: `curl http://localhost:8090/search?pattern=einstein` returns HTTP 200, 24 KB HTML.
- Catalog endpoint: `http://localhost:8090/catalog/v2/entries` lists book `wikipedia_en_simple_all`.
- **After #2 finishes**, recreate the container including the second ZIM:
  ```
  docker rm -f kiwix
  docker run -d --name kiwix --restart unless-stopped -p 8090:8080 \
    -v /opt/corpus/wiki:/data \
    ghcr.io/kiwix/kiwix-serve \
    /data/wikipedia_en_simple_all_maxi.zim \
    /data/wikipedia_en_all_nopic.zim
  ```

## Progress probe (for later)

Check download progress from Mac:
```
ssh westd 'wsl -d Ubuntu -- bash -c "ls -lh /opt/corpus/wiki/ && tail -3 /tmp/wiki_fullen.log && ps -p $(cat /tmp/wiki_dl.pid) -o pid,stat,etime,cmd 2>&1 | head -3"'
```

Background wget pid file: `/tmp/wiki_dl.pid` → current pid `703971`.
Log: `/tmp/wiki_fullen.log`.

## Disk

- Mount: `D:\` → `/mnt/d` in WSL
- Total: 932 GB
- Used: 756 GB
- **Remaining D 盘空间: 177 GB** (4.5 GB consumed by Wiki so far; will drop to ~125 GB once #2 finishes).
