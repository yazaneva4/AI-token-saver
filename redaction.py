"""Secret redaction for AI Token Saver. Redaction is lossy by design and is not compaction.

Goals, in priority order: never leave a recognised credential in the text; keep Python, JSON
and YAML parseable; leave code that merely *reads* a secret (calls, attributes, subscripts,
``self.password = password``) untouched. Quoted values keep their quotes, structured values
(arrays/objects) keep their shape with every scalar masked, and private-key blocks keep their
BEGIN/END lines. Matching is by key name, so a secret stored under an unrecognised name is
not found.
"""
from __future__ import annotations

import re
from typing import Literal

RedactionMode = Literal["off", "common", "strict"]
MODES = ("off", "common", "strict")


def validate_mode(mode: str) -> None:
    if mode not in MODES:
        raise ValueError("redaction_mode must be 'off', 'common', or 'strict'")

_KEY = r"(?:api[_-]key|access[_-]?token|auth[_-]?token|private[_-]?key|passwd|password|secret)"
# DB_PASSWORD, client_secret, self.password, "api-key", secret_key ... but not "apikey" or "mypassword".
# Repetitions are bounded so a long a_b_c_... or a.b.c... chain cannot cause quadratic backtracking.
_NAME = r"(?:[A-Za-z0-9]{1,32}[_.-]){0,8}" + _KEY + r"(?:[_-][A-Za-z0-9]{1,32}){0,8}"
_PREFIX = r"[rRbBuUfF]{0,2}"
_ASSIGN = re.compile(
    r"(?i)(?P<pre>(?P<q>[\"']?)(?<![A-Za-z0-9])(?P<name>" + _NAME + r")(?![A-Za-z0-9])(?P=q)"
    r"(?:\s*:\s*[A-Za-z_][\w.\[\], |]{0,80}?)?\s*[:=](?!=)\s*)"
    r"(?P<val>" + _PREFIX + r"\"[^\"\\\n]*(?:\\.[^\"\\\n]*)*\"|" + _PREFIX + r"'[^'\\\n]*(?:\\.[^'\\\n]*)*'|[\[{]|[^\s,;&}\])]+)"
)
_NAME_ONLY = re.compile(r"(?i)^" + _NAME + r"$")
_BEARER = re.compile(r"(?i)(\bBearer\s+)([A-Za-z0-9._~+/=-]{16,})")
_AUTH_HEADER = re.compile(r"(?i)(\bAuthorization\s*[:=]\s*(?:Basic|Bearer|Token)\s+)([^\s\"',;]{8,})")
_URL_CREDENTIALS = re.compile(r"((?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]{0,30}://[^\s/:@\"']+:)([^\s/@\"']+)(@)")
_TOKEN_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
)
_GOOGLE_KEY = re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b")
_PEM_BEGIN = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----")
_PEM_BODY = re.compile(r"^(?:[A-Za-z0-9+/=]*|[A-Za-z][A-Za-z0-9-]*:\s.*)$")  # base64 lines or `Key: value` headers
_PEM_END = re.compile(r"-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----")
_PEM_ONE_LINE = re.compile(r"(-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----).*?(-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----)")
# Cheap pre-filter: a line with none of these cannot contain anything the patterns look for.
# Applied to the lower-cased line: a case-sensitive alternation is several times faster than (?i).
_TRIGGER = re.compile(r"pass|secret|key|token|bearer|begin|akia|asia|ghp_|gho_|ghu_|ghs_|ghr_|github_pat|xox|eyj|://|authorization|sk-|aiza")
# One token of a JSON / YAML-flow / Python-literal fragment: a string, a bare word, or a delimiter.
_TOKEN = re.compile(r"\"[^\"\\]*(?:\\.[^\"\\]*)*\"|'[^'\\]*(?:\\.[^'\\]*)*'|[^\s,\[\]{}\"':][^\s,\[\]{}\"']*|\S")
_KEEP_LITERALS = frozenset({"null", "true", "false", "none", "nil", "~"})
_DOTTED = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$")
_CALL_ARGUMENTS = re.compile(r"[\w\])]\s*\([^()]*$")  # text ends inside "name(" ... unclosed
_NUMERIC = re.compile(r"^[+-]?\d[\d_.eE+-]*$")
_NON_SECRET_BARE = frozenset({"none", "null", "nil", "true", "false", "undefined"})
_SELF_OBJECTS = frozenset({"self", "this", "cls"})
_BLOCK_SCALARS = frozenset({"|", "|-", "|+", ">", ">-", ">+"})
# Further space-separated words of an unquoted value (`password: correct horse battery`), stopping at
# another `key=value` pair, a comment or a delimiter.
_VALUE_TAIL = re.compile(r"(?:[ \t]+(?![A-Za-z_][\w.-]*=)[^\s,;&#}\])]+)*")
_MAX_BLOCK_LINES = 500  # a block that never closes stops being masked after this many lines
MARK = "[REDACTED]"


