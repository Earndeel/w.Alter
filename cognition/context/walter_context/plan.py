"""The contracts walter-context works with, as plain data with validation. Stdlib only.

ContextPlan     what the preflight decides for one owner message: walter-context's own output, traced.
SessionState    the working state of a thread between calls (walter-context owns it).
ThreadHint      walter-context's guess of the thread, sent to Walter Memory, which owns the final attachment.
MemoryViewQuery what walter-context asks Walter Memory for: a domain, a horizon, a depth (Memory owns the views).

JSON Schemas of the same contracts: contracts/schemas/*.vN.json. Vocabularies are closed: a new value is a new
contract version, not a silent extension. ContextPlan v2 (2026-11-07): the v1 capability `search` mixed the owner's
memory and the web, so a web question (« prix du Bitcoin ») pulled memory records; it is split into `memory` and
`web`, and `browser` (act in a web page or an app as the owner) is added. A v1 plan still reads: `search` becomes
`memory` + `web` (nothing lost).
ContextPlan v3 (2026-11-17, Walter Decision 2.0): `observations` = what was read in the message itself and can be
checked against it (dates written in words, each read as a calendar day by Walter; the people it names), apart from
the judgements (act, level, capabilities…). A v1 or v2 plan still reads (no observations).
ContextPlan v4 (2026-11-18, préflight natif d1.2-ultra): `personal` = what of the owner's own situation the answer
depends on, even when the message only implies it (« une pizza autour de moi » → location; « mon rendez-vous » →
agenda): Context fetches it (the position block for `location`, memory for the rest); `observations` adds the places
and the amounts or quantities the message names; `assessment` = urgency and clarity of the request; `media` = what an
attached image shows (the main model then needs vision). A v1, v2 or v3 plan still reads (none of them).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

VERSION = 1                 # SessionState, ThreadHint, MemoryViewQuery
PLAN_VERSION = 4            # ContextPlan

# Context level: how much the model needs to see beyond the message itself.
LEVELS = {
    "L0": "nothing beyond the message: the assistant's tools suffice",
    "L1": "the last exchange of its thread",
    "L2": "its thread at overview depth (card, recent exchanges)",
    "L3": "its thread at synthesis depth plus targeted memory (people, decisions, other sources)",
    "L4": "its thread at synthesis depth plus deep memory reaching months or years back",
}
# Three independent dimensions (2026-11-27, Monsieur): this context depth (Context), the reasoning tier L1-L3
# (model_profile.level, the Router) and the execution budget L0-L4 (decision.effort, the Engine). None is derived from
# another: deep external research gets an L4 budget without the owner's memory, a simple question that needs a deep
# memory lookup gets that memory without an L4 budget.
# The four plans measured in lot 1 map onto the first four levels.
PLAN_TO_LEVEL = {"none": "L0", "last_exchange": "L1", "thread": "L2", "thread_and_memory": "L3"}
ACTS = ("new", "continue", "approve", "correct", "inform")
DOMAINS = ("projects", "profile", "activities", "relations", "agenda", "decisions", "goals", "walter")
# "walter" (lot 3d, 2026-11-24): the message is about W.Alter itself; its D2 comes as a tool card, no memory read
MEMORY_DOMAINS = tuple(d for d in DOMAINS if d != "walter")   # the domains Walter Memory holds views for
HORIZONS = ("instant", "day", "medium", "long", "stable")
DEPTHS = ("index", "overview", "synthesis", "details", "sources")
CAPABILITIES = ("tools", "skills", "memory", "web", "browser", "delegation", "secrets")
V1_CAPABILITIES = {"search": ("memory", "web")}     # v1 value -> v2 values
MODEL_LEVELS = ("L1", "L2", "L3")          # Walter Router's text tiers (not the context levels above)
FAST_PATHS = ("short_reply", "trivial")
# dates (18/11 evening): a period carries `end` (and `past_end` with its other reading), `approx` when the words give
# no exact bounds; a length of time that names no day carries `duration` (ISO 8601) instead of `date`
OBSERVATIONS = {"dates": ("text", "date", "end", "past", "past_end", "time", "ambiguous", "approx", "duration", "found"),
                "people": ("text", "found"),
                "places": ("text", "found"), "amounts": ("text", "found")}          # places, amounts: v4
# v4: the owner's own situation the answer depends on (fetched by Context: `location` → the position block, the
# others → the owner's memory)
PERSONAL = ("location", "preferences", "history", "people", "projects", "tasks", "agenda")
URGENCY = ("low", "normal", "high")
CLARITY = ("clear", "ambiguous", "missing_info")
IMAGE_KINDS = ("photo", "screenshot", "document", "other")


class ContractError(ValueError):
    pass


def _one_of(name: str, value: Any, allowed) -> None:
    if value not in allowed:
        raise ContractError(f"{name}: {value!r} not in {sorted(allowed)}")


def _subset(name: str, values: Any, allowed) -> None:
    if not isinstance(values, list) or any(v not in allowed for v in values) or len(set(values)) != len(values):
        raise ContractError(f"{name}: {values!r} must be distinct values of {sorted(allowed)}")


def _probability(name: str, value: Any) -> None:
    if value is not None and not (isinstance(value, (int, float)) and 0 <= value <= 1):
        raise ContractError(f"{name}: {value!r} is not a probability")


@dataclass
class ThreadChoice:
    id: str | None                       # a thread id, or None when the message opens a new one
    new: bool = False
    confidence: float | None = None
    alternates: list[str] = field(default_factory=list)   # other threads worth showing when unsure


@dataclass
class ModelProfile:
    """What the preflight asks of Walter Router; the Router alone picks the concrete model."""
    task: str = "general"                # a Router task family (`walter-router tasks`)
    level: str = "L1"                    # a Router text tier
    require: list[str] = field(default_factory=list)       # Router capability words (e.g. vision, long_context)


@dataclass
class ContextPlan:
    turn_id: str
    thread: ThreadChoice
    act: str
    level: str
    domains: list[str] = field(default_factory=list)
    horizons: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    model_profile: ModelProfile = field(default_factory=ModelProfile)
    fast_path: str | None = None         # the plan came from a rule, without a model call
    escalated: bool = False              # a stronger model settled part of it
    decision: dict = field(default_factory=dict)          # model, ms, confidences; degraded + error (A2): trace
    answer: str | None = None            # fast_path trivial only: the exact answer, no model needed (lot 2, 07/11)
    observations: dict = field(default_factory=dict)      # v3: read in the message (dates, people), checkable
    personal: list[str] = field(default_factory=list)     # v4: the owner's situation the answer depends on
    assessment: dict = field(default_factory=dict)        # v4: {urgency, clarity}
    media: dict = field(default_factory=dict)             # v4: {image: kind} of an attached image
    version: int = PLAN_VERSION

    def validate(self) -> "ContextPlan":
        if self.version != PLAN_VERSION:
            raise ContractError(f"ContextPlan version {self.version} != {PLAN_VERSION}")
        if not self.turn_id:
            raise ContractError("turn_id required")
        if self.thread.new == (self.thread.id is not None):
            raise ContractError("thread: either an id or new, not both")
        _probability("thread.confidence", self.thread.confidence)
        _one_of("act", self.act, ACTS)
        _one_of("level", self.level, LEVELS)
        _subset("domains", self.domains, DOMAINS)
        _subset("horizons", self.horizons, HORIZONS)
        _subset("capabilities", self.capabilities, CAPABILITIES)
        _one_of("model_profile.level", self.model_profile.level, MODEL_LEVELS)
        if self.fast_path is not None:
            _one_of("fast_path", self.fast_path, FAST_PATHS)
        if self.answer is not None and self.fast_path != "trivial":
            raise ContractError("answer: only a trivial fast path answers without a model")
        if not isinstance(self.observations, dict) or set(self.observations) - set(OBSERVATIONS):
            raise ContractError(f"observations: keys among {sorted(OBSERVATIONS)}")
        for k, items in self.observations.items():
            if not isinstance(items, list) or not all(isinstance(i, dict) and isinstance(i.get("text"), str)
                                                      and set(i) <= set(OBSERVATIONS[k]) for i in items):
                raise ContractError(f"observations.{k}: items {{{', '.join(OBSERVATIONS[k])}}} with their text")
        _subset("personal", self.personal, PERSONAL)
        if not isinstance(self.assessment, dict) or set(self.assessment) - {"urgency", "clarity"}:
            raise ContractError("assessment: keys among clarity, urgency")
        if "urgency" in self.assessment:
            _one_of("assessment.urgency", self.assessment["urgency"], URGENCY)
        if "clarity" in self.assessment:
            _one_of("assessment.clarity", self.assessment["clarity"], CLARITY)
        if not isinstance(self.media, dict) or set(self.media) - {"image", "audio"}:
            raise ContractError("media: keys among audio, image")
        if "image" in self.media:
            _one_of("media.image", self.media["image"], IMAGE_KINDS)
        if "audio" in self.media and not isinstance(self.media["audio"], bool):
            raise ContractError("media.audio: a boolean (the voice note itself was read)")
        return self

    def to_dict(self) -> dict:
        return asdict(self.validate())

    @classmethod
    def from_dict(cls, d: dict) -> "ContextPlan":
        version, caps = d.get("version", PLAN_VERSION), list(d.get("capabilities") or [])
        if version == 1:                 # a traced v1 plan: same meaning in the v2 vocabulary
            caps = list(dict.fromkeys(c2 for c in caps for c2 in V1_CAPABILITIES.get(c, (c,))))
        if version in (1, 2, 3):         # v1 / v2: no observations; v3: no personal, assessment, media
            version = PLAN_VERSION
        try:
            plan = cls(turn_id=d["turn_id"], thread=ThreadChoice(**d["thread"]), act=d["act"], level=d["level"],
                       domains=list(d.get("domains") or []), horizons=list(d.get("horizons") or []),
                       capabilities=caps,
                       model_profile=ModelProfile(**(d.get("model_profile") or {})),
                       fast_path=d.get("fast_path"), escalated=bool(d.get("escalated")),
                       decision=dict(d.get("decision") or {}), answer=d.get("answer"),
                       observations=dict(d.get("observations") or {}), personal=list(d.get("personal") or []),
                       assessment=dict(d.get("assessment") or {}), media=dict(d.get("media") or {}),
                       version=version)
        except (KeyError, TypeError) as exc:
            raise ContractError(f"malformed ContextPlan: {exc}") from exc
        return plan.validate()


@dataclass
class SessionState:
    """The working state of a thread: what a model must not lose, small and dense. Updated after each turn."""
    thread_id: str
    objective: str = ""                  # the owner's initial intent for this thread; changed only by the owner
    constraints: list[str] = field(default_factory=list)   # owner instructions still in force, verbatim
    decisions: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)          # tool call ids, files, commits: recoverable originals
    open_capabilities: list[str] = field(default_factory=list)  # skills / modules opened in the thread
    plan: str = ""                       # the current step, if a multi-step task is under way
    updated_at: str = ""
    version: int = VERSION

    def validate(self) -> "SessionState":
        if self.version != VERSION or not self.thread_id:
            raise ContractError("SessionState: version 1 and thread_id required")
        for name in ("constraints", "decisions", "refs", "open_capabilities"):
            v = getattr(self, name)
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                raise ContractError(f"SessionState.{name} must be a list of strings")
        return self

    def to_dict(self) -> dict:
        return asdict(self.validate())


@dataclass
class ThreadHint:
    """walter-context → Walter Memory (bus `turn.ended` payload): a hint, Memory decides the attachment."""
    session_id: str
    turn_id: str
    thread_id: str | None
    new: bool
    confidence: float | None = None
    version: int = VERSION

    def validate(self) -> "ThreadHint":
        if self.new == (self.thread_id is not None):
            raise ContractError("ThreadHint: either a thread_id or new")
        _probability("confidence", self.confidence)
        return self

    def to_dict(self) -> dict:
        return asdict(self.validate())


@dataclass
class MemoryViewQuery:
    """walter-context → Walter Memory: the exact depth needed, never the whole view by default."""
    depth: str
    key: str | None = None               # e.g. "project:walter-context"; or a domain with a horizon
    domain: str | None = None
    horizon: str | None = None
    max_tokens: int = 800
    max_age_s: int | None = None         # stricter freshness: Memory rebuilds that depth if older
    privacy: str = "cloud_allowed"       # the strictest class the caller may receive
    version: int = VERSION

    def validate(self) -> "MemoryViewQuery":
        _one_of("depth", self.depth, DEPTHS)
        if not self.key and not self.domain:
            raise ContractError("MemoryViewQuery: a key or a domain")
        if self.domain is not None:
            _one_of("domain", self.domain, MEMORY_DOMAINS)
        if self.horizon is not None:
            _one_of("horizon", self.horizon, HORIZONS)
        _one_of("privacy", self.privacy, ("cloud_allowed", "redacted_cloud", "local_only"))
        if not (isinstance(self.max_tokens, int) and 0 < self.max_tokens <= 64000):
            raise ContractError("max_tokens out of range")
        return self

    def to_dict(self) -> dict:
        return asdict(self.validate())


# --- JSON Schemas (one source: the vocabularies above) -------------------------------------------------------------
def _enum(values) -> dict:
    return {"enum": list(values)}


def _set_of(values) -> dict:
    return {"type": "array", "items": _enum(values), "uniqueItems": True}


_PROB = {"type": ["number", "null"], "minimum": 0, "maximum": 1}
_STRS = {"type": "array", "items": {"type": "string"}}


def schemas() -> dict[str, dict]:
    base = "https://walter.local/contracts/context/"
    return {
        "context-plan.v4.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": base + "context-plan.v4.json",
            "title": "ContextPlan v4", "description": (
                "What the preflight decides for one owner message (walter-context output, traced). v3 (2026-11-17): "
                "observations read in the message, apart from the judgements. v4 (2026-11-18): personal (the owner's "
                "situation the answer depends on, even implied), places and amounts read, assessment (urgency, "
                "clarity), media (what an attached image shows); a v1/v2/v3 plan reads as v4 without them."),
            "type": "object",
            "required": ["version", "turn_id", "thread", "act", "level"],
            "properties": {
                "version": {"const": PLAN_VERSION}, "turn_id": {"type": "string", "minLength": 1},
                "thread": {"type": "object", "required": ["id", "new"], "properties": {
                    "id": {"type": ["string", "null"]}, "new": {"type": "boolean"}, "confidence": _PROB,
                    "alternates": _STRS}},
                "act": _enum(ACTS), "level": {**_enum(LEVELS), "description": "; ".join(f"{k}: {v}" for k, v in LEVELS.items())},
                "domains": _set_of(DOMAINS), "horizons": _set_of(HORIZONS), "capabilities": _set_of(CAPABILITIES),
                "model_profile": {"type": "object", "properties": {
                    "task": {"type": "string"}, "level": _enum(MODEL_LEVELS), "require": _STRS},
                    "description": "Asked of Walter Router; the Router alone picks the concrete model."},
                "fast_path": {"enum": [*FAST_PATHS, None]}, "escalated": {"type": "boolean"},
                "answer": {"type": ["string", "null"], "description": "trivial fast path only: the exact answer"},
                "observations": {"type": "object", "additionalProperties": False, "description": (
                    "read in the message and checkable against it (Walter Decision 2.0 signals context.dates and "
                    "context.people): each date passage as written, the calendar day Walter reads it as (`end` = "
                    "the last day of a period, `past`/`past_end` = the same words read as already gone, `ambiguous` = "
                    "the words leave a choice, `approx` = no exact bounds, `duration` = a length of time that names "
                    "no day), the people named"),
                    "properties": {k: {"type": "array", "items": {
                        "type": "object", "required": ["text"], "additionalProperties": False,
                        "properties": {f: ({"type": "boolean"} if f in ("ambiguous", "approx") else _PROB if f == "found"
                                           else {"type": "string"}) for f in fields}}}
                        for k, fields in OBSERVATIONS.items()}},
                "personal": {**_set_of(PERSONAL), "description": (
                    "the owner's own situation the answer depends on, said or implied: location → Context adds the "
                    "position block (last known position, its age and the known home); the others → owner memory")},
                "assessment": {"type": "object", "additionalProperties": False, "properties": {
                    "urgency": _enum(URGENCY), "clarity": _enum(CLARITY)}},
                "media": {"type": "object", "additionalProperties": False, "properties": {
                    "image": _enum(IMAGE_KINDS), "audio": {"type": "boolean"}},
                    "description": "what an attached image shows (the main model then needs vision); audio = the "
                                   "voice note itself was read by the decision model, beside its transcript"},
                "decision": {"type": "object", "description": (
                    "trace only; degraded = true with error (exception class + short scrubbed reason) when the "
                    "decision failed and the plan is the prudent default (SOCLE A2, 2026-11-11)"),
                    "properties": {"degraded": {"type": "boolean"}, "error": {"type": "string", "maxLength": 120},
                                   "work": {"type": "number", "minimum": 0, "maximum": 1, "description": (
                                       "the decision model's judgement that the message asks for work to carry out and "
                                       "follow (>= 0.5: the Run Plane keeps it as a durable task, SOCLE A3, 2026-11-12)")},
                                   "resume": {"type": "number", "minimum": 0, "maximum": 1, "description": (
                                       "asked only when a thread shows an open or suspended task: the judgement that "
                                       "the message carries on, resumes or finishes it (>= 0.5: the Run Plane attaches "
                                       "the run to the thread's task instead of opening another, 2026-11-13)")},
                                   "effort": {"enum": list(LEVELS), "description": (
                                       "the level whose ceilings the engine gives the turn (SOCLE A7): the context "
                                       "level raised to the difficulty asked (text tier) and to L4 for work to carry "
                                       "out; absent (fast path, degraded plan) = the plan's level, or the general "
                                       "ceilings when degraded")}}}}},
        "session-state.v1.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": base + "session-state.v1.json",
            "title": "SessionState v1", "type": "object", "required": ["version", "thread_id"],
            "properties": {"version": {"const": VERSION}, "thread_id": {"type": "string", "minLength": 1},
                           "objective": {"type": "string"}, "constraints": _STRS, "decisions": _STRS, "refs": _STRS,
                           "open_capabilities": _STRS, "plan": {"type": "string"}, "updated_at": {"type": "string"}}},
        "thread-hint.v1.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": base + "thread-hint.v1.json",
            "title": "ThreadHint v1", "description": "walter-context -> Walter Memory (bus turn.ended); Memory decides.",
            "type": "object", "required": ["version", "session_id", "turn_id", "thread_id", "new"],
            "properties": {"version": {"const": VERSION}, "session_id": {"type": "string"},
                           "turn_id": {"type": "string"}, "thread_id": {"type": ["string", "null"]},
                           "new": {"type": "boolean"}, "confidence": _PROB}},
        "memory-view-query.v1.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": base + "memory-view-query.v1.json",
            "title": "MemoryViewQuery v1",
            "description": "walter-context -> Walter Memory. The answer (owned by Memory) carries key, version, depth, "
                           "content, built_at, watermark, stale, sources[] and deeper[].",
            "type": "object", "required": ["version", "depth"],
            "anyOf": [{"required": ["key"]}, {"required": ["domain"]}],
            "properties": {"version": {"const": VERSION}, "depth": _enum(DEPTHS), "key": {"type": "string"},
                           "domain": _enum(MEMORY_DOMAINS), "horizon": _enum(HORIZONS),
                           "max_tokens": {"type": "integer", "minimum": 1, "maximum": 64000},
                           "max_age_s": {"type": ["integer", "null"], "minimum": 0},
                           "privacy": _enum(("cloud_allowed", "redacted_cloud", "local_only"))}},
    }


if __name__ == "__main__":       # python -m walter_context.plan [--write]: print or (re)write contracts/schemas/
    import json
    import sys
    from pathlib import Path
    out = Path(__file__).resolve().parents[1] / "contracts" / "schemas"
    for name, schema in schemas().items():
        text = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
        if "--write" in sys.argv:
            out.mkdir(parents=True, exist_ok=True)
            (out / name).write_text(text)
        print(name, len(text))
