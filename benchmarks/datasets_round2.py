"""Datasets for the round-2 stress and compression benchmarks.

Real files from this machine are used when present (Python stdlib, npm JavaScript, YAML,
licence texts, Markdown); every dataset has a deterministic generated fallback so the
benchmarks run anywhere. Each builder returns a list of documents.
"""
from __future__ import annotations

import glob
import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_files(patterns, limit_bytes, min_size=0):
    docs, total = [], 0
    for pattern in patterns:
        for path in sorted(glob.glob(pattern, recursive=True)):
            try:
                if os.path.getsize(path) < min_size:
                    continue
                text = open(path, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
            docs.append(text)
            total += len(text)
            if total >= limit_bytes:
                return docs
    return docs


def repetitive_synthetic(limit=1_000_000):
    line = "The project state is important and must be saved accurately.\n"
    return [line * (limit // len(line))]


def agent_conversation(limit=1_000_000, seed=1):
    """A long coding-agent session: prompts, explanations, shell commands, test runs, diffs, retries."""
    rng = random.Random(seed)
    modules = ["auth", "billing", "router", "cache", "parser", "scheduler", "exporter", "loader"]
    out, size, turn = [], 0, 0
    while size < limit:
        turn += 1
        mod = rng.choice(modules)
        block = [
            f"## Turn {turn}",
            f"User: The {mod} module fails when the input is empty. Can you fix it and add a test?",
            f"Assistant: I'll look at src/{mod}.py first, then reproduce the failure.",
            f"$ grep -n \"def \" src/{mod}.py",
            *[f"src/{mod}.py:{10 + i * 7}:def handle_{rng.choice(['read', 'write', 'parse', 'flush'])}_{i}(self, data):" for i in range(rng.randint(3, 6))],
            f"$ python -m pytest tests/test_{mod}.py -x -q",
        ]
        for attempt in range(rng.randint(1, 3)):  # retries print the same failure again
            block += [
                "============================= test session starts ==============================",
                f"tests/test_{mod}.py::test_empty_input FAILED",
                f"E   ValueError: {mod} received no data",
                f"E   ValueError: {mod} received no data" if rng.random() < 0.4 else f"tests/test_{mod}.py:42: AssertionError",
                "=========================== short test summary info ============================",
                f"FAILED tests/test_{mod}.py::test_empty_input - ValueError: {mod} received no data",
            ]
            if attempt < 2:
                block += ["Assistant: Still failing; checking the guard clause.", f"$ sed -n '30,60p' src/{mod}.py"]
        block += [
            f"Assistant: The function indexes data[0] before checking length. Fixing it.",
            f"--- a/src/{mod}.py", f"+++ b/src/{mod}.py", "@@ -31,6 +31,8 @@", f"     def handle(self, data):",
            "+        if not data:", "+            return []", "         first = data[0]",
            f"$ python -m pytest tests/test_{mod}.py -q",
            f"tests/test_{mod}.py ...                                                   [100%]",
            "3 passed in 0.12s",
            f"Assistant: Fixed. The {mod} module now returns an empty list for empty input, and I added a regression test.",
            "",
        ]
        text = "\n".join(block) + "\n"
        out.append(text)
        size += len(text)
    return ["".join(out)]


def python_source(limit=1_000_000):
    docs = _read_files(["/usr/lib/python3.13/*.py"], limit, 2000)
    return docs or [f"def f{i}(x):\n    return x + {i}\n\n\n" * 1 for i in range(limit // 30)]


def javascript_source(limit=1_000_000):
    docs = _read_files(["/opt/node22/lib/node_modules/npm/node_modules/**/*.js"], limit, 2000)
    return docs or ["".join(f"function f{i}(x) {{\n  return x + {i};\n}}\n\n" for i in range(limit // 40))]


def project_memory(limit=1_000_000):
    docs = [open(os.path.join(ROOT, name), encoding="utf-8").read() for name in ("README.md", "SKILL.md") if os.path.exists(os.path.join(ROOT, name))]
    rng = random.Random(3)
    facts = [f"Decision {i}: module_{i}.py uses timeout={i * 10}s" for i in range(60)]
    memory, size = [], 0
    while size < min(limit, 200_000):  # a memory file that re-states facts across sessions
        session = "\n".join(f"- {rng.choice(facts)}" for _ in range(25))
        memory.append(f"## Session {len(memory) + 1}\n\n{session}\n")
        size += len(memory[-1])
    return docs + ["\n".join(memory)]


def json_documents(limit=1_000_000):
    docs = _read_files(["/opt/node22/lib/node_modules/npm/node_modules/**/package.json"], limit // 2, 500)
    rng = random.Random(5)
    api = {"items": [{"id": i, "status": rng.choice(["ok", "ok", "failed"]), "tags": ["a", "a", "b"], "score": rng.choice([1, 1, 2])} for i in range(2000)]}
    return [d for d in docs if _is_json(d)] + [json.dumps(api, indent=2) + "\n"]


def _is_json(text):
    try:
        json.loads(text)
        return True
    except ValueError:
        return False


def yaml_documents(limit=1_000_000):
    docs = _read_files(["/opt/**/*.yml", "/opt/**/*.yaml"], limit // 2, 500)
    manifest = "".join(
        f"apiVersion: v1\nkind: Pod\nmetadata:\n  name: worker-{i}\n  labels:\n    app: worker\n    tier: backend\nspec:\n  containers:\n"
        f"    - name: app\n      image: registry/app:1.{i % 3}\n      args: [\"--mode\", \"fast\", \"--mode\", \"fast\"]\n---\n" for i in range(300))
    return docs + [manifest]


def prose_text(limit=1_000_000):
    docs = _read_files(["/usr/share/common-licenses/*", "/mnt/skills/**/*.md"], limit, 3000)
    return docs or [" ".join(f"Sentence number {i} says something different about topic {i * 7 % 13}." for i in range(limit // 70))]


def multilingual(limit=1_000_000):
    base = [
        "Это тестовое сообщение на русском языке с разными словами.", "这是一个用于测试的中文句子，包含不同的内容。",
        "これは日本語のテスト文であり、内容はそれぞれ異なります。", "هذه جملة اختبار باللغة العربية تحتوي على كلمات مختلفة.",
        "Ceci est une phrase de test en français avec des accents é è ê.", "Dies ist ein deutscher Testsatz mit Umlauten ä ö ü ß.",
        "🙂 emoji and mixed scripts: 한국어 テスト Привет 你好 مرحبا", "Αυτή είναι μια δοκιμαστική πρόταση στα ελληνικά.",
    ]
    rng = random.Random(7)
    out, size = [], 0
    while size < limit:
        line = f"{rng.choice(base)} #{rng.randint(1, 50)}\n"
        out.append(line)
        size += len(line)
    return ["".join(out)]


DATASETS = {
    "repetitive synthetic (best case)": repetitive_synthetic,
    "coding-agent conversation": agent_conversation,
    "Python source (stdlib)": python_source,
    "JavaScript source (npm)": javascript_source,
    "project-memory documents": project_memory,
    "JSON documents": json_documents,
    "YAML documents": yaml_documents,
    "non-repetitive prose": prose_text,
    "multilingual Unicode": multilingual,
}