def _is_reference(value: str) -> bool:
    """True for values that read a secret instead of containing one."""
    return (
        any(ch in value for ch in "()[]{}")
        or value.startswith(("$", "%", "<"))
        or bool(_DOTTED.match(value))
        or value.lower() in _NON_SECRET_BARE
    )


def _structure_end(text: str, start: int, depth: int = 0) -> tuple[int | None, int]:
    """Scan JSON/YAML-flow/Python brackets from ``start``. Returns (index after the closing
    bracket or None, remaining depth). Quotes and escapes are honoured."""
    quote = ""
    i = start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch == '"' or (ch == "'" and (i == 0 or not text[i - 1].isalnum())):
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth <= 0:
                return i + 1, 0
        i += 1
    return None, depth


def _is_key(segment: str, end: int, token: str) -> bool:
    """True when the token just scanned is an object key: followed by a colon (or ending with one)."""
    if token.endswith(":") and len(token) > 1 and token[0] not in "\"'":
        return True  # YAML flow `{a: 1}`
    i = end
    while i < len(segment) and segment[i] in " \t":
        i += 1
    return i < len(segment) and segment[i] == ":"


def _mask_scalars(segment: str) -> str:
    """Mask every *value* in a structure and leave object keys, brackets and layout alone, so the
    result has the same keys (no duplicates), nesting and array lengths and stays valid JSON,
    YAML-flow or Python. Strings and numbers become "[REDACTED]"; null/true/false stay."""
    out, last = [], 0
    for match in _TOKEN.finditer(segment):
        token = match.group(0)
        if token[0] in "[]{},#" or len(token) == 1 and not token.isalnum():
            continue
        if token.lower() in _KEEP_LITERALS or _is_key(segment, match.end(), token):
            continue
        out.append(segment[last:match.start()])
        out.append(f'"{MARK}"')
        last = match.end()
    out.append(segment[last:])
    return "".join(out)


