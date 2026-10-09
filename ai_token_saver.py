"""AI Token Saver: conservative, dependency-free context compaction and memory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from functools import lru_cache
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


# Key names whose values are treated as secrets. "apikey" (no separator) is
# intentionally not matched; see tests/test_bug_hunter_regressions.py.
_SECRET_KEY = r"(?:api[_-]key|access[_-]?token|auth[_-]?token|password|secret)"
# key [: type annotation] (=|:) value.  The key may be quoted (JSON, YAML, dict
# literals); the value is a complete quoted string or a bare token.  "==" is a
# comparison, not an assignment, so it is never matched.
_SECRET_ASSIGN = re.compile(
    r"(?i)(?P<pre>(?P<q>[\"']?)\b" + _SECRET_KEY + r"\b(?P=q)"
    r"(?:\s*:\s*[A-Za-z_][\w.\[\], |]*?)?\s*[:=](?!=)\s*)"
    r"(?P<val>\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|[^\s,;}\])]+)"
)
_SECRET_PATTERNS = (
    _SECRET_ASSIGN,
    re.compile(r"(?i)(\bBearer\s+)([A-Za-z0-9._~+/=-]{16,})"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
)
_DOTTED_NAME = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$")
_CALL_ARGUMENTS = re.compile(r"[\w\])]\s*\([^()]*$")  # text ends inside "name(" ... unclosed
_NUMERIC = re.compile(r"^[+-]?\d[\d_.eE+-]*$")
_NON_SECRET_BARE = frozenset({"none", "null", "nil", "true", "false", "undefined"})

_CODE_HINTS = (
    "```", "#!/", "import ", "from ", "def ", "class ", "function ",
    "const ", "let ", "var ", "return ", "print(", "lambda ", "yield ",
    "raise ", "assert ", "with ", "try:", "except", "finally:", "async ",
    "await ", "elif ", "else:", "match ", "case ", "SELECT ", "INSERT ",
    "UPDATE ", "DELETE ", "curl ", "npm ", "pip ", "python ", "powershell ",
    "docker ", "kubectl ", "=>", "::", "&&", "||", "./", "../",
)

_CODE_HINT_RE = re.compile("|".join(re.escape(hint) for hint in _CODE_HINTS))  # one pass instead of ~45 scans

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


def _is_reference(value: str) -> bool:
    """True for values that read a secret instead of containing one.

    Calls, subscripts, attribute access, environment references and literals such
    as None are code or configuration, not secret material. Replacing them would
    change what the code does, so they are left untouched.
    """
    return (
        any(ch in value for ch in "()[]{}")
        or value.startswith(("$", "%", "<"))
        or bool(_DOTTED_NAME.match(value))
        or value.lower() in _NON_SECRET_BARE
    )


def _redact_assignment(match: "re.Match[str]") -> str:
    pre, value = match.group("pre"), match.group("val")
    if value[0] in "\"'":
        if len(value) <= 2:
            return match.group(0)  # empty string: nothing to hide
        return f"{pre}{value[0]}[REDACTED]{value[0]}"  # keep quotes: JSON/Python stay parseable
    if _is_reference(value):
        return match.group(0)
    # Inside an unclosed "(" this is a keyword argument such as f(password=pw): the
    # value is a variable reference, and a literal secret would have been quoted.
    if _CALL_ARGUMENTS.search(match.string[: match.start()]):
        return match.group(0)
    if match.group("q"):
        # JSON / dict literal: a bare value is a number (redact, as a string so the
        # document stays valid) or a variable reference (keep).
        return f'{pre}"[REDACTED]"' if _NUMERIC.match(value) else match.group(0)
    return f"{pre}[REDACTED]"


def _redact_secrets(text: str, mode: RedactionMode = "common") -> str:
    """Redact credentials. This is separate from compaction and is NOT lossless."""
    if mode == "off":
        return text
    result = _SECRET_PATTERNS[0].sub(_redact_assignment, text)
    result = _SECRET_PATTERNS[1].sub(lambda m: m.group(1) + "[REDACTED]", result)
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
    if _CODE_SYNTAX.match(stripped) or _CODE_HINT_RE.search(stripped):
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
    return any(_looks_like_code_line(line) for line in sample_lines) or bool(_CODE_HINT_RE.search(sample))


_NEWLINE = re.compile(r"\r\n|\r|\n")
# Record lines: log/event entries (a leading timestamp, or an upper-case level
# token), list items (YAML sequences, Markdown/numbered lists) and ``key: value``
# entries. Identical consecutive records are separate data points (their repeat
# count matters), so they are never removed. The level match is upper-case only so
# ordinary prose such as "error" is unaffected.
_EVENT_RECORD = re.compile(
    r"^\s*\[?\d{4}-\d{2}-\d{2}|^\s*\[?\d{1,2}:\d{2}:\d{2}"
    r"|\b(?:TRACE|DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|FATAL|CRITICAL)\b"
    r"|^\s*(?:[-*+]|\d+[.)])\s+\S"
    r"|^\s*[A-Za-z_][\w.-]*:\s"
)


def _is_event_record(line: str) -> bool:
    return bool(_EVENT_RECORD.search(line))


@lru_cache(maxsize=8192)
def _is_technical_line(line: str) -> bool:
    """Cached per-line technical test: repeated lines (the case compaction targets) are classified once."""
    return _looks_like_technical_content([line])


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
    """Batch compaction. Runs the streaming engine over the whole text so that batch
    and streaming output are identical by construction."""
    compactor = RealtimeCompactor(redaction_mode=redact_mode, aggressive=aggressive, _retain_original=False)
    return compactor.feed(text) + compactor.finish()


class RealtimeCompactor:
    """Line-oriented compaction that gives identical output for any chunking.

    Processing levels (kept distinct):
    * lossless:  nothing is removed. Line endings are normalised to "\\n".
    * conservative (default): drops blank-line runs beyond one paragraph break and
      consecutive duplicate prose lines. Code, JSON and other technical content,
      and log/event records, are never deduplicated.
    * intentionally lossy: ``aggressive=True`` removes any repeated prose line;
      secret redaction replaces credentials with ``[REDACTED]``.
    Redaction is not compaction: it is lossy by design and is never counted as
    lossless.
    """

    _LOOKAHEAD_LINES = 4

    def __init__(
        self,
        *,
        redact_secrets: bool = True,
        redaction_mode: RedactionMode | None = None,
        tokenizer: TokenizerLike | None = None,
        aggressive: bool = False,
        _retain_original: bool = True,
    ):
        if redaction_mode is None:
            redaction_mode = "common" if redact_secrets else "off"
        _validate_redaction_mode(redaction_mode)
        self.redaction_mode = redaction_mode
        self.tokenizer = tokenizer
        self.aggressive = aggressive
        self._retain_original = _retain_original
        self._tail: list[str] = []  # unterminated final line, kept as parts (O(n) for 1-char chunks)
        self._seen: set[str] = set()
        self._previous_key: str | None = None
        self._technical = False
        self._original_parts: list[str] = []
        self._output_parts: list[str] = []
        self._pending_lines: list[tuple[str, str]] = []
        self._pending_technical = False
        self._blank_newlines: list[str] = []
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
            if not line.strip():
                self._blank_newlines.append(newline or "\n")
                continue
            key = _line_key(line)
            duplicate = False if self._technical or _is_event_record(line) else (
                key in self._seen if self.aggressive else key == self._previous_key
            )
            self._previous_key = key
            if duplicate:
                continue
            self._seen.add(key)
            if self._blank_newlines:
                if self._technical:
                    output.extend(self._blank_newlines)  # code: blank lines are preserved exactly
                elif self._output_parts or output:
                    output.append("\n")  # prose: one blank line keeps the paragraph boundary
                self._blank_newlines = []
            output.append(line + newline)
        value = "".join(output)
        if value:
            self._output_parts.append(value)
        return value

    def _process_line(self, raw_line: str, newline: str) -> str:
        line = _redact_secrets(raw_line, self.redaction_mode)
        self._pending_lines.append((line, newline))
        if not (self._technical or self._pending_technical) and line.strip():
            self._pending_technical = _is_technical_line(line)
        return self._flush_pending()

    def _consume(self, text: str, *, final: bool) -> str:
        """Process complete lines in ``text``; keep any unterminated tail."""
        hold_cr = not final and text.endswith("\r")  # a following "\n" may complete "\r\n"
        limit = len(text) - 1 if hold_cr else len(text)
        output: list[str] = []
        position = 0
        for match in _NEWLINE.finditer(text, 0, limit):
            output.append(self._process_line(text[position:match.start()], "\n"))
            position = match.end()
        rest = text[position:]
        if final:
            if rest:
                output.append(self._process_line(rest, ""))
        elif rest:
            self._tail = [rest]
        return "".join(output)

    def feed(self, chunk: str) -> str:
        if self.finished:
            raise RuntimeError("RealtimeCompactor is already finished")
        if not isinstance(chunk, str):
            raise TypeError("chunk must be a string")
        if not chunk:
            return ""
        if self._retain_original:
            self._original_parts.append(chunk)
        if "\n" not in chunk and "\r" not in chunk:
            self._tail.append(chunk)  # no line end yet: just extend the partial line
            return ""
        text = "".join(self._tail) + chunk
        self._tail = []
        return self._consume(text, final=False)

    def finish(self) -> str:
        if self.finished:
            return ""
        self.finished = True
        text = "".join(self._tail)
        self._tail = []
        output = [self._consume(text, final=True) if text else ""]
        output.append(self._flush_pending(force=True))
        # Trailing blank lines: kept for code (exact), dropped for prose.
        if self._technical and self._blank_newlines:
            tail = "".join(self._blank_newlines)
            self._output_parts.append(tail)
            output.append(tail)
        self._blank_newlines = []
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


def memory_to_text(memory: Memory) -> str:
    """Render structured memory as compact, readable context text."""
    if not isinstance(memory, Memory):
        raise TypeError("memory must be a Memory")

    sections: list[str] = []
    for title, value in (("PROJECT", memory.project), ("GOAL", memory.goal)):
        if value:
            sections.append(f"{title}: {value}")

    for title, values in (
        ("STATE", memory.state),
        ("DECISIONS", memory.decisions),
        ("FILES", memory.files),
        ("ISSUES", memory.issues),
        ("NEXT", memory.next_steps),
        ("PREFERENCES", memory.preferences),
        ("HISTORY", memory.history),
    ):
        entries = [value for value in values if value]
        if entries:
            sections.append(title + ":\n" + "\n".join(f"- {value}" for value in entries))

    return "\n\n".join(sections)
