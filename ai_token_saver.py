"""AI Token Saver: conservative, dependency-free context compaction and memory.

Input is never rewritten on the basis of what it looks like (credentials and configuration values pass
through untouched); the only thing that changes text is the opt-in ``dedupe`` modes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from functools import lru_cache, wraps
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
from typing import Callable, Iterable, Iterator, Literal, Mapping, Protocol


class Tokenizer(Protocol):
    def encode(self, text: str) -> object: ...


TokenCounter = Callable[[str], int]
TokenizerLike = Tokenizer | TokenCounter


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


def _is_fact(value: object) -> bool:
    """Text and finite numbers are facts; booleans, NaN/inf, null and containers are ignored."""
    if isinstance(value, bool):
        return False
    return isinstance(value, (str, int)) or (isinstance(value, float) and math.isfinite(value))


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
                    [str(x) for x in value if _is_fact(x)]
                    if isinstance(value, list)
                    else []
                )
        return cls(**values)


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


def check_state_path(path: str | os.PathLike[str] | None) -> Path | None:
    """Expand a saver's ``state_path`` and reject a directory up front (shared by every saver)."""
    if not path:
        return None
    resolved = Path(path).expanduser()
    if resolved.is_dir():
        raise ValueError(f"state_path must be a file, not a directory: {resolved}")
    return resolved


def _check_tokenizer(tokenizer: TokenizerLike | None) -> None:
    if tokenizer is not None and not (callable(tokenizer) or hasattr(tokenizer, "encode")):
        raise TypeError("tokenizer must be a callable or have an encode(text) method")


def _line_key(line: str) -> str:
    return line.rstrip(" \t")


def _seen_entry(key: str) -> str | bytes:
    """What ``dedupe="global"`` remembers about a line: short lines as they are, long ones as a 16-byte
    digest, so memory grows with the number of distinct lines and not with their length."""
    if len(key) <= 64:
        return key
    return hashlib.blake2b(key.encode("utf-8", "surrogatepass"), digest_size=16).digest()


def _code_syntax_or_json(stripped: str) -> bool:
    """Code by structure (statement syntax or a JSON object/array), not by hint words."""
    if _CODE_SYNTAX.match(stripped):
        return True
    if _JSON_OBJECT.match(stripped) or _JSON_ARRAY.match(stripped):
        try:
            parsed = json.loads(stripped)
        except RecursionError:
            return True  # nested too deeply to parse, but it is bracketed JSON-like structure
        except (json.JSONDecodeError, TypeError):
            return False
        return isinstance(parsed, (dict, list))
    return False


def _looks_like_code_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return bool(_CODE_HINT_RE.search(stripped)) or _code_syntax_or_json(stripped)


def _looks_like_technical_content(lines: list[str]) -> bool:
    sample_lines = lines[:80]
    sample = "\n".join(sample_lines)
    if not sample.strip():
        return False
    return any(_looks_like_code_line(line) for line in sample_lines) or bool(_CODE_HINT_RE.search(sample))


_NEWLINE = re.compile(r"\r\n|\r|\n")
# Record lines carry data whose repeat count matters, so identical consecutive copies are
# never removed: log/event entries (a timestamp or clock time anywhere in the line, an
# upper-case level token, glog/pytest markers), list items (YAML sequences, Markdown and
# numbered lists), ``key: value`` entries and ``key=value`` pairs (logfmt, .env).
_EVENT_RECORD = re.compile(
    r"\d{4}[-/]\d{2}[-/]\d{2}|\b\d{1,2}:\d{2}:\d{2}|\b\d{1,2}/[A-Z][a-z]{2}/\d{4}"
    r"|^\s*[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:|^\s*\d{9,13}\b|^\s*[IWEF]\d{4}\s"
    r"|\b(?:TRACE|DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|FATAL|CRITICAL|FAILED|PASSED|SKIPPED|XFAIL)\b"
    r"|^\s*(?:[-*+]|\d+[.)])\s+\S|^\s*[A-Za-z_][\w.-]*:(?:\s|$)|^\s*[A-Za-z_][\w.-]*=\S"
)
# Only lines that read as plain prose may ever be dropped as duplicates. Code, markup and
# structured data are never removed, even before any later line shows the input is code.
_CODE_PUNCTUATION = re.compile(r"[{}\[\]()<>=;\\|$@^~`]|\+\+|--|->|::")
# Counts, ids, paths, file names and labels carry data, so they are never treated as prose either.
_NON_PROSE = re.compile(r"\d|\w[./\\]\w|:\s*$|\S,\S|\t")
_COMMAND_WORDS = frozenset(
    "echo cd ls cat git make npm npx pip pip3 pytest python python3 node go cargo docker kubectl curl wget rm cp mv mkdir touch "
    "export source sudo apt apt-get brew yarn pnpm gcc clang tar chmod chown ssh scp grep sed awk find tail head sleep kill".split()
)
_BARE_KEYWORDS = frozenset("pass break continue end fi done esac else then do begin return null none nil true false try finally default".split())


