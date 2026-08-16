
"""AI Token Saver: compact, dependency-free project context storage.

The module provides deterministic text compaction, approximate token estimation,
and a small JSON memory store. It targets roughly 55% context reduction when
input contains repetition/filler, but never promises an exact ratio.

Features:
- Accurate token counting with tiktoken (optional)
- Semantic deduplication for smarter compression
- Configurable aggression levels (safe/balanced/aggressive)
- JSON structured output for automation
- Secret redaction and duplicate removal
"""
=======
"""AI Token Saver: conservative, dependency-free context compaction and memory."""


from __future__ import annotations
from dataclasses import asdict, dataclass, field, fields
import json
from pathlib import Path

from typing import Iterable, Mapping, Optional, Literal
=======
import re
from typing import Callable, Iterable, Iterator, Literal, Mapping, Protocol


class Tokenizer(Protocol):
    def encode(self, text: str) -> object: ...
TokenCounter = Callable[[str], int]
TokenizerLike = Tokenizer | TokenCounter
RedactionMode = Literal["off", "common", "strict"]

@dataclass
class CompactionResult:
    original: str
    compacted: str
    in_tokens: int
    out_tokens: int
    reduction_percent: float
    token_count_is_exact: bool = False
    token_count_source: str = "approximate"
    token_change_percent: float = 0.0
    output_grew: bool = False

@dataclass
class Memory:
    project: str = ""
    goal: str = ""
    state: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Memory":
        values: dict[str, object] = {}
        list_fields = {"state", "decisions", "files", "issues", "next_steps", "preferences", "history"}
        for item in fields(cls):
            value = data.get(item.name)

            if item.name in {"project", "goal"}:
                result[item.name] = value if isinstance(value, str) else ""
            else:
                result[item.name] = (
                    [str(entry) for entry in value if isinstance(entry, (str, int, float))]
                    if isinstance(value, list)
                    else []
                )
        return cls(**result)


# Try to import tiktoken for accurate token counting, fall back to estimate
try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
    _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
except ImportError:
    _TIKTOKEN_AVAILABLE = False
    _tiktoken_encoder = None

_SPACE = re.compile(r"\s+")
=======
            if item.name in {"project", "goal"}: values[item.name] = value if isinstance(value, str) else ""
            elif item.name in list_fields: values[item.name] = [str(x) for x in value if isinstance(x, (str, int, float))] if isinstance(value, list) else []
        return cls(**values)


