"""AI Token Saver: conservative, dependency-free context compaction and memory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import json
from pathlib import Path
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
                values[item.name] = value if isinstance(value, str) else ""
            elif item.name in list_fields:
                values[item.name] = (
                    [str(x) for x in value if isinstance(x, (str, int, float))]
                    if isinstance(value, list)
                    else []
                )
        return cls(**values)


_SECRET_PATTERNS = (
    re.compile(
        r"(?i)(\b(?:api[_-]key|access[_-]?token|auth[_-]?token|password|secret)\b\s*[:=]\s*)([^\s,;]+)"
    ),
    re.compile(r"(?i)(\bBearer\s+)([A-Za-z0-9._~+/=-]{16,})"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
)

_CODE_HINTS = (
    "```", "#!/", "import ", "from ", "def ", "class ", "function ",
    "const ", "let ", "var ", "return ", "print(", "lambda ", "yield ",
    "raise ", "assert ", "with ", "try:", "except", "finally:", "async ",
    "await ", "elif ", "else:", "match ", "case ", "SELECT ", "INSERT ",
    "UPDATE ", "DELETE ", "curl ", "npm ", "pip ", "python ", "powershell ",
    "docker ", "kubectl ", "=>", "::", "&&", "||", "./", "../",
)

_CODE_SYNTAX = re.compile(
    r"^\s*(?:"
    r"(?:def|class|if|elif|else|for|while|try|except|finally|with|match|case)\b.*:?\s*$|"
    r"(?:import|from)\s+\S+|"
    r"(?:return|yield|raise|assert|print|lambda)\b.*$|"
    r"(?:async\s+def|async\s+for|await\b).*$|"
    r"[A-Za-z_][A-Za-z0-9_.\[\]]*\s*(?:=|:=|\+=|-=|\*=|/=|//=|%=|\*\*=|&=|\|=|\^=|<<=|>>=)\s*.+$"
    r")"
)
_JSON_OBJECT = re.compile(r"^\s*\{.*\}\s*$", re.DOTALL)
_JSON_ARRAY = re.compile(r"^\s*\[.*\]\s*$", re.DOTALL)


def _fallback_token_count(text: str) -> int:
    return 0 if not text.strip() else max(1, round(len(text) / 4))


def _token_count_with(tokenizer: TokenizerLike | None, text: str) -> tuple[int, bool, str]:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if tokenizer is None:
        return _fallback_token_count(text), False, "approximate"
    if callable(tokenizer) and not hasattr(tokenizer, "encode"):
        count = tokenizer(text)
    else:
        encoded = tokenizer.encode(text)  # type: ignore[union-attr]
        try:
            count = len(encoded)  # type: ignore[arg-type]
        except TypeError as exc:
            raise TypeError("tokenizer.encode(text) must return a sized token sequence") from exc
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError("token counter must return an integer")
    if count < 0:
        raise ValueError("token count cannot be negative")
    return count, True, "supplied-tokenizer"


def estimate_tokens(text: str, tokenizer: TokenizerLike | None = None) -> int:
    return _token_count_with(tokenizer, text)[0]


def _redact_secrets(text: str, mode: RedactionMode = "common") -> str:
    if mode == "off":
        return text
    result = text
    for pattern in _SECRET_PATTERNS[:2]:
        result = pattern.sub(lambda m: m.group(1) + "[REDACTED]", result)
    result = _SECRET_PATTERNS[2].sub("[REDACTED]", result)
    if mode == "strict":
        result = _SECRET_PATTERNS[3].sub("[REDACTED]", result)
    return result


def _validate_redaction_mode(mode: RedactionMode) -> None:
    if mode not in {"off", "common", "strict"}:
        raise ValueError("redaction_mode must be 'off', 'common', or 'strict'")


def _line_key(line: str) -> str:
    return line.rstrip(" \t")


def _looks_like_code_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _CODE_SYNTAX.match(stripped) or any(hint in stripped for hint in _CODE_HINTS):
        return True
    if _JSON_OBJECT.match(stripped) or _JSON_ARRAY.match(stripped):
        try:
            parsed = json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            return False
        return isinstance(parsed, (dict, list))
    return False


def _looks_like_technical_content(lines: list[str]) -> bool:
    sample_lines = lines[:80]
    sample = "\n".join(sample_lines)
    if not sample.strip():
        return False
    return any(_looks_like_code_line(line) for line in sample_lines) or any(
        hint in sample for hint in _CODE_HINTS
    )


def deduplicate(lines: Iterable[str], *, aggressive: bool = False) -> list[str]:
    source = list(lines)
    if any(not isinstance(line, str) for line in source):
        raise TypeError("lines must contain only strings")
    if _looks_like_technical_content(source):
        return [line.rstrip("\r\n") for line in source if line.rstrip("\r\n").strip()]

    result: list[str] = []
    seen: set[str] = set()
    previous_key: str | None = None
    for raw in source:
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        key = _line_key(line)
        duplicate = key in seen if aggressive else key == previous_key
        if not duplicate:
            result.append(line)
            seen.add(key)
        previous_key = key
    return result


def _deduplicate_memory_facts(lines: Iterable[str]) -> list[str]:
    """Deduplicate stored memory facts independently of conversation code detection."""
    result: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        if not isinstance(raw, str):
            raise TypeError("memory facts must contain only strings")
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        key = _line_key(line)
        if key in seen:
            continue
        seen.add(key)
        result.append(line)
    return result


def _compact_lines(text: str, *, redact_mode: RedactionMode, aggressive: bool = False) -> str:
    had_final_newline = text.endswith(("\n", "\r"))
    lines = text.splitlines()
    technical = _looks_like_technical_content(lines)
    cleaned = [
        _redact_secrets(line, redact_mode) if redact_mode != "off" else line
        for line in lines
    ]
    result = "\n".join(cleaned) if technical else "\n".join(
        deduplicate(cleaned, aggressive=aggressive)
    )
    if had_final_newline and result:
        result += "\n"
    return result


class RealtimeCompactor:
    _LOOKAHEAD_LINES = 4

    def __init__(
        self,
        *,
        redact_secrets: bool = True,
        redaction_mode: RedactionMode | None = None,
        tokenizer: TokenizerLike | None = None,
        aggressive: bool = False,
    ):
        if redaction_mode is None:
            redaction_mode = "common" if redact_secrets else "off"
        _validate_redaction_mode(redaction_mode)
        self.redaction_mode = redaction_mode
        self.tokenizer = tokenizer
        self.aggressive = aggressive
        self._buffer = ""
        self._seen: set[str] = set()
        self._previous_key: str | None = None
        self._technical = False
        self._original_parts: list[str] = []
        self._output_parts: list[str] = []
        self._pending_lines: list[tuple[str, str]] = []
        self._pending_technical = False
        self.finished = False

    def _flush_pending(self, *, force: bool = False) -> str:
        if not self._pending_lines:
            return ""
        if self._pending_technical:
            self._technical = True
        if self.aggressive and not self._technical and not force and len(self._pending_lines) < self._LOOKAHEAD_LINES:
            return ""

        pending = self._pending_lines
        self._pending_lines = []
        self._pending_technical = False
        output: list[str] = []
        for line, newline in pending:
            key = _line_key(line)
            code_line = _looks_like_code_line(line)
            duplicate = False if self._technical or code_line else (
                key in self._seen if self.aggressive else key == self._previous_key
            )
            self._previous_key = key
            if duplicate:
                continue
            self._seen.add(key)
            value = line + newline
            self._output_parts.append(value)
            output.append(value)
        return "".join(output)

    def _process_line(self, raw_line: str, newline: str) -> str:
        line = _redact_secrets(raw_line, self.redaction_mode).rstrip("\r\n")
        if not line.strip():
            return ""
        if self.aggressive:
            self._pending_lines.append((line, newline))
            self._pending_technical = self._pending_technical or _looks_like_code_line(line)
            return self._flush_pending()

        self._technical = self._technical or _looks_like_code_line(line) or _looks_like_technical_content([line])
        key = _line_key(line)
        duplicate = False if self._technical else key == self._previous_key
        self._previous_key = key
        if duplicate:
            return ""
        self._seen.add(key)
        value = line + newline
        self._output_parts.append(value)
        return value

    def feed(self, chunk: str) -> str:
        if self.finished:
            raise RuntimeError("RealtimeCompactor is already finished")
        if not isinstance(chunk, str):
            raise TypeError("chunk must be a string")
        if not chunk:
            return ""

        self._original_parts.append(chunk)
        self._buffer += chunk
        output: list[str] = []

        # Only retain the final incomplete line. The previous character-by-character
        # scanner repeatedly rescanned the entire unterminated buffer when a stream
        # delivered one character at a time, making streaming effectively O(n^2).
        trailing_cr = self._buffer.endswith("\r")
        scan_buffer = self._buffer[:-1] if trailing_cr else self._buffer
        parts = scan_buffer.splitlines(keepends=True)
        self._buffer = ""
        if parts and not parts[-1].endswith(("\n", "\r")):
            self._buffer = parts.pop()
        if trailing_cr:
            self._buffer += "\r"

        for part in parts:
            if part.endswith("\r\n"):
                output.append(self._process_line(part[:-2], "\n"))
            elif part.endswith("\n") or part.endswith("\r"):
                output.append(self._process_line(part[:-1], "\n"))
            else:
                # Defensive fallback; normally only the final incomplete part reaches here.
                self._buffer = part + self._buffer

        return "".join(output)

    def finish(self) -> str:
        if self.finished:
            return ""
        self.finished = True
        output: list[str] = []
        if self._buffer:
            buffer = self._buffer
            self._buffer = ""
            if buffer.endswith("\r\n"):
                output.append(self._process_line(buffer[:-2], "\n"))
            elif buffer.endswith(("\n", "\r")):
                output.append(self._process_line(buffer[:-1], "\n"))
            else:
                output.append(self._process_line(buffer, ""))
        output.append(self._flush_pending(force=True))
        return "".join(output)

    @property
    def original(self) -> str:
        return "".join(self._original_parts)

    @property
    def compacted(self) -> str:
        return "".join(self._output_parts)

    @property
    def in_tokens(self) -> int:
        return estimate_tokens(self.original, self.tokenizer)

    @property
    def out_tokens(self) -> int:
        return estimate_tokens(self.compacted, self.tokenizer)

    @property
    def token_count_is_exact(self) -> bool:
        return self.tokenizer is not None

    @property
    def token_count_source(self) -> str:
        return "supplied-tokenizer" if self.tokenizer is not None else "approximate"

    @property
    def reduction_percent(self) -> float:
        return reduction(self.original, self.compacted, tokenizer=self.tokenizer)

    @property
    def token_change_percent(self) -> float:
        old = self.in_tokens
        return 0.0 if old == 0 else (1.0 - self.out_tokens / old) * 100.0

    @property
    def output_grew(self) -> bool:
        return self.out_tokens > self.in_tokens

    def result(self) -> CompactionResult:
        if not self.finished:
            raise RuntimeError("Call finish() before requesting the final result")
        return CompactionResult(
            self.original,
            self.compacted,
            self.in_tokens,
            self.out_tokens,
            self.reduction_percent,
            self.token_count_is_exact,
            self.token_count_source,
            self.token_change_percent,
            self.output_grew,
        )


def compact_stream(
    chunks: Iterable[str],
    *,
    redact_secrets: bool = True,
    redaction_mode: RedactionMode | None = None,
    tokenizer: TokenizerLike | None = None,
    aggressive: bool = False,
) -> Iterator[str]:
    compactor = RealtimeCompactor(
        redact_secrets=redact_secrets,
        redaction_mode=redaction_mode,
        tokenizer=tokenizer,
        aggressive=aggressive,
    )
    for chunk in chunks:
        emitted = compactor.feed(chunk)
        if emitted:
            yield emitted
    final = compactor.finish()
    if final:
        yield final


def compact_text(
    text: str,
    *,
    redact_secrets: bool = True,
    redaction_mode: RedactionMode | None = None,
    aggressive: bool = False,
) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not text:
        return ""
    if redaction_mode is None:
        redaction_mode = "common" if redact_secrets else "off"
    _validate_redaction_mode(redaction_mode)
    return _compact_lines(text, redact_mode=redaction_mode, aggressive=aggressive)


def compact_text_with_metrics(
    text: str,
    *,
    redact_secrets: bool = True,
    redaction_mode: RedactionMode | None = None,
    tokenizer: TokenizerLike | None = None,
    aggressive: bool = False,
) -> CompactionResult:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    compacted = compact_text(
        text,
        redact_secrets=redact_secrets,
        redaction_mode=redaction_mode,
        aggressive=aggressive,
    )
    in_tokens, exact, source = _token_count_with(tokenizer, text)
    out_tokens, _, _ = _token_count_with(tokenizer, compacted)
    change = 0.0 if in_tokens == 0 else (1.0 - out_tokens / in_tokens) * 100.0
    return CompactionResult(
        text,
        compacted,
        in_tokens,
        out_tokens,
        max(0.0, change / 100.0),
        exact,
        source,
        change,
        out_tokens > in_tokens,
    )


def reduction(before: str, after: str, *, tokenizer: TokenizerLike | None = None) -> float:
    if not isinstance(before, str) or not isinstance(after, str):
        raise TypeError("before and after must be strings")
    old = estimate_tokens(before, tokenizer)
    new = estimate_tokens(after, tokenizer)
    return 0.0 if old == 0 else min(1.0, max(0.0, 1.0 - new / old))


def save_memory(path: str | Path, memory: Memory) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(asdict(memory), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_memory(path: str | Path) -> Memory:
    target = Path(path)
    if not target.exists():
        return Memory()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read memory file: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Memory file must contain a JSON object")
    return Memory.from_dict(raw)


def merge_list(current: Iterable[str], incoming: Iterable[str]) -> list[str]:
    return _deduplicate_memory_facts([*current, *incoming])


def merge_memory(current: Memory, incoming: Memory) -> Memory:
    return Memory(
        project=incoming.project or current.project,
        goal=incoming.goal or current.goal,
        state=merge_list(current.state, incoming.state),
        decisions=merge_list(current.decisions, incoming.decisions),
        files=merge_list(current.files, incoming.files),
        issues=merge_list(current.issues, incoming.issues),
        next_steps=merge_list(current.next_steps, incoming.next_steps),
        preferences=merge_list(current.preferences, incoming.preferences),
        history=merge_list(current.history, incoming.history),
    )
