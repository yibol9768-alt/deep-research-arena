from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.rl.tools import ToolContext
from src.rl.tools_rag import RagSearchTool


def test_build_rag_index_no_dense_and_rag_search_loads(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    out = tmp_path / "index"
    rows = [
        {
            "url": "http://localhost:7770/novamax-pro.html",
            "text": "NovaMax Pro headphones have balanced sound and strong battery.",
        },
        {
            "url": "http://localhost:9999/f/headphones/thread",
            "text": "Owners discuss comfort and long term durability.",
        },
        {
            "url": "http://localhost:8090/content/A/Rocks",
            "text": "Geology article about rocks.",
        },
    ]
    corpus.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    cmd = [
        sys.executable,
        "scripts/build_rag_index.py",
        "--corpus-jsonl",
        str(corpus),
        "--out",
        str(out),
        "--no-dense",
        "--chunk-words",
        "20",
    ]
    proc = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=True)
    summary = json.loads(proc.stdout)

    assert summary["dense"] is False
    assert (out / "chunks.json").exists()
    assert (out / "meta.json").exists()
    assert not (out / "dense.faiss").exists()

    ctx = ToolContext(
        backend=None,
        task_config={"acquisition": {"rag_index_dir": str(out)}},
        extras={},
    )
    result = RagSearchTool().run(ctx, {"query": "NovaMax balanced battery", "top_k": 1})

    assert result.ok is True
    assert result.hits[0]["url"] == "http://localhost:7770/novamax-pro.html"
    assert "balanced sound" in result.snippets["http://localhost:7770/novamax-pro.html"]


def test_build_rag_index_no_dense_avoids_heavy_modules(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    out = tmp_path / "index"
    corpus.write_text(
        json.dumps({"url": "http://localhost:7770/a.html", "text": "alpha beta gamma"}) + "\n",
        encoding="utf-8",
    )

    code = (
        "import sys; "
        "from scripts.build_rag_index import main; "
        f"main(['--corpus-jsonl',{str(corpus)!r},'--out',{str(out)!r},'--no-dense']); "
        "print('faiss' in sys.modules, 'sentence_transformers' in sys.modules, 'numpy' in sys.modules)"
    )
    proc = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, check=True)

    assert "False False False" in proc.stdout
