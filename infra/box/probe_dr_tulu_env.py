from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


print("python:", sys.executable)
print("version:", sys.version.replace("\n", " "))
print("platform:", platform.platform())
for name in ("torch", "transformers", "huggingface_hub", "hf_transfer", "vllm", "openai"):
    print(f"module:{name}={module_available(name)}")
print("HF_ENDPOINT:", os.environ.get("HF_ENDPOINT", ""))
print("HF_HOME:", os.environ.get("HF_HOME", ""))
print("vllm_bin:", shutil.which("vllm") or "")
try:
    out = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total,memory.used",
            "--format=csv,noheader",
        ],
        text=True,
        timeout=10,
    )
    print("nvidia-smi:", out.strip())
except Exception as exc:
    print("nvidia-smi-error:", type(exc).__name__, str(exc))
