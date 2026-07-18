#!/usr/bin/env python3
"""Create a sealed route-flexible judgment artifact for one report."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.observation_ledger import load_observation_ledger
from src.eval.route_flexible_judge import judge_route_flexible


def _ssh_judge_call(host: str, distro: str):
    """Return a judge backend that keeps the model proxy bound to WSL loopback."""

    remote_python = (
        "import re,sys,urllib.request;"
        "cfg=open('/run/cliproxyapi/config.yaml',encoding='utf-8').read();"
        "m=re.search(r'(?m)^api-keys:\\s*$\\n\\s*-\\s*[\\\"\\\']?([^\\\"\\\'\\s]+)',cfg);"
        "assert m,'runtime api key missing';"
        "data=sys.stdin.buffer.read();"
        "req=urllib.request.Request('http://127.0.0.1:8317/v1/chat/completions',data=data,"
        "headers={'Authorization':'Bearer '+m.group(1),'Content-Type':'application/json'});"
        "resp=urllib.request.urlopen(req,timeout=240).read();"
        "sys.stdout.buffer.write(resp)"
    )
    encoded_remote = base64.b64encode(remote_python.encode("utf-8")).decode("ascii")
    remote_command = (
        f'wsl -d {distro} -- python3 -c "import base64;'
        f"exec(base64.b64decode('{encoded_remote}'))\""
    )

    def call(system: str, user: str, model: str | None, max_tokens: int, temperature: float):
        payload = {
            "model": model or "deepseek-v4-pro",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        completed = subprocess.run(
            [
                "ssh",
                host,
                remote_command,
            ],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if completed.returncode != 0:
            return None, (completed.stderr or completed.stdout or "SSH judge failed")[:1000]
        try:
            response = json.loads(completed.stdout)
            content = response["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            return None, f"invalid SSH judge response: {exc}"
        if isinstance(content, list):
            content = "".join(
                str(item.get("text") or "") if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content), None

    return call


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rubric", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model")
    parser.add_argument(
        "--ssh-judge-host",
        help="pilot-only: invoke the loopback-bound judge through this SSH host",
    )
    parser.add_argument("--ssh-wsl-distro", default="Ubuntu")
    args = parser.parse_args()
    rubric = json.loads(args.rubric.read_text(encoding="utf-8"))
    report = args.report.read_text(encoding="utf-8")
    ledger = load_observation_ledger(args.ledger)
    judge_call = (
        _ssh_judge_call(args.ssh_judge_host, args.ssh_wsl_distro)
        if args.ssh_judge_host
        else None
    )
    artifact = judge_route_flexible(
        rubric,
        report,
        ledger,
        model=args.model,
        judge_call=judge_call,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "report_targets": len(artifact["report_results"]),
                "evidence_bindings": len(artifact["evidence_results"]),
                "judge": artifact["judge"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
