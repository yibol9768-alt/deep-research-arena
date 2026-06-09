from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from huggingface_hub import snapshot_download


MODEL_ID = os.environ.get("DR_TULU_MODEL_ID", "rl-research/DR-Tulu-8B")
OUT_JSON = Path(os.environ.get("DR_TULU_DOWNLOAD_REPORT", "/opt/deep_reserch/.dra_tmp/dr_tulu_download.json"))


def main() -> int:
    local_dir = snapshot_download(
        repo_id=MODEL_ID,
        resume_download=True,
        local_files_only=False,
    )
    root = Path(local_dir)
    files = [p for p in root.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    report = {
        "model_id": MODEL_ID,
        "local_dir": str(root),
        "file_count": len(files),
        "total_bytes": total,
        "hf_endpoint": os.environ.get("HF_ENDPOINT", ""),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
