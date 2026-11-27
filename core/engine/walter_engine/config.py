"""Walter Engine — configuration and paths (2026-11-17).

Everything the engine needs to find is resolved here, never hardcoded elsewhere: the instance (`walter_platform`
instance pointer), the engine's state under `@instance/state/core/engine/native`, the composition values in
`core/config/engine.toml` merged with `@instance/config/core/engine.toml` (`[native]`, and the turn ceilings of
`[dsh.budget]` the native engine reads unchanged), the other modules' doors (ports of walter-llm, Memory's gateway,
Context's preflight, Skills) and the engine's own credentials (local tokens in the instance bootstrap, never a
provider key).
"""
from __future__ import annotations

import logging
import os
import subprocess
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]          # core/engine
CORE_ROOT = ENGINE_ROOT.parent                              # core
RUNTIME = "walter"                                          # runtime name in runs, walter_logs, core.events
KEY_PREFIX = "walter/vm/"                                   # a session's Walter key: walter/vm/<id>
KERNEL_RUNTIME_DIR = ENGINE_ROOT / "plugins" / "python" / "runtime"   # walter_kernel.py (protocol walter-1)

LLM_URL = os.environ.get("WALTER_LLM_URL", "http://127.0.0.1:8894")
MEMORY_URL = os.environ.get("WALTER_MEMORY_URL", "http://127.0.0.1:8890")
PREFLIGHT_URL = os.environ.get("WALTER_PREFLIGHT_URL", "http://127.0.0.1:8897")
SKILLS_URL = os.environ.get("WALTER_SKILLS_URL", "http://127.0.0.1:8891")


def _instance():
    import sys
    if str(CORE_ROOT) not in sys.path:
        sys.path.insert(0, str(CORE_ROOT))
    from walter_platform import instance
    return instance


@lru_cache(maxsize=1)
def instance_root() -> Path:
    return Path(_instance().root())


def module_root(name: str) -> Path | None:
    """Another module's root through its declared interface (`walter path <module>`), for its own CLI/bridge."""
    try:
        out = subprocess.run(["walter", "path", name], capture_output=True, text=True, timeout=20).stdout.strip()
        return Path(out) if out else None
    except (OSError, subprocess.SubprocessError):
        return None


def memory_credential_file() -> Path:
    """Walter Memory's gateway credential file, as its public client names it (never its folder by path)."""
    try:
        from walter_memory import client
        return Path(client.ENV_FILE)
    except Exception:  # noqa: BLE001 — no client: the engine runs without Memory's gateway, `check` says so
        return Path("/dev/null")


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _module_path(value: str) -> str:
    """A path shipped with the engine, relative to core/engine (absolute and @instance/ paths kept as they are)."""
    if not isinstance(value, str) or not value:
        return ""
    if value.startswith("@instance/"):
        return _resolve(value)
    return value if value.startswith("/") else str(ENGINE_ROOT / value)


def _resolve(value: str) -> str:
    return str(instance_root() / value.removeprefix("@instance/")) if isinstance(value, str) and value.startswith("@instance/") else value


@dataclass
class Settings:
    state: Path
    api_host: str = "127.0.0.1"
    api_port: int = 8895
    web_host: str = "127.0.0.1"
    web_port: int = 3080
    trusted_hosts: list = field(default_factory=list)
    workspace: Path = Path("/tmp")
    instructions: str = ""
    model: str = "auto"
    models: list = field(default_factory=lambda: ["auto", "coding", "general", "document", "summarization"])
    max_depth: int = 3
    approval_timeout_s: float = 600.0
    tool_result_chars: int = 8192
    tool_result_head: int = 4096
    tool_result_tail: int = 1024
    context_window: int = 200_000
    system_order: str = "socle_first"             # payload lot 2: "socle_first" | "legacy" (rollback)
    system_blocks: bool = True                    # payload cache layout (24/11): socle block marked for Anthropic
    # lot 3a (2026-11-24): "v1" = one walter-soul profile (`instructions`); "v2" = Soul + the engine's operating rules
    # + the owner's conduct, composed here. `prompt_layout_test` = the layout of test accounts only ("" = the same)
    prompt_layout: str = "v1"
    prompt_layout_test: str = ""
    prompt_layout_accounts: dict = field(default_factory=dict)   # test account id → layout (A/B arms of the bench)
    # lot 3e (2026-11-27): how capabilities reach the model. "hybrid" = direct tools + walter_call + python;
    # "python" = 100 % Unharnessed, the python kernel is the model's only tool (every capability through tools.*)
    exposure: str = "hybrid"
    exposure_accounts: dict = field(default_factory=dict)        # test account id → exposure (A/B arms of the bench)
    # lot 3c: documentation layer of the v2 layout ("mcp" | "s1" | "s2"; a layout "v2+s2" overrides it) and the skills
    # map (a layout suffix "-skills" drops it)
    doc_layer: str = "mcp"
    skills_map: bool = True
    # lot 3b: the recipient's communication profile (core/interfaces/<name>/COMMUNICATION.md); a layout "…+comm" turns
    # it on for one test account
    communication: bool = False
    # owner 2026-11-26: "socle" = the owner's universal consignes in force, read from Memory at each turn start, in the
    # cached socle after the conduct at every level (L0 included); the preflight's pack then leaves them out. "pack" =
    # before: they come in the per-message pack (L1-L4 only).
    owner_rules: str = "pack"
    soul: str = ""
    conduct: str = ""
    operating: str = str(ENGINE_ROOT / "instructions" / "OPERATING.md")
    resume_interrupted: bool = True
    python: str = "full"
    python_idle_s: float = 1800.0
    python_interpreter: str = "/services/python/engine-python/bin/python"
    web_cookie_days: int = 30
    web_name: str = "Walter"
    web_tagline: str = "Que puis-je faire pour vous ?"
    panels: list = field(default_factory=list)
    links: list = field(default_factory=list)
    budget: dict = field(default_factory=dict)
    api_token_file: Path = Path("/dev/null")
    login_url_file: Path = Path("/dev/null")
    llm_env_file: Path = Path("/dev/null")
    memory_env_file: Path = Path("/dev/null")
    api_state: Path = Path("/tmp")
    dsh_home: Path = Path("/opt/dsh/home")           # read only by `import-dsh` (one-shot migration), never at run time
    config_error: str | None = None

    # ── derived ──
    @property
    def sessions_dir(self) -> Path:
        return self.state / "sessions"

    @property
    def python_dir(self) -> Path:
        return self.state / "python"