_CACHE_LINE_LIMIT = 256


def _cache_short_lines(function):
    """Memoise a per-line predicate for short lines only. Repeated lines are the case compaction targets,
    but long lines are computed fresh and never retained, so a stream cannot pin them in memory."""
    cached = lru_cache(maxsize=8192)(function)

    @wraps(function)
    def wrapper(line: str) -> bool:
        return cached(line) if len(line) <= _CACHE_LINE_LIMIT else function(line)

    return wrapper


@_cache_short_lines
def _is_dedupable_prose(line: str) -> bool:
    """True when ``line`` is plain prose that may be dropped as a repeat."""
    if not line or line[0].isspace() or line[0] in "#>|-*+=~_\"'" or line.endswith(","):
        return False
    if _CODE_PUNCTUATION.search(line) or _NON_PROSE.search(line) or _EVENT_RECORD.search(line):
        return False
    words = line.split()
    if words[0] in _COMMAND_WORDS or (len(words) == 1 and words[0] in _BARE_KEYWORDS):
        return False
    return any(ch.isalpha() for ch in line)


@_cache_short_lines
def _is_technical_line(line: str) -> bool:
    """Equivalent to ``_looks_like_technical_content([line])`` with one hint scan instead of two."""
    if _CODE_HINT_RE.search(line):
        return True
    stripped = line.strip()
    return bool(stripped) and _code_syntax_or_json(stripped)


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


def _compact_lines(text: str, *, aggressive: bool = False, dedupe: str | None = None) -> str:
    """Batch compaction. Runs the streaming engine over the whole text so that batch
    and streaming output are identical by construction."""
    compactor = RealtimeCompactor(aggressive=aggressive, dedupe=dedupe, retain=False)
    return compactor.feed(text) + compactor.finish()


DEDUPE_MODES = ("off", "runs", "adjacent", "global")
_RUN_MARKER = "[previous line repeated {n} more times]"
_RUN_MARKER_WIDTH = len(_RUN_MARKER.format(n=10 ** 7))  # worst case, so collapsing never makes text longer
_MARKER_LOOKALIKE = re.compile(r"\\*\[previous line repeated \d+ more times\]\Z")
_MARKER_LINE = re.compile(r"\[previous line repeated (\d+) more times\]\Z")


def _resolve_dedupe(dedupe: str | None, aggressive: bool) -> str:
    """The effective duplicate-handling mode. ``aggressive=True`` keeps meaning "global"; an
    explicit ``dedupe`` always wins."""
    mode = dedupe if dedupe is not None else ("global" if aggressive else "off")
    if mode not in DEDUPE_MODES:
        raise ValueError(f"dedupe must be one of {DEDUPE_MODES}")
    return mode


