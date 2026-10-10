"""Provider-neutral model catalog: map the three quality tiers to whatever is available.

Tiers keep their Claude names internally (haiku < sonnet < opus) because the router,
optimizer and CLI already use them, but they stand for "light", "standard" and "deep"
on any provider. A GPT, Gemini or local model is placed in the same tier by what it is
for (mini/flash -> light, plain -> standard, pro/ultra -> deep), and the router asks for
a *tier*, not a vendor model. No API keys are used: every provider is a CLI that is
already signed in on the machine.

Configuration (all optional):
  AITS_PROVIDERS            comma list of enabled providers, in preference order
  AITS_<PROVIDER>_<TIER>_MODEL   concrete model for a tier, TIER = LIGHT | STANDARD | DEEP
                            (Claude also honours the older AITS_HAIKU/SONNET/OPUS_MODEL)
  AITS_CUSTOM_PROVIDERS     JSON {"name": {"cmd": "tool --model {model} --effort {effort}",
                            "light": "...", "standard": "...", "deep": "..."}}; the prompt
                            is sent on stdin
"""
from __future__ import annotations

import json
import re
import shlex
import shutil

RANKS = ("haiku", "sonnet", "opus")               # ascending quality
TIER_NAMES = {"haiku": "light", "sonnet": "standard", "opus": "deep"}
_TIER_ALIASES = {"light": "haiku", "standard": "sonnet", "deep": "opus"}

# Built-in providers. ``tiers`` are defaults; an empty model string means "the CLI's own
# default model" and omits the model flag. Codex model names change often, so only the
# standard tier has a default there; set AITS_CODEX_LIGHT_MODEL / _DEEP_MODEL to add more.
BUILTIN = {
    "claude": {"binary": "claude", "tiers": {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus"}},
    "codex": {"binary": "codex", "tiers": {"sonnet": ""}},
}

_LIGHT = re.compile(r"(?<![a-z])(?:mini|nano|flash|lite|small|light|fast|haiku)(?![a-z])")
_DEEP = re.compile(r"(?<![a-z])(?:pro|ultra|max|deep|large|opus|o[134])(?![a-z0-9])")


def tier_of_model(name: str | None) -> str:
    """Rank (haiku/sonnet/opus) for any model id; unknown models count as standard."""
    m = (name or "").lower()
    for rank in RANKS:
        if rank in m:
            return rank
    if m in _TIER_ALIASES:
        return _TIER_ALIASES[m]
    if _LIGHT.search(m):
        return "haiku"
    if _DEEP.search(m):
        return "opus"
    return "sonnet"


def provider_of_model(name: str | None) -> str | None:
    """Which built-in provider a model id belongs to, or None when unknown."""
    m = (name or "").lower()
    if any(k in m for k in ("claude", "anthropic", "opus", "sonnet", "haiku")):
        return "claude"
    if re.search(r"gpt|codex|openai|(?<![a-z])o[134](?![a-z0-9])", m):
        return "codex"
    return None


def _custom(env) -> dict[str, dict]:
    raw = env.get("AITS_CUSTOM_PROVIDERS")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"AITS_CUSTOM_PROVIDERS is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise ValueError("AITS_CUSTOM_PROVIDERS must be a JSON object")
    return data


def _env_model(provider: str, rank: str, env) -> str | None:
    names = [f"AITS_{provider.upper()}_{TIER_NAMES[rank].upper()}_MODEL"]
    if provider == "claude":
        names.append(f"AITS_{rank.upper()}_MODEL")  # legacy names
    for name in names:
        if env.get(name):
            return env[name]
    return None


def catalog(env, providers=None) -> dict[str, dict]:
    """Enabled providers in preference order: {name: {"tiers": {rank: model}, "argv": [...] | None}}.

    ``providers`` (a mapping, as accepted by route()) overrides detection; it is how a
    host agent states exactly which models it can reach.
    """
    if providers is not None:
        return {name: {"tiers": _tiers_from_spec(spec), "argv": _argv_from_spec(spec)}
                for name, spec in providers.items()}
    custom = _custom(env)
    wanted = [p.strip() for p in env.get("AITS_PROVIDERS", "").split(",") if p.strip()]
    if not wanted:
        # Detect installed CLIs, but only when the environment actually carries a PATH;
        # otherwise (and when nothing is found) fall back to Claude, the original default.
        path = env.get("PATH")
        wanted = [n for n, spec in BUILTIN.items() if path and shutil.which(spec["binary"], path=path)]
        wanted += [n for n in custom if n not in wanted]
        wanted = wanted or ["claude"]
    result: dict[str, dict] = {}
    for name in wanted:
        if name in custom:
            result[name] = {"tiers": _tiers_from_spec(custom[name]), "argv": _argv_from_spec(custom[name])}
        elif name in BUILTIN:
            tiers = dict(BUILTIN[name]["tiers"])
            for rank in RANKS:
                override = _env_model(name, rank, env)
                if override:
                    tiers[rank] = override
            result[name] = {"tiers": tiers, "argv": None}
        else:
            raise ValueError(f"unknown provider {name!r}; define it in AITS_CUSTOM_PROVIDERS or use one of {tuple(BUILTIN)}")
    return result


def _tiers_from_spec(spec) -> dict[str, str]:
    tiers = {}
    for tier, rank in _TIER_ALIASES.items():
        if spec.get(tier) is not None:
            tiers[rank] = str(spec[tier])
    for rank in RANKS:  # also accept the Claude-style names
        if spec.get(rank) is not None:
            tiers[rank] = str(spec[rank])
    return tiers


def _argv_from_spec(spec) -> list[str] | None:
    cmd = spec.get("cmd")
    return shlex.split(cmd) if cmd else None


def order(cat: dict[str, dict], main: str | None) -> list[str]:
    """Provider preference: the main model's own provider first, then the configured order."""
    first = provider_of_model(main)
    names = list(cat)
    return ([first] if first in cat else []) + [n for n in names if n != first]


def _nearest(cat: dict[str, dict], names: list[str], rank: str) -> tuple[str, str, str] | None:
    best = None
    for name in names:
        for have, model in cat[name]["tiers"].items():
            distance = abs(RANKS.index(have) - RANKS.index(rank))
            key = (distance, -RANKS.index(have))  # nearest tier; the stronger one wins a tie
            if best is None or key < best[0]:
                best = (key, name, model, have)
    return None if best is None else (best[1], best[2], best[3])


def resolve(cat: dict[str, dict], rank: str, main: str | None = None) -> tuple[str, str, str] | None:
    """(provider, model, effective_rank) for ``rank``.

    The main model's own provider is used first, at its nearest tier, even when other
    providers' CLIs are installed: a GPT main keeps to GPT tiers and a Claude main to
    Claude tiers. Other providers are used only when the main model's provider has no
    model at all, and then an exact tier match wins before the nearest tier.
    """
    names = order(cat, main)
    own = provider_of_model(main)
    if own in cat and cat[own]["tiers"]:
        return _nearest(cat, [own], rank)
    for name in names:
        if rank in cat[name]["tiers"]:
            return name, cat[name]["tiers"][rank], rank
    return _nearest(cat, names, rank)