def load(state: Path | None = None) -> Settings:
    inst = _instance()
    neutral = CORE_ROOT / "config" / "engine.toml"
    doc = tomllib.loads(neutral.read_text()) if neutral.exists() else {}
    config_error = None
    try:
        over = Path(inst.config("core", "engine.toml"))
        if over.exists() and over.resolve() != neutral.resolve():
            doc = _merge(doc, tomllib.loads(over.read_text()))
    except tomllib.TOMLDecodeError as e:  # a broken instance file is said (log + `check`), never silently dropped
        config_error = f"{over}: {e}"
        logging.getLogger("walter_engine").error("instance config unreadable, neutral defaults used: %s", config_error)
    except Exception:  # noqa: BLE001 — no instance config: neutral defaults
        pass
    n = doc.get("native", {})
    web = doc.get("dsh", {}).get("web", {})
    root = instance_root()
    st = Path(state or os.environ.get("WALTER_ENGINE_STATE") or root / "state" / "core" / "engine" / "native")
    s = Settings(
        state=st,
        api_host=n.get("api_host", "127.0.0.1"), api_port=int(n.get("api_port", 8895)),
        web_host=n.get("web_host", "127.0.0.1"), web_port=int(n.get("web_port", 3080)),
        trusted_hosts=list(n.get("trusted_hosts", [])),
        workspace=Path(_resolve(n.get("workspace", "@instance/workspace"))),
        instructions=_resolve(n.get("instructions", "")),
        model=n.get("model", "auto"), models=list(n.get("models", Settings.__dataclass_fields__["models"].default_factory())),
        max_depth=int(n.get("max_depth", 3)),
        approval_timeout_s=float(n.get("approval_timeout_min", 10)) * 60,
        tool_result_chars=int(n.get("tool_result_chars", 8192)), tool_result_head=int(n.get("tool_result_head", 4096)),
        tool_result_tail=int(n.get("tool_result_tail", 1024)), context_window=int(n.get("context_window", 200_000)),
        system_order=str(n.get("system_order", "socle_first")),
        system_blocks=bool(n.get("system_blocks", True)),
        prompt_layout=str(n.get("prompt_layout", "v1")), prompt_layout_test=str(n.get("prompt_layout_test", "")),
        prompt_layout_accounts={str(k): str(v) for k, v in dict(n.get("prompt_layout_accounts", {})).items()},
        exposure=str(n.get("exposure", "hybrid")),
        exposure_accounts={str(k): str(v) for k, v in dict(n.get("exposure_accounts", {})).items()},
        doc_layer=str(n.get("doc_layer", "mcp")), skills_map=bool(n.get("skills_map", True)),
        communication=bool(n.get("communication", False)),
        owner_rules=str(n.get("owner_rules", "pack")),
        soul=_resolve(n.get("soul", "")), conduct=_resolve(n.get("conduct", "")),
        operating=_module_path(n.get("operating", "instructions/OPERATING.md")),
        resume_interrupted=bool(n.get("resume_interrupted", True)), python=n.get("python", "full"),
        python_idle_s=float(n.get("python_idle_min", 30)) * 60,
        python_interpreter=n.get("python_interpreter", "/services/python/engine-python/bin/python"),
        web_cookie_days=int(n.get("web_cookie_days", web.get("cookie_max_age_days", 30))),
        web_name=web.get("name", "Walter"), web_tagline=web.get("tagline", "Que puis-je faire pour vous ?"),
        panels=list(web.get("panels", [])), links=list(web.get("links", [])),
        budget=doc.get("dsh", {}).get("budget", {}),
        api_token_file=root / "bootstrap" / "engine" / "api.token",
        login_url_file=root / "state" / "core" / "engine" / "web" / "login-url",
        llm_env_file=root / "bootstrap" / "engine" / "walter-llm.env",
        memory_env_file=memory_credential_file(),
        api_state=root / "state" / "core" / "engine" / "api",
        config_error=config_error,
    )
    if os.environ.get("WALTER_ENGINE_API_PORT"):
        s.api_port = int(os.environ["WALTER_ENGINE_API_PORT"])
    if os.environ.get("WALTER_ENGINE_WEB_PORT"):
        s.web_port = int(os.environ["WALTER_ENGINE_WEB_PORT"])
    if os.environ.get("WALTER_ENGINE_API_STATE"):
        s.api_state = Path(os.environ["WALTER_ENGINE_API_STATE"])
    if os.environ.get("WALTER_ENGINE_RESUME") in ("0", "false", "no"):
        s.resume_interrupted = False           # a side-by-side run never resumes a conversation on its own
    if os.environ.get("WALTER_ENGINE_LOGIN_URL"):
        s.login_url_file = Path(os.environ["WALTER_ENGINE_LOGIN_URL"])
    return s


def env_value(path: Path, name: str) -> str | None:
    """One VAR=value line of a 0600 env file (local tokens only), never logged."""
    try:
        for line in path.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None