def expand_runs(text: str, *, max_chars: int | None = None) -> str:
    """Exact inverse of ``compact_text(x, dedupe="runs")``: ``expand_runs(compact_text(x, dedupe="runs")) == x``
    for every string ``x``.

    A marker line stands for N more copies of the line before it, with the same line ending. Original lines
    that merely look like a marker (optionally already prefixed with backslashes) were given one extra
    leading backslash by the compactor; it is removed here. ``max_chars`` bounds the result so a hostile
    marker count cannot exhaust memory (``ValueError`` when exceeded)."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    out: list[str] = []
    size = 0
    previous: str | None = None
    position = 0

    def add(body: str, term: str) -> None:
        nonlocal previous
        marker = _MARKER_LINE.match(body) if previous is not None and body.startswith("[") else None
        if marker is not None:
            count = int(marker.group(1))
            size_after = size + (len(previous) + len(term)) * count
            if max_chars is not None and size_after > max_chars:
                raise ValueError("expanded text exceeds max_chars")
            out.append((previous + term) * count)
            previous = None  # only the compactor writes markers, and never two in a row
            return size_after
        if body.startswith("\\") and _MARKER_LOOKALIKE.match(body):
            body = body[1:]
        out.append(body + term)
        previous = body
        return size + len(body) + len(term)

    for match in _NEWLINE.finditer(text):
        size = add(text[position:match.start()], match.group())
        position = match.end()
    if position < len(text):
        size = add(text[position:], "")
    if max_chars is not None and size > max_chars:
        raise ValueError("expanded text exceeds max_chars")
    return "".join(out)


class RealtimeCompactor:
    """Line-oriented compaction that gives identical output for any chunking.

    Nothing is rewritten by default: ``dedupe="off"`` returns the input unchanged (every character,
    blank line, indentation and line ending). ``dedupe`` selects what happens to *prose* lines that
    repeat (code, markup, structured data and log/event records are never touched in any mode):

    * ``"off"`` (default): identity. Information-preserving.
    * ``"runs"``: a long run of identical consecutive lines becomes the line plus a count marker
      (``[previous line repeated N more times]``). Exactly reversible with ``expand_runs`` and applied only
      when it makes the text shorter.
    * ``"adjacent"``: LOSSY. Drops a line identical to the previous one.
    * ``"global"``: LOSSY. Drops any line seen before (``aggressive=True`` is the same mode).

    ``retain=False`` keeps neither the input nor the output (constant memory for streams); the
    ``original``/``compacted``/``result`` accessors then raise ``RuntimeError``.
    ``redact_secrets`` and ``redaction_mode`` are accepted for backwards compatibility and ignored.
    """

    _LOOKAHEAD_LINES = 4

    def __init__(
        self,
        *,
        redact_secrets: bool = True,
        redaction_mode: str | None = None,
        tokenizer: TokenizerLike | None = None,
        aggressive: bool = False,
        dedupe: str | None = None,
        retain: bool = True,
    ):
        _check_tokenizer(tokenizer)
        self.tokenizer = tokenizer
        self.dedupe = _resolve_dedupe(dedupe, aggressive)
        self.aggressive = self.dedupe == "global"
        self._run_key: tuple[str, str] | None = None  # dedupe="runs": the (line, ending) of the run being counted
        self._run_count = 0
        self._run_need = 0
        self._run_held: list[tuple[str, str]] = []
        self._run_newline = ""
        self._retain = retain
        self._tail: list[str] = []  # unterminated final line, kept as parts (O(n) for 1-char chunks)
        self._seen: set[str | bytes] = set()
        self._previous_key: object = None
        self._technical = False
        self._original_parts: list[str] = []
        self._output_parts: list[str] = []
        self._pending_lines: list[tuple[str, str]] = []
        self._pending_technical = False
        self.finished = False

    def _end_run(self, output: list[str]) -> None:
        """Close the run being counted (dedupe="runs"): emit its count marker, or the held lines when short."""
        if self._run_key is None:
            return
        if self._run_count >= self._run_need:
            output.append(_RUN_MARKER.format(n=self._run_count - 1) + self._run_newline)
        else:
            output.extend(line + newline for line, newline in self._run_held)
        self._run_key = None
        self._run_held = []

    def _emit(self, line: str, newline: str, output: list[str]) -> None:
        """Decide one line (blank, duplicate or kept) and append what is emitted to ``output``."""
        if not line.strip():
            self._end_run(output)
            self._previous_key = None  # identical lines separated by a blank line are not repeats
            output.append(line + newline)
            return
        if self.dedupe == "runs":
            key = (line, newline)  # exact: the same text with the same ending, so expand_runs restores it
            if self._run_key is not None:
                if key == self._run_key:  # the run continues (it only starts for eligible prose)
                    self._run_count += 1
                    if self._run_count < self._run_need:
                        self._run_held.append((line, newline))
                    else:
                        self._run_held = []  # long enough to collapse: only the count matters now
                    return
                self._end_run(output)
            elif key == self._previous_key and not self._technical and _is_dedupable_prose(line):
                # Second identical prose line in a row: start counting a run. (The first one is already out.)
                self._run_key, self._run_count, self._run_held = key, 2, [(line, newline)]
                self._run_newline = newline
                self._run_need = max(3, 2 + (_RUN_MARKER_WIDTH + 1) // (len(line) + 1))
                return
            self._previous_key = key
            output.append(line + newline)
            return
        key = _line_key(line)
        duplicate = self.dedupe != "off" and not self._technical and (
            _seen_entry(key) in self._seen if self.aggressive else key == self._previous_key
        ) and _is_dedupable_prose(line)
        self._previous_key = key
        if duplicate:
            return
        if self.aggressive:  # only the global mode reads this set, so no other mode may grow it
            self._seen.add(_seen_entry(key))
        output.append(line + newline)

    def _store(self, output: list[str]) -> str:
        value = "".join(output)
        if value and self._retain:
            self._output_parts.append(value)
        return value

    def _flush_pending(self, *, force: bool = False) -> str:
        """Global mode only: decide lines in groups so code just ahead of a repeat protects it."""
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
            self._emit(line, newline, output)
        return self._store(output)

    def _process_line(self, line: str, newline: str) -> str:
        if self.dedupe == "runs" and "[previous line repeated" in line and _MARKER_LOOKALIKE.match(line):
            line = "\\" + line  # a real line that looks like a marker is escaped so expand_runs can tell them apart
        if not self.aggressive:  # conservative mode decides each line at once
            if not self._technical and line.strip() and _is_technical_line(line):
                self._technical = True
            output: list[str] = []
            self._emit(line, newline, output)
            return self._store(output)
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
            output.append(self._process_line(text[position:match.start()], match.group()))
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
        if self._retain:
            self._original_parts.append(chunk)
        if self.dedupe == "off":  # identity: no line state is needed at all
            if self._retain:
                self._output_parts.append(chunk)
            return chunk
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
        closing: list[str] = []
        self._end_run(closing)
        output.append(self._store(closing))
        return "".join(output)

    def _retained(self, parts: list[str]) -> str:
        if not self._retain:
            raise RuntimeError("this compactor was created with retain=False and keeps no text")
        return "".join(parts)

    @property
    def original(self) -> str:
        return self._retained(self._original_parts)

    @property
    def compacted(self) -> str:
        return self._retained(self._output_parts)

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
    redaction_mode: str | None = None,
    tokenizer: TokenizerLike | None = None,
    aggressive: bool = False,
    dedupe: str | None = None,
) -> Iterator[str]:
    """Compact an iterable of chunks lazily in constant memory. Options are validated when this is
    called, not on the first ``next()``, so a bad option fails even for an empty stream."""
    compactor = RealtimeCompactor(tokenizer=tokenizer, aggressive=aggressive, dedupe=dedupe, retain=False)

    def run() -> Iterator[str]:
        for chunk in chunks:
            emitted = compactor.feed(chunk)
            if emitted:
                yield emitted
        final = compactor.finish()
        if final:
            yield final

    return run()


def compact_text(
    text: str,
    *,
    redact_secrets: bool = True,
    redaction_mode: str | None = None,
    aggressive: bool = False,
    dedupe: str | None = None,
) -> str:
    """Compact ``text``. By default the text is returned unchanged; ``dedupe`` (or ``aggressive=True``)
    opts into handling repeated lines, see ``RealtimeCompactor`` for the modes and which are lossy.
    ``redact_secrets``/``redaction_mode`` are accepted for backwards compatibility and ignored."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if _resolve_dedupe(dedupe, aggressive) == "off" or not text:  # validated even for empty input
        return text
    return _compact_lines(text, aggressive=aggressive, dedupe=dedupe)


