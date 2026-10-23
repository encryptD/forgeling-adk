"""Deterministic verifier for the generated CAP / Fiori elements project.

Runs real tools against ``cap-app/`` and returns structured results that can be
fed back to the implement agent:

1. static   - JSON / YAML parse, ``node --check`` on JS, FE content rules
2. compile  - ``cds compile * --to edmx`` (parsed into file:line:col messages)
3. build    - ``cds build --for nodejs`` into a temp dir (repo is not touched)
4. smoke    - ``cds serve all`` on a free port, GET $metadata + every entity set

Missing toolchains (no node, no ``cap-app/node_modules``) never raise. The step
is reported as ``skipped`` with a clear reason and ``toolchain_ok`` is False so
callers can stop retrying instead of looping on an environment problem.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent / "cap-app"

PASSED, FAILED, SKIPPED = "passed", "failed", "skipped"

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# [ERROR] srv/gatepass-service.cds:2:42-46: Artifact "x" has not been found (...)
_CDS_MSG = re.compile(
    r"^\[(?P<severity>ERROR|WARNING|INFO|DEBUG)\]\s+"
    r"(?:(?P<file>[^\s:][^:]*?):(?P<line>\d+)(?::(?P<col>\d+)(?:-[\d.:]+)?)?:\s+)?"
    r"(?P<message>.+)$"
)
_SERVING_AT = re.compile(r"at:\s*\[\s*'([^']+)'")
_ENTITY_SET = re.compile(r'<EntitySet\s+Name="([^"]+)"')

NPM_HINT = "run `npm ci` (or `npm install`) in cap-app/ with Node >= 22, then re-verify"


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text or "")


def parse_cds_messages(output: str) -> list[dict[str, Any]]:
    """Parse cds compiler/build output into structured messages."""
    msgs: list[dict[str, Any]] = []
    for raw in strip_ansi(output).splitlines():
        m = _CDS_MSG.match(raw.strip())
        if not m:
            continue
        msgs.append(
            {
                "severity": m.group("severity").lower(),
                "file": m.group("file"),
                "line": int(m.group("line")) if m.group("line") else None,
                "col": int(m.group("col")) if m.group("col") else None,
                "message": m.group("message").strip(),
            }
        )
    return msgs


def format_message(msg: dict[str, Any]) -> str:
    loc = msg.get("file") or ""
    if loc and msg.get("line"):
        loc += f":{msg['line']}"
        if msg.get("col"):
            loc += f":{msg['col']}"
    sev = str(msg.get("severity", "error")).upper()
    return f"{sev} {loc}: {msg['message']}" if loc else f"{sev}: {msg['message']}"


def _step(name: str, status: str, errors=None, warnings=None, reason=None, **extra) -> dict:
    out = {
        "name": name,
        "status": status,
        "errors": list(errors or []),
        "warnings": list(warnings or []),
    }
    if reason:
        out["reason"] = reason
    out.update(extra)
    return out


def _cds_bin(root: Path) -> Path | None:
    cand = root / "node_modules" / ".bin" / "cds"
    return cand if cand.is_file() else None


def _node_bin() -> str | None:
    return shutil.which("node")


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("NO_COLOR", "1")
    env.setdefault("FORCE_COLOR", "0")
    return env


def _run(cmd: list[str], cwd: Path, timeout: int) -> tuple[int, str]:
    proc = subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=_env()
    )
    return proc.returncode, strip_ansi((proc.stdout or "") + (proc.stderr or ""))


def _toolchain_reason(root: Path) -> str | None:
    if not root.is_dir():
        return f"project folder {root} does not exist"
    if not (root / "package.json").is_file():
        return "cap-app/package.json missing (write_cap_package_template first)"
    if not _node_bin():
        return "node is not on PATH; install Node >= 22"
    if not _cds_bin(root):
        return f"cap-app/node_modules/.bin/cds missing; {NPM_HINT}"
    return None


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #


def _project_files(root: Path, *suffixes: str) -> list[Path]:
    files: list[Path] = []
    for sub in ("db", "srv", "app"):
        base = root / sub
        if base.is_dir():
            files += [
                p
                for p in base.rglob("*")
                if p.is_file() and p.suffix in suffixes and "node_modules" not in p.parts
            ]
    return sorted(files)


def check_static(root: Path = ROOT) -> dict:
    """Parse JSON/YAML, syntax-check JS, and apply FE content rules."""
    from .tools import _validate_fe_content  # local import: tools imports ADK

    errors: list[str] = []
    warnings: list[str] = []
    if not root.is_dir():
        return _step("static", FAILED, [f"project folder {root} does not exist"])

    json_files = _project_files(root, ".json")
    if (root / "package.json").is_file():
        json_files.insert(0, root / "package.json")
    for p in json_files:
        try:
            json.loads(p.read_text())
        except Exception as e:  # noqa: BLE001
            errors.append(f"{p.relative_to(root)}: invalid JSON: {e}")

    try:
        import yaml
    except ImportError:  # pragma: no cover - PyYAML ships with google-adk
        yaml = None
    for p in _project_files(root, ".yaml", ".yml"):
        if yaml is None:
            warnings.append(f"{p.relative_to(root)}: PyYAML missing, YAML not parsed")
            continue
        try:
            yaml.safe_load(p.read_text())
        except Exception as e:  # noqa: BLE001
            errors.append(f"{p.relative_to(root)}: invalid YAML: {e}")

    node = _node_bin()
    js_files = _project_files(root, ".js")
    if js_files and not node:
        warnings.append("node not on PATH; JS syntax not checked")
    elif node:
        for p in js_files:
            rc, out = _run([node, "--check", str(p)], root, 30)
            if rc != 0:
                first = next((ln for ln in out.splitlines() if "Error" in ln), out[:200])
                errors.append(f"{p.relative_to(root)}: JS syntax error: {first.strip()}")

    fe_files = _project_files(root, ".cds", ".html", ".json", ".yaml", ".yml")
    if (root / "package.json").is_file():
        fe_files.insert(0, root / "package.json")
    for p in fe_files:
        rel = str(p.relative_to(root)).replace("\\", "/")
        err = _validate_fe_content(rel, p.read_text())
        if err:
            errors.append(f"{rel}: {err}")

    return _step("static", FAILED if errors else PASSED, errors, warnings)


def check_compile(root: Path = ROOT, *, require_ui: bool | None = None) -> dict:
    """cds compile * --to edmx; parse messages; optionally require UI annotations."""
    reason = _toolchain_reason(root)
    if reason:
        return _step("compile", SKIPPED, reason=reason)
    try:
        rc, out = _run([str(_cds_bin(root)), "compile", "*", "--to", "edmx"], root, 180)
    except subprocess.TimeoutExpired:
        return _step("compile", FAILED, ["cds compile timed out after 180s"])
    msgs = parse_cds_messages(out)
    errors = [format_message(m) for m in msgs if m["severity"] == "error"]
    warnings = [format_message(m) for m in msgs if m["severity"] == "warning"]
    if rc != 0 and not errors:
        errors.append(f"cds compile exited {rc}: {out.strip()[-400:]}")
    if rc == 0:
        if require_ui is None:
            require_ui = any((root / "app").glob("**/annotations.cds"))
        if require_ui:
            for needle in ("UI.SelectionFields", "UI.LineItem"):
                if needle not in out:
                    errors.append(
                        f"compiled EDMX missing {needle}: annotations.cds not applied "
                        "to the served entity (empty filter bar / table)"
                    )
    return _step("compile", FAILED if errors else PASSED, errors, warnings)


def check_build(root: Path = ROOT) -> dict:
    """cds build --for nodejs into a throwaway folder."""
    reason = _toolchain_reason(root)
    if reason:
        return _step("build", SKIPPED, reason=reason)
    with tempfile.TemporaryDirectory(prefix="forgeline-build-") as dest:
        try:
            rc, out = _run(
                [str(_cds_bin(root)), "build", "--for", "nodejs", "--dest", dest],
                root,
                300,
            )
        except subprocess.TimeoutExpired:
            return _step("build", FAILED, ["cds build timed out after 300s"])
    msgs = parse_cds_messages(out)
    errors = [format_message(m) for m in msgs if m["severity"] == "error"]
    if rc != 0 and not errors:
        errors.append(f"cds build exited {rc}: {out.strip()[-400:]}")
    return _step("build", FAILED if rc != 0 or errors else PASSED, errors)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http(method: str, url: str, body: dict | None = None, timeout: float = 10) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def parse_service_paths(serve_log: str) -> list[str]:
    return sorted(set(_SERVING_AT.findall(strip_ansi(serve_log))))


def parse_entity_sets(metadata_xml: str) -> list[str]:
    return _ENTITY_SET.findall(metadata_xml or "")


def check_smoke(root: Path = ROOT, *, startup_timeout: float = 45) -> dict:
    """Boot `cds serve all` and probe $metadata, GET and POST {} per entity set.

    POST {} must not 5xx: a 4xx proves mandatory/handler validation is active.
    """
    reason = _toolchain_reason(root)
    if reason:
        return _step("smoke", SKIPPED, reason=reason)
    port = _free_port()
    log_path = Path(tempfile.mkstemp(prefix="forgeline-serve-", suffix=".log")[1])
    errors: list[str] = []
    probes: list[str] = []
    with open(log_path, "w") as log:
        proc = subprocess.Popen(
            [str(_cds_bin(root)), "serve", "all", "--port", str(port)],
            cwd=str(root),
            stdout=log,
            stderr=subprocess.STDOUT,
            env=_env(),
        )
    try:
        deadline = time.time() + startup_timeout
        while time.time() < deadline:
            text = log_path.read_text(errors="replace")
            if "server listening" in text or proc.poll() is not None:
                break
            time.sleep(0.5)
        text = strip_ansi(log_path.read_text(errors="replace"))
        if proc.poll() is not None:
            return _step("smoke", FAILED, [f"cds serve exited early: {text.strip()[-600:]}"])
        if "server listening" not in text:
            return _step("smoke", FAILED, [f"cds serve not listening after {startup_timeout}s"])

        base = f"http://127.0.0.1:{port}"
        paths = parse_service_paths(text)
        if not paths:
            errors.append("cds serve started but served no service")
        for path in paths:
            status, body = _http("GET", f"{base}{path}/$metadata")
            probes.append(f"GET {path}/$metadata -> {status}")
            if status != 200:
                errors.append(f"GET {path}/$metadata returned {status}")
                continue
            for es in parse_entity_sets(body):
                if es.endswith("_texts") or es.startswith("DraftAdministrativeData"):
                    continue
                status, body_g = _http("GET", f"{base}{path}/{es}?$top=1")
                probes.append(f"GET {path}/{es} -> {status}")
                if status != 200:
                    errors.append(f"GET {path}/{es} returned {status}: {body_g[:200]}")
                status, body_p = _http("POST", f"{base}{path}/{es}", {})
                probes.append(f"POST {path}/{es} {{}} -> {status}")
                if status >= 500:
                    errors.append(f"POST {path}/{es} with empty body crashed ({status}): {body_p[:200]}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()
        log_path.unlink(missing_ok=True)
    return _step("smoke", FAILED if errors else PASSED, errors, probes=probes)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def summarize(steps: list[dict], max_lines: int = 40) -> str:
    lines: list[str] = []
    for s in steps:
        head = f"[{s['status'].upper()}] {s['name']}"
        if s.get("reason"):
            head += f" - {s['reason']}"
        lines.append(head)
        lines += [f"  - {e}" for e in s["errors"]]
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"  ... {len(lines) - max_lines} more lines"]
    return "\n".join(lines)


def run_verification(
    root: Path = ROOT,
    *,
    build: bool = True,
    smoke: bool = True,
) -> dict:
    """Run all steps. Later steps are skipped once an earlier one fails."""
    steps = [check_static(root)]
    compile_step = check_compile(root)
    steps.append(compile_step)
    toolchain_ok = compile_step["status"] != SKIPPED

    for name, enabled, fn in (("build", build, check_build), ("smoke", smoke, check_smoke)):
        if not enabled:
            steps.append(_step(name, SKIPPED, reason="disabled"))
        elif not toolchain_ok:
            steps.append(_step(name, SKIPPED, reason=compile_step.get("reason")))
        elif any(s["status"] == FAILED for s in steps):
            steps.append(_step(name, SKIPPED, reason="earlier step failed"))
        else:
            steps.append(fn(root))

    ok = toolchain_ok and all(s["status"] != FAILED for s in steps)
    return {
        "ok": ok,
        "toolchain_ok": toolchain_ok,
        "steps": steps,
        "summary": summarize(steps),
        "hint": None
        if ok
        else (NPM_HINT if not toolchain_ok else "fix the listed errors with write_file, then stop; the verifier re-runs automatically"),
    }