class SecretScanner:
    """Line-by-line redactor. Holds the state needed for multi-line private keys and
    multi-line secret arrays/objects, so a stream of lines gives the same result as the
    whole text at once."""

    def __init__(self, mode: RedactionMode = "common") -> None:
        validate_mode(mode)
        self.mode = mode
        self._pem = 0       # lines consumed inside an open private-key block (0 = closed)
        self._depth = 0     # open bracket depth inside a secret structure (0 = closed)
        self._block_lines = 0
        self._yaml_indent: int | None = None  # indent of a `key: |` line whose content is being masked

    # -- public ------------------------------------------------------------------
    def redact_line(self, line: str) -> str | None:
        """Redacted line, or None when the line is dropped (the body of a private key)."""
        if self.mode == "off":
            return line
        if self._pem:
            return self._pem_body(line)
        if self._depth:
            return self._block_line(line)
        if self._yaml_indent is not None:
            masked = self._yaml_block_line(line)
            if masked is not None:
                return masked
        if not _TRIGGER.search(line.lower()):
            return line
        if _PEM_BEGIN.fullmatch(line.strip()):  # a bare header line, not a quoted constant in source
            self._pem, self._block_lines = 1, 0
            return line
        return self._line(line)

    # -- internals ----------------------------------------------------------------
    def _pem_body(self, line: str) -> str | None:
        self._block_lines += 1
        if _PEM_END.search(line):
            self._pem = 0
            return line
        if not _PEM_BODY.match(line.strip()):  # not key material: the block never closed, so stop dropping lines
            self._pem = 0
            return self.redact_line(line)
        return MARK if self._block_lines == 1 else None

    def _yaml_block_line(self, line: str) -> str | None:
        """Mask a line of a `key: |` block scalar; None once the block has ended."""
        if not line.strip():
            return line
        indent = len(line) - len(line.lstrip(" \t"))
        self._block_lines += 1
        if indent > (self._yaml_indent or 0) and self._block_lines <= _MAX_BLOCK_LINES:
            return line[:indent] + MARK
        self._yaml_indent = None
        return None

    def _block_line(self, line: str) -> str:
        self._block_lines += 1
        end, depth = _structure_end(line, 0, self._depth)
        self._depth = depth
        if self._block_lines > _MAX_BLOCK_LINES:
            self._depth = 0
        if end is None:
            return self._tokens(_mask_scalars(line))
        remainder = line[end:]  # e.g. `], "other": "value"`: may hold more secrets
        return self._tokens(_mask_scalars(line[:end])) + (self._line(remainder) if remainder.strip() else remainder)

    def _line(self, line: str) -> str:
        line = _PEM_ONE_LINE.sub(lambda m: f"{m.group(1)}{MARK}{m.group(2)}", line)
        line = self._assignments(line)
        line = _AUTH_HEADER.sub(lambda m: m.group(1) + MARK, line)
        line = _URL_CREDENTIALS.sub(lambda m: m.group(1) + MARK + m.group(3), line)
        line = _BEARER.sub(lambda m: m.group(1) + MARK, line)
        return self._tokens(line)

    def _tokens(self, line: str) -> str:
        """Mask credential-shaped tokens anywhere in the line, including object keys."""
        for pattern in _TOKEN_PATTERNS:
            line = pattern.sub(MARK, line)
        if self.mode == "strict":
            line = _GOOGLE_KEY.sub(MARK, line)
        return line

    def _assignments(self, line: str) -> str:
        """Apply the assignment pattern to one line."""
        out, position = [], 0
        for match in _ASSIGN.finditer(line):
            if match.start() < position:
                continue
            replacement, consumed_to = self._assignment(match)
            out.append(line[position:match.start()])
            out.append(replacement)
            position = consumed_to
        out.append(line[position:])
        return "".join(out)

    def _assignment(self, match: "re.Match[str]") -> tuple[str, int]:
        """(replacement text, index in the line up to which the match was consumed)."""
        pre, value, name = match.group("pre"), match.group("val"), match.group("name")
        keep = (match.group(0), match.end())
        if value in ("[", "{"):
            if value == "{" and match.string[match.end(): match.end() + 1] in ("{", "%", "#"):
                return keep  # a Jinja/Ansible placeholder such as {{ vault_pw }}: a reference, not a value
            return self._structured(match)
        if value in _BLOCK_SCALARS:
            line = match.string
            self._yaml_indent, self._block_lines = len(line) - len(line.lstrip(" \t")), 0
            return keep  # the secret is on the following indented lines
        body = value.lstrip("rRbBuUfF")
        if body[:1] in ("\"", "'"):
            quote = body[0]
            if len(body) <= 2:
                return keep  # empty string: nothing to hide
            return f"{pre}{quote}{MARK}{quote}", match.end()  # string prefix drops; quotes stay, so syntax stays valid
        if _is_reference(value):
            return keep
        if _CALL_ARGUMENTS.search(match.string[: match.start()]):
            return keep  # f(password=pw): a keyword argument reading a variable
        if "." in name and name.split(".")[0].lower() in _SELF_OBJECTS:
            return keep  # self.password = password: attribute assignment is code
        if match.group("q"):
            # JSON / dict literal: a bare value is a number (mask, as a string so the document
            # stays valid) or a variable reference (keep).
            return (f'{pre}"{MARK}"', match.end()) if _NUMERIC.match(value) else keep
        if pre.rstrip().endswith(":") or pre.endswith((" ", "\t")) and pre.rstrip().endswith("="):
            tail = _VALUE_TAIL.match(match.string, match.end())
            return f"{pre}{MARK}", tail.end() if tail else match.end()
        return f"{pre}{MARK}", match.end()

    def _structured(self, match: "re.Match[str]") -> tuple[str, int]:
        """An array/object value under a secret key: keep its shape, mask every scalar."""
        text, pre = match.string, match.group("pre")
        start = match.end() - 1  # the opening bracket
        end, depth = _structure_end(text, start)
        if end is not None:
            if text[start + 1: end - 1].strip() == "REDACTED":
                return match.group(0), match.end()  # already redacted: stay idempotent
            return pre + _mask_scalars(text[start:end]), end
        # Opens here and closes on a later line: mask the rest of this line, then the following lines.
        self._depth, self._block_lines = depth, 0
        return pre + _mask_scalars(text[start:]), len(text)


_NEWLINES = re.compile(r"(\r\n|\r|\n)")


def redact_secrets(text: str, mode: RedactionMode = "common") -> str:
    """Redact credentials in ``text`` (any number of lines). Lossy; never lossless."""
    validate_mode(mode)
    if mode == "off" or not text:
        return text
    if not _TRIGGER.search(text.lower()):
        return text
    scanner = SecretScanner(mode)
    parts = _NEWLINES.split(text)  # [line, newline, line, newline, ..., line]
    out: list[str] = []
    for i in range(0, len(parts), 2):
        redacted = scanner.redact_line(parts[i])
        if redacted is None:
            continue  # dropped line: drop its newline too
        out.append(redacted)
        if i + 1 < len(parts):
            out.append(parts[i + 1])
    return "".join(out)