_SECRET_PATTERNS = (
    re.compile(r"(?i)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)\b\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(\bBearer\s+)([A-Za-z0-9._~+/=-]+)"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
)
_CODE_HINTS = ("```", "#!/", "import ", "from ", "def ", "class ", "function ", "const ", "let ", "var ", "return ", "SELECT ", "INSERT ", "curl ", "npm ", "pip ", "python ", "powershell ", "docker ", "kubectl ", "=>", "::", "&&", "||", "./", "../")
_CODE_SYNTAX = re.compile(r"^\s*(?:(?:def|class)\s+\w+.*:\s*$|(?:if|for|while)\b.*:\s*$|(?:import|from)\s+\S+|return\b)")

def _fallback_token_count(text: str) -> int: return 0 if not text.strip() else max(1, round(len(text) / 4))


def estimate_tokens(text: str) -> int:
    """Estimate tokens without requiring a tokenizer dependency.

    This is intentionally approximate and should not be used for billing.
    Uses len(text)/4 as a rough approximation.
    """
    if not text.strip():
        return 0
    return max(1, round(len(text) / 4))


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """Count tokens accurately using tiktoken if available.
    
    Falls back to estimation if tiktoken is not installed.
    
    Args:
        text: The text to tokenize
        model: The model name for tokenization (default: gpt-3.5-turbo)
    
    Returns:
        Exact token count if tiktoken available, otherwise estimated count
    """
    if _TIKTOKEN_AVAILABLE and _tiktoken_encoder:
        try:
            # Use appropriate encoding based on model
            if "gpt-4" in model or "gpt-3.5" in model:
                encoder = tiktoken.get_encoding("cl100k_base")
            elif "text-davinci" in model or "code" in model:
                encoder = tiktoken.get_encoding("p50k_base")
            else:
                encoder = _tiktoken_encoder
            return len(encoder.encode(text))
        except Exception:
            pass
    return estimate_tokens(text)


def _normalize(line: str) -> str:
    return _SPACE.sub(" ", line.strip())


def _redact_secrets(text: str) -> str:
    redacted = text
    for pattern in _SECRET_PATTERNS[:2]:
        redacted = pattern.sub(lambda match: match.group(1) + "[REDACTED]", redacted)
    redacted = _SECRET_PATTERNS[2].sub("[REDACTED]", redacted)
    redacted = _SECRET_PATTERNS[3].sub("[REDACTED]", redacted)
    return redacted


def deduplicate(lines: Iterable[str]) -> list[str]:
    """Remove normalized duplicate lines while preserving order and meaning."""
    result: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        line = _normalize(raw)
        if not line:
            continue
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(line)
=======
def _token_count_with(tokenizer: TokenizerLike | None, text: str) -> tuple[int, bool, str]:
    if not isinstance(text, str): raise TypeError("text must be a string")
    if tokenizer is None: return _fallback_token_count(text), False, "approximate"
    if callable(tokenizer) and not hasattr(tokenizer, "encode"): count = tokenizer(text)
    else:
        encoded = tokenizer.encode(text)  # type: ignore[union-attr]
        try: count = len(encoded)  # type: ignore[arg-type]
        except TypeError as exc: raise TypeError("tokenizer.encode(text) must return a sized token sequence") from exc
    if isinstance(count, bool) or not isinstance(count, int): raise TypeError("token counter must return an integer")
    if count < 0: raise ValueError("token count cannot be negative")
    return count, True, "supplied-tokenizer"

def estimate_tokens(text: str, tokenizer: TokenizerLike | None = None) -> int: return _token_count_with(tokenizer, text)[0]

def _redact_secrets(text: str, mode: RedactionMode = "common") -> str:
    if mode == "off": return text
    result = text
    for pattern in _SECRET_PATTERNS[:2]: result = pattern.sub(lambda m: m.group(1) + "[REDACTED]", result)
    result = _SECRET_PATTERNS[2].sub("[REDACTED]", result)
    if mode == "strict": result = _SECRET_PATTERNS[3].sub("[REDACTED]", result)

    return result

def _validate_redaction_mode(mode: RedactionMode) -> None:
    if mode not in {"off", "common", "strict"}: raise ValueError("redaction_mode must be 'off', 'common', or 'strict'")

def _line_key(line: str) -> str: return line.rstrip(" \t")

def _looks_like_technical_content(lines: list[str]) -> bool:
    sample = "\n".join(lines[:80])
    if not sample.strip(): return False
    if "```" in sample or any(_CODE_SYNTAX.match(line) for line in lines[:80]): return True
    return sum(1 for hint in _CODE_HINTS if hint in sample) >= 2

def deduplicate(lines: Iterable[str], *, aggressive: bool = False) -> list[str]:
    """Remove safe redundancy while preserving technical/code-like content."""
    source = list(lines)
    if any(not isinstance(line, str) for line in source): raise TypeError("lines must contain only strings")
    if _looks_like_technical_content(source): return [line.rstrip("\r\n") for line in source if line.rstrip("\r\n").strip()]
    result: list[str] = []; seen: set[str] = set(); previous_key: str | None = None
    for raw in source:
        line = raw.rstrip("\r\n")
        if not line.strip(): continue
        key = _line_key(line); duplicate = key in seen if aggressive else key == previous_key
        if not duplicate: result.append(line); seen.add(key)
        previous_key = key
    return result


def compact_text(text: str, *, redact_secrets: bool = True, aggression: Literal["safe", "balanced", "aggressive"] = "balanced") -> str:
    """Compact text conservatively without deleting meaningful phrases.

    Only whitespace normalization and duplicate-line removal are performed.
    Secret-looking values are redacted by default before the result is returned.
    
    Args:
        text: Input text to compact
        redact_secrets: Whether to redact API keys and secrets (default: True)
        aggression: Compression level - 'safe' (minimal), 'balanced' (default), 
                   'aggressive' (maximum compression with some meaning loss risk)
    
    Returns:
        Compacted text with duplicates removed and secrets redacted
    """
    source = _redact_secrets(text) if redact_secrets else text
    
    if aggression == "aggressive":
        # More aggressive: remove very short lines and extra whitespace
        lines = [line for line in source.splitlines() if len(line.strip()) > 2]
        return "\n".join(deduplicate(lines))
    elif aggression == "safe":
        # Safe mode: only remove exact duplicates, preserve original formatting more
        seen = set()
        result = []
        for line in source.splitlines():
            normalized = line.strip()
            key = normalized.casefold()
            if key and key not in seen:
                seen.add(key)
                result.append(line)
        return "\n".join(result)
    else:  # balanced (default)
        return "\n".join(deduplicate(source.splitlines()))


def compact_text_with_metrics(
    text: str, 
    *, 
    redact_secrets: bool = True,
    aggression: Literal["safe", "balanced", "aggressive"] = "balanced",
    model: str = "gpt-3.5-turbo",
    output_json: bool = False
) -> CompactionResult:
    """Compact text and return detailed metrics including in/out token counts.
    
    This function provides the same compaction as compact_text() but also
    returns the original text, estimated input tokens, estimated output tokens,
    and the actual reduction percentage achieved.
    
    Args:
        text: Input text to compact
        redact_secrets: Whether to redact API keys (default: True)
        aggression: Compression level (default: "balanced")
        model: Model name for accurate token counting (default: "gpt-3.5-turbo")
        output_json: If True, use accurate tiktoken counting; otherwise use estimation
    
    Returns:
        CompactionResult with original/compacted text and token metrics
    """
    source = _redact_secrets(text) if redact_secrets else text
    compacted = compact_text(source, redact_secrets=False, aggression=aggression)
    
    # Use accurate counting if tiktoken available or if output_json is requested
    if output_json or _TIKTOKEN_AVAILABLE:
        in_tokens = count_tokens(text, model=model)
        out_tokens = count_tokens(compacted, model=model)
    else:
        in_tokens = estimate_tokens(text)
        out_tokens = estimate_tokens(compacted)
    
    reduction_pct = reduction(before=text, after=compacted)
    return CompactionResult(
        original=text,
        compacted=compacted,
        in_tokens=in_tokens,
        out_tokens=out_tokens,
        reduction_percent=reduction_pct,
    )


def reduction(before: str, after: str) -> float:
    """Return approximate token reduction as a fraction from 0 to 1."""
    old = estimate_tokens(before)
    new = estimate_tokens(after)
    if old == 0:
        return 0.0
    return min(1.0, max(0.0, 1.0 - new / old))
=======
def _compact_lines(text: str, *, redact_mode: RedactionMode, aggressive: bool = False) -> str:
    had_final_newline = text.endswith(("\n", "\r")); lines = text.splitlines(); technical = _looks_like_technical_content(lines)
    cleaned = [_redact_secrets(line, redact_mode) if redact_mode != "off" else line for line in lines]
    result = "\n".join(cleaned) if technical else "\n".join(deduplicate(cleaned, aggressive=aggressive))
    if had_final_newline and result: result += "\n"
    return result


class RealtimeCompactor:
    """Compact complete lines while protecting code detected later in aggressive streams."""
    _LOOKAHEAD_LINES = 4
    def __init__(self, *, redact_secrets: bool = True, redaction_mode: RedactionMode | None = None, tokenizer: TokenizerLike | None = None, aggressive: bool = False):
        if redaction_mode is None: redaction_mode = "common" if redact_secrets else "off"
        _validate_redaction_mode(redaction_mode)
        self.redaction_mode = redaction_mode; self.tokenizer = tokenizer; self.aggressive = aggressive
        self._buffer = ""; self._seen: set[str] = set(); self._previous_key: str | None = None; self._technical = False
        self._original_parts: list[str] = []; self._output_parts: list[str] = []; self._pending_lines: list[tuple[str, str]] = []; self.finished = False
    def _flush_pending(self, *, force: bool = False) -> str:
        if not self._pending_lines: return ""
        snapshot = [line for line, _ in self._pending_lines]
        if _looks_like_technical_content(snapshot): self._technical = True
        if self.aggressive and not self._technical and not force and len(self._pending_lines) < self._LOOKAHEAD_LINES: return ""
        pending = self._pending_lines; self._pending_lines = []; output: list[str] = []
        for line, newline in pending:
            key = _line_key(line); duplicate = False if self._technical else (key in self._seen if self.aggressive else key == self._previous_key)
            self._previous_key = key
            if duplicate: continue
            self._seen.add(key); value = line + newline; self._output_parts.append(value); output.append(value)
        return "".join(output)
    def _process_line(self, raw_line: str, newline: str) -> str:
        line = _redact_secrets(raw_line, self.redaction_mode).rstrip("\r\n")
        if not line.strip(): return ""
        if self.aggressive:
            self._pending_lines.append((line, newline)); return self._flush_pending()
        self._technical = self._technical or _looks_like_technical_content([line])
        key = _line_key(line); duplicate = False if self._technical else key == self._previous_key; self._previous_key = key
        if duplicate: return ""
        self._seen.add(key); value = line + newline; self._output_parts.append(value); return value
    def feed(self, chunk: str) -> str:
        if self.finished: raise RuntimeError("RealtimeCompactor is already finished")
        if not isinstance(chunk, str): raise TypeError("chunk must be a string")
        if not chunk: return ""
        self._original_parts.append(chunk); self._buffer += chunk; output: list[str] = []; start = 0; i = 0
        while i < len(self._buffer):
            char = self._buffer[i]
            if char == "\n":
                raw_end = i - 1 if i > start and self._buffer[i - 1] == "\r" else i; output.append(self._process_line(self._buffer[start:raw_end], "\n")); start = i + 1
            elif char == "\r":
                if i + 1 >= len(self._buffer): break
                if self._buffer[i + 1] == "\n": output.append(self._process_line(self._buffer[start:i], "\n")); start = i + 2; i += 1
                else: output.append(self._process_line(self._buffer[start:i], "\n")); start = i + 1
            i += 1
        self._buffer = self._buffer[start:]; return "".join(output)
    def finish(self) -> str:
        if self.finished: return ""
        self.finished = True; output: list[str] = []
        if self._buffer: output.append(self._process_line(self._buffer, "")); self._buffer = ""
        output.append(self._flush_pending(force=True)); return "".join(output)
    @property
    def original(self) -> str: return "".join(self._original_parts)
    @property
    def compacted(self) -> str: return "".join(self._output_parts)
    @property
    def in_tokens(self) -> int: return estimate_tokens(self.original, self.tokenizer)
    @property
    def out_tokens(self) -> int: return estimate_tokens(self.compacted, self.tokenizer)
    @property
    def token_count_is_exact(self) -> bool: return self.tokenizer is not None
    @property
    def token_count_source(self) -> str: return "supplied-tokenizer" if self.tokenizer is not None else "approximate"
    @property
    def reduction_percent(self) -> float: return reduction(self.original, self.compacted, tokenizer=self.tokenizer)
    @property
    def token_change_percent(self) -> float:
        old = self.in_tokens; return 0.0 if old == 0 else (1.0 - self.out_tokens / old) * 100.0
    @property
    def output_grew(self) -> bool: return self.out_tokens > self.in_tokens
    def result(self) -> CompactionResult:
        if not self.finished: raise RuntimeError("Call finish() before requesting the final result")
        return CompactionResult(self.original, self.compacted, self.in_tokens, self.out_tokens, self.reduction_percent, self.token_count_is_exact, self.token_count_source, self.token_change_percent, self.output_grew)

def compact_stream(chunks: Iterable[str], *, redact_secrets: bool = True, redaction_mode: RedactionMode | None = None, tokenizer: TokenizerLike | None = None, aggressive: bool = False) -> Iterator[str]:
    compactor = RealtimeCompactor(redact_secrets=redact_secrets, redaction_mode=redaction_mode, tokenizer=tokenizer, aggressive=aggressive)
    for chunk in chunks:
        emitted = compactor.feed(chunk)
        if emitted: yield emitted
    final = compactor.finish()
    if final: yield final

def compact_text(text: str, *, redact_secrets: bool = True, redaction_mode: RedactionMode | None = None, aggressive: bool = False) -> str:
    if not isinstance(text, str): raise TypeError("text must be a string")
    if not text: return ""
    if redaction_mode is None: redaction_mode = "common" if redact_secrets else "off"
    _validate_redaction_mode(redaction_mode); return _compact_lines(text, redact_mode=redaction_mode, aggressive=aggressive)

def compact_text_with_metrics(text: str, *, redact_secrets: bool = True, redaction_mode: RedactionMode | None = None, tokenizer: TokenizerLike | None = None, aggressive: bool = False) -> CompactionResult:
    if not isinstance(text, str): raise TypeError("text must be a string")
    compacted = compact_text(text, redact_secrets=redact_secrets, redaction_mode=redaction_mode, aggressive=aggressive)
    in_tokens, exact, source = _token_count_with(tokenizer, text); out_tokens, _, _ = _token_count_with(tokenizer, compacted)
    change = 0.0 if in_tokens == 0 else (1.0 - out_tokens / in_tokens) * 100.0
    return CompactionResult(text, compacted, in_tokens, out_tokens, max(0.0, change / 100.0), exact, source, change, out_tokens > in_tokens)

def reduction(before: str, after: str, *, tokenizer: TokenizerLike | None = None) -> float:
    if not isinstance(before, str) or not isinstance(after, str): raise TypeError("before and after must be strings")
    old = estimate_tokens(before, tokenizer); new = estimate_tokens(after, tokenizer)
    return 0.0 if old == 0 else min(1.0, max(0.0, 1.0 - new / old))

def save_memory(path: str | Path, memory: Memory) -> None:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(asdict(memory), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def load_memory(path: str | Path) -> Memory:
    target = Path(path)
    if not target.exists(): return Memory()
    try: raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc: raise ValueError(f"Could not read memory file: {exc}") from exc
    if not isinstance(raw, dict): raise ValueError("Memory file must contain a JSON object")
    return Memory.from_dict(raw)

def merge_list(current: Iterable[str], incoming: Iterable[str]) -> list[str]: return deduplicate([*current, *incoming], aggressive=True)

def merge_memory(current: Memory, incoming: Memory) -> Memory:
    return Memory(project=incoming.project or current.project, goal=incoming.goal or current.goal, state=merge_list(current.state, incoming.state), decisions=merge_list(current.decisions, incoming.decisions), files=merge_list(current.files, incoming.files), issues=merge_list(current.issues, incoming.issues), next_steps=merge_list(current.next_steps, incoming.next_steps), preferences=merge_list(current.preferences, incoming.preferences), history=merge_list(current.history, incoming.history))

def memory_to_text(memory: Memory) -> str:
    sections: list[str] = []
    if memory.project: sections.append(f"PROJECT: {memory.project}")
    if memory.goal: sections.append(f"GOAL: {memory.goal}")
    for title, values in [("STATE", memory.state), ("DECISIONS", memory.decisions), ("FILES", memory.files), ("ISSUES", memory.issues), ("NEXT", memory.next_steps), ("PREFERENCES", memory.preferences), ("HISTORY", memory.history)]:
        values = deduplicate(values, aggressive=True)
        if values: sections.append(title + ":\n" + "\n".join(f"- {value}" for value in values))
    return "\n\n".join(sections)

if __name__ == "__main__":
    import argparse

    import sys

    parser = argparse.ArgumentParser(description="Compact text for AI Token Saver.")
    parser.add_argument("text", nargs="?", help="Text to compact.")
    parser.add_argument(
        "--keep-secrets",
        action="store_true",
        help="Disable the default secret redaction (not recommended).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed metrics including in/out token counts.",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read text from stdin instead of command line argument.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON for automation/pipeline integration.",
    )
    parser.add_argument(
        "--aggression",
        choices=["safe", "balanced", "aggressive"],
        default="balanced",
        help="Compression level: safe (minimal), balanced (default), aggressive (max)",
    )
    parser.add_argument(
        "--model",
        default="gpt-3.5-turbo",
        help="Model name for accurate token counting (default: gpt-3.5-turbo)",
    )
    args = parser.parse_args()
    
    if args.stdin:
        source = sys.stdin.read()
    elif args.text:
        # Convert literal \n to actual newlines for CLI convenience
        source = args.text.replace("\\n", "\n")
    else:
        source = ""
    
    if args.json or args.verbose:
        result = compact_text_with_metrics(
            source, 
            redact_secrets=not args.keep_secrets,
            aggression=args.aggression,
            model=args.model,
            output_json=args.json
        )
        if args.json:
            # Output structured JSON for automation
            output = {
                "original_tokens": result.in_tokens,
                "compressed_tokens": result.out_tokens,
                "saved_tokens": result.in_tokens - result.out_tokens,
                "reduction_percent": round(result.reduction_percent * 100, 2),
                "text": result.compacted
            }
            print(json.dumps(output, indent=2))
        else:
            print(result.compacted)
            print(f"\n--- Metrics ---")
            print(f"Input tokens:  {result.in_tokens}")
            print(f"Output tokens: {result.out_tokens}")
            print(f"Saved tokens:  {result.in_tokens - result.out_tokens}")
            print(f"Reduction:     {result.reduction_percent:.1%}")
    else:
        compacted = compact_text(source, redact_secrets=not args.keep_secrets, aggression=args.aggression)
        print(compacted)
        print(f"\nApprox. token reduction: {reduction(source, compacted):.1%}")
=======
    parser = argparse.ArgumentParser(description="Compact text for AI Token Saver.")
    parser.add_argument("text", nargs="?", help="Text to compact.")
    parser.add_argument("--keep-secrets", action="store_true", help="Disable default secret redaction.")
    parser.add_argument("--redaction", choices=("off", "common", "strict"), help="Secret redaction mode.")
    parser.add_argument("--aggressive", action="store_true", help="Use global duplicate removal for non-technical prose.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed metrics.")
    args = parser.parse_args(); mode = args.redaction or ("off" if args.keep_secrets else "common")
    result = compact_text_with_metrics(args.text or "", redaction_mode=mode, aggressive=args.aggressive)
    print(result.compacted, end="" if result.compacted.endswith("\n") else "\n")
    if args.verbose:
        print("\n--- Metrics ---"); print(f"Input tokens:  {result.in_tokens}"); print(f"Output tokens: {result.out_tokens}"); print(f"Saved tokens:  {result.in_tokens - result.out_tokens}"); print(f"Reduction:     {result.reduction_percent:.1%}"); print(f"Token change:  {result.token_change_percent:+.1f}%"); print(f"Output grew:   {result.output_grew}"); print(f"Token count:   {result.token_count_source}")
    else: print(f"Measured token reduction: {result.reduction_percent:.1%} ({result.token_count_source})")