def compact_text_with_metrics(
    text: str,
    *,
    redact_secrets: bool = True,
    redaction_mode: str | None = None,
    tokenizer: TokenizerLike | None = None,
    aggressive: bool = False,
    dedupe: str | None = None,
) -> CompactionResult:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    _check_tokenizer(tokenizer)
    compacted = compact_text(text, aggressive=aggressive, dedupe=dedupe)
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
    """Write the memory file atomically: a failed or interrupted save leaves the previous file intact.

    A symlink is written through (the link is kept), and an existing file keeps its permissions."""
    target = Path(os.path.realpath(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(asdict(memory), ensure_ascii=False, indent=2) + "\n"
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())  # the data is on disk before the old file is replaced
        if target.exists():
            shutil.copymode(target, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


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


def _block(text: str) -> str:
    """Indent continuation lines so a multi-line entry cannot pose as a section header or a bullet."""
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\n  ")


def memory_to_text(memory: Memory) -> str:
    """Render structured memory as compact, readable context text."""
    if not isinstance(memory, Memory):
        raise TypeError("memory must be a Memory")

    sections: list[str] = []
    for title, value in (("PROJECT", memory.project), ("GOAL", memory.goal)):
        if value:
            sections.append(f"{title}: {_block(value)}")

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
            sections.append(title + ":\n" + "\n".join(f"- {_block(value)}" for value in entries))

    return "\n\n".join(sections)
