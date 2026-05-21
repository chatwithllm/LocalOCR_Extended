#!/usr/bin/env python3
"""
orchestrator.py — fully autonomous native-app conversion driver.

Drives: branch -> audit -> plan -> vetoes -> build -> qa-loop (max 6 rounds).
Each stage shells out to `claude` (Claude Code CLI) with a stage-specific prompt.
Status is mirrored into orchestrator_status.json which feeds orchestrator_dashboard.html.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import http.server
import json
import os
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Port discovery (called at module import time)
# ---------------------------------------------------------------------------

def find_free_port(start: int = 9000, attempts: int = 20) -> int:
    """Try ports start..start+attempts-1. Return first free; raise if none."""
    for p in range(start, start + attempts):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
        finally:
            s.close()
    raise RuntimeError(f"No free port found in {start}..{start + attempts - 1}")


DASHBOARD_PORT = find_free_port()
print(f"Dashboard port: {DASHBOARD_PORT} (auto-selected)", flush=True)


# ---------------------------------------------------------------------------
# Globals + constants
# ---------------------------------------------------------------------------

ROOT: Path = Path.cwd()
STATUS_PATH: Path = ROOT / "orchestrator_status.json"
PAUSED_PATH: Path = ROOT / "PAUSED.json"
PROMPTS_DIR: Path = ROOT / "stage_prompts"

MAX_RETRIES = 3
QA_MAX_ROUNDS = 6

_status_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def read_status() -> dict[str, Any]:
    with _status_lock:
        with open(STATUS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)


def write_status(d: dict[str, Any]) -> None:
    with _status_lock:
        tmp = STATUS_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
        os.replace(tmp, STATUS_PATH)


def update_status(patch_fn) -> dict[str, Any]:
    """Read-modify-write atomically. patch_fn receives the dict and mutates it."""
    with _status_lock:
        with open(STATUS_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        patch_fn(d)
        tmp = STATUS_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
        os.replace(tmp, STATUS_PATH)
        return d


def log(msg: str) -> None:
    """Append a one-line log entry visible on the dashboard + stdout."""
    ts = _dt.datetime.now().strftime("%H:%M:%S")
    line = {"ts": ts, "msg": msg}
    print(f"[{ts}] {msg}", flush=True)

    def _add(d: dict[str, Any]) -> None:
        d.setdefault("log", []).append(line)
        if len(d["log"]) > 500:
            d["log"] = d["log"][-500:]

    update_status(_add)


def set_stage(name: str) -> None:
    update_status(lambda d: d.update({"stage": name}))


def set_paused(reason: str) -> None:
    update_status(lambda d: d.update({"paused": True, "pause_reason": reason}))
    PAUSED_PATH.write_text(json.dumps({"reason": reason, "ts": _now()}, indent=2))
    log(f"PAUSED: {reason}")


# ---------------------------------------------------------------------------
# Dashboard HTTP server (background thread)
# ---------------------------------------------------------------------------

class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # silence stdout spam
        return


class _ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def start_dashboard(port: int) -> None:
    os.chdir(ROOT)
    httpd = _ReusableTCPServer(("127.0.0.1", port), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True, name="dashboard")
    t.start()
    log(f"Dashboard serving at http://localhost:{port}/orchestrator_dashboard.html")


# ---------------------------------------------------------------------------
# Claude CLI driver
# ---------------------------------------------------------------------------

def _claude_bin() -> str:
    found = shutil.which("claude")
    if not found:
        raise RuntimeError("`claude` CLI not on PATH — install Claude Code CLI first")
    return found


def run_claude(prompt: str, *, tag: str, timeout_s: int = 60 * 90) -> int:
    """Invoke claude with a prompt via stdin in headless print mode.

    Returns exit code. Streams a heartbeat to the log so the dashboard sees life
    even on long stages.
    """
    cmd = [
        _claude_bin(),
        "--print",
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
    ]
    log(f"[{tag}] launching claude (timeout={timeout_s}s)")
    t0 = time.time()
    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=ROOT, text=True,
            bufsize=1,
        )
    except FileNotFoundError as e:
        log(f"[{tag}] claude launch failed: {e}")
        return 127

    assert proc.stdin and proc.stdout
    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
    except BrokenPipeError:
        pass

    # Reader thread drains stdout independently so the main loop can emit a
    # heartbeat regardless of subprocess output cadence (claude --print can stay
    # silent for many minutes while the model thinks/tool-uses).
    last_emit_holder = {"v": ""}

    def _reader() -> None:
        try:
            for raw in proc.stdout:  # type: ignore[arg-type]
                line = raw.rstrip("\n")
                if line and line != last_emit_holder["v"]:
                    log(f"[{tag}] {line[:240]}")
                    last_emit_holder["v"] = line
        except Exception as e:
            log(f"[{tag}] reader error: {e!r}")

    rt = threading.Thread(target=_reader, name=f"reader-{tag}", daemon=True)
    rt.start()

    last_hb = t0
    while True:
        rc = proc.poll()
        if rc is not None:
            break
        now = time.time()
        if now - last_hb >= 30:
            log(f"[{tag}] ...still working ({int(now - t0)}s)")
            last_hb = now
        if now - t0 > timeout_s:
            log(f"[{tag}] timeout after {timeout_s}s — killing")
            proc.kill()
            rt.join(timeout=2)
            return 124
        time.sleep(2)

    rt.join(timeout=5)
    rc = proc.returncode or 0
    log(f"[{tag}] claude exited rc={rc} in {int(time.time()-t0)}s")
    return rc


def load_prompt(name: str, **subs: str) -> str:
    src = (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")
    for k, v in subs.items():
        src = src.replace("{" + k + "}", v)
    return src


# ---------------------------------------------------------------------------
# Stage 0 — branch
# ---------------------------------------------------------------------------

def run_branch(target: str) -> None:
    set_stage("branch")
    branch_target = f"{target}-build"
    try:
        rc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                            cwd=ROOT, capture_output=True, text=True)
        if rc.returncode != 0:
            log("git not initialized — continuing without branch management")
            update_status(lambda d: d.update({"branch": "(no git)"}))
            return

        cur = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True
        ).strip()

        # accept exact name or a suffix match (e.g. feat/android-build matches android-build)
        if cur == branch_target or cur.endswith("/" + branch_target):
            log(f"already on branch '{cur}' (matches '{branch_target}') — keeping")
            update_status(lambda d: d.update({"branch": cur}))
            return

        # check if target branch already exists
        list_rc = subprocess.run(
            ["git", "rev-parse", "--verify", branch_target],
            cwd=ROOT, capture_output=True, text=True,
        )
        if list_rc.returncode == 0:
            log(f"branch '{branch_target}' exists — checking out")
            subprocess.check_call(["git", "checkout", branch_target], cwd=ROOT)
        else:
            log(f"creating branch '{branch_target}'")
            subprocess.check_call(["git", "checkout", "-b", branch_target], cwd=ROOT)

        update_status(lambda d: d.update({"branch": branch_target}))
    except Exception as e:
        log(f"branch stage warning: {e} (continuing)")
        update_status(lambda d: d.update({"branch": "(skipped)"}))


# ---------------------------------------------------------------------------
# Stage helpers — resume-safe output checks
# ---------------------------------------------------------------------------

def _existing(out_file: str) -> bool:
    return (ROOT / out_file).exists()


def _mark(stage_key: str, status: str, **extra: Any) -> None:
    def _set(d: dict[str, Any]) -> None:
        s = d["stages"][stage_key]
        s["status"] = status
        for k, v in extra.items():
            s[k] = v

    update_status(_set)


def _check_paused() -> None:
    if PAUSED_PATH.exists():
        body = PAUSED_PATH.read_text(encoding="utf-8", errors="replace")[:240]
        set_paused(body)
        log("PAUSED.json detected — halting orchestrator")
        sys.exit(2)


# ---------------------------------------------------------------------------
# Stage 1 — audit
# ---------------------------------------------------------------------------

def run_audit(project: str, target: str, prod_url: str) -> None:
    set_stage("audit")
    if _existing("FEATURE_PARITY_REGISTRY.md"):
        log("audit: FEATURE_PARITY_REGISTRY.md exists — skipping (resume-safe)")
        _mark("audit", "done")
        return
    _mark("audit", "running")
    prompt = load_prompt("audit", PROJECT=project, PROD_URL=prod_url)
    for attempt in range(1, MAX_RETRIES + 1):
        rc = run_claude(prompt, tag=f"audit#{attempt}")
        if rc == 0 and _existing("FEATURE_PARITY_REGISTRY.md"):
            break
        log(f"audit attempt {attempt} failed (rc={rc}); retrying")
    if not _existing("FEATURE_PARITY_REGISTRY.md"):
        _mark("audit", "error")
        set_paused("audit: FEATURE_PARITY_REGISTRY.md not produced after retries")
        sys.exit(2)

    # Pull row + screen counts from the registry
    try:
        text = (ROOT / "FEATURE_PARITY_REGISTRY.md").read_text(encoding="utf-8")
        m = re.search(r"^# audit-complete:\s*rows=(\d+)\s+screens=(\d+)", text, re.M)
        rows = int(m.group(1)) if m else len(re.findall(r"^\| F-\d+", text, re.M))
        screens = int(m.group(2)) if m else len(re.findall(r"^## Screen:", text, re.M))
    except Exception:
        rows = screens = 0
    _mark("audit", "done", rows=rows, screens=screens)
    log(f"audit: done — rows={rows} screens={screens}")
    _check_paused()


# ---------------------------------------------------------------------------
# Stage 2 — plan
# ---------------------------------------------------------------------------

def run_plan(project: str, target: str, prod_url: str, bundle_id: str) -> None:
    set_stage("plan")
    plan_file = "ANDROID_APP_PLAN.md" if target == "android" else f"{target.upper()}_APP_PLAN.md"
    if _existing(plan_file):
        log(f"plan: {plan_file} exists — skipping (resume-safe)")
        _mark("plan", "done")
        return
    _mark("plan", "running")
    prompt = load_prompt("plan", PROJECT=project, PROD_URL=prod_url, BUNDLE_ID=bundle_id)
    for attempt in range(1, MAX_RETRIES + 1):
        rc = run_claude(prompt, tag=f"plan#{attempt}")
        if rc == 0 and _existing(plan_file):
            break
        log(f"plan attempt {attempt} failed (rc={rc}); retrying")
    if not _existing(plan_file):
        _mark("plan", "error")
        set_paused(f"plan: {plan_file} not produced after retries")
        sys.exit(2)

    try:
        t = (ROOT / plan_file).read_text(encoding="utf-8")
        m = re.search(r"^# plan-complete:\s*agents=(\d+)\s+vetoes=(\d+)\s+confidence=(\d+)", t, re.M)
        agents, vetoes, conf = (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (7, 0, 0)
    except Exception:
        agents, vetoes, conf = 7, 0, 0
    _mark("plan", "done", agents=agents, vetoes=vetoes, confidence=conf)
    log(f"plan: done — agents={agents} vetoes={vetoes} confidence={conf}")
    _check_paused()


# ---------------------------------------------------------------------------
# Stage 3 — vetoes
# ---------------------------------------------------------------------------

def run_vetoes(project: str) -> None:
    set_stage("vetoes")
    if _existing("VETO_RESOLUTION_PATCH.md"):
        log("vetoes: VETO_RESOLUTION_PATCH.md exists — skipping")
        _mark("vetoes", "done")
        return

    plan_status = read_status()["stages"]["plan"]
    vetoes_n = int(plan_status.get("vetoes") or 0)
    if vetoes_n == 0:
        (ROOT / "VETO_RESOLUTION_PATCH.md").write_text(
            "# VETO_RESOLUTION_PATCH\n\n## Summary\n- total: 0\n- resolved: 0\n- unresolved: 0\n\n"
            "# vetoes-complete: total=0 resolved=0 blocked=0\n",
            encoding="utf-8",
        )
        _mark("vetoes", "done", resolved=0, total=0)
        log("vetoes: none raised — wrote stub")
        return

    _mark("vetoes", "running", total=vetoes_n, resolved=0)
    prompt = load_prompt("vetoes", PROJECT=project)
    for attempt in range(1, MAX_RETRIES + 1):
        rc = run_claude(prompt, tag=f"vetoes#{attempt}")
        if rc == 0 and _existing("VETO_RESOLUTION_PATCH.md"):
            break
        log(f"vetoes attempt {attempt} failed (rc={rc}); retrying")
    if not _existing("VETO_RESOLUTION_PATCH.md"):
        _mark("vetoes", "error")
        set_paused("vetoes: VETO_RESOLUTION_PATCH.md not produced after retries")
        sys.exit(2)

    text = (ROOT / "VETO_RESOLUTION_PATCH.md").read_text(encoding="utf-8")
    resolved = len(re.findall(r"Status:\s*RESOLVED", text))
    blocked = len(re.findall(r"Status:\s*BLOCKED", text))
    if blocked > 0:
        _mark("vetoes", "error", resolved=resolved, total=vetoes_n, blocked=blocked)
        set_paused(f"vetoes: {blocked} BLOCKED veto(s); requires user input")
        sys.exit(2)
    _mark("vetoes", "done", resolved=resolved, total=vetoes_n)
    log(f"vetoes: done — resolved={resolved}/{vetoes_n}")
    _check_paused()


# ---------------------------------------------------------------------------
# Stage 4 — build
# ---------------------------------------------------------------------------

def _ingest_build_status() -> None:
    """Mirror build_status.json into orchestrator_status.json (if present)."""
    bsp = ROOT / "build_status.json"
    if not bsp.exists():
        return
    try:
        bs = json.loads(bsp.read_text(encoding="utf-8"))
    except Exception:
        return

    def _set(d: dict[str, Any]) -> None:
        b = d["stages"]["build"]
        for k in ("phases_done", "phases_total", "current_screen", "screens_done", "gates"):
            if k in bs:
                b[k] = bs[k]

    update_status(_set)


def _watch_build_status(stop_evt: threading.Event) -> None:
    while not stop_evt.is_set():
        _ingest_build_status()
        stop_evt.wait(2.0)


def run_build(project: str, target: str, prod_url: str, bundle_id: str) -> None:
    set_stage("build")
    if (ROOT / "BUILD_COMPLETE").exists():
        log("build: BUILD_COMPLETE marker exists — skipping")
        _mark("build", "done")
        return

    _mark("build", "running")
    prompt = load_prompt("build", PROJECT=project, PROD_URL=prod_url, BUNDLE_ID=bundle_id)

    stop = threading.Event()
    watcher = threading.Thread(target=_watch_build_status, args=(stop,), daemon=True)
    watcher.start()

    rc_final = 1
    try:
        for attempt in range(1, MAX_RETRIES + 1):
            rc = run_claude(prompt, tag=f"build#{attempt}", timeout_s=60 * 180)
            _ingest_build_status()
            if rc == 0 and (ROOT / "BUILD_COMPLETE").exists():
                rc_final = 0
                break
            log(f"build attempt {attempt} did not finish (rc={rc}); retrying")
            _check_paused()
    finally:
        stop.set()
        watcher.join(timeout=3)

    _ingest_build_status()
    if rc_final != 0 or not (ROOT / "BUILD_COMPLETE").exists():
        _mark("build", "error")
        set_paused("build: BUILD_COMPLETE marker not produced after retries")
        sys.exit(2)
    _mark("build", "done")
    log("build: done — BUILD_COMPLETE present")
    _check_paused()


# ---------------------------------------------------------------------------
# Stage 5 — QA loop
# ---------------------------------------------------------------------------

def _qa_round_patch(round_num: int, patch: dict[str, Any]) -> None:
    """Merge a patch into the rounds_detail entry for round_num (create if missing)."""
    def _apply(d: dict[str, Any]) -> None:
        rd = d["stages"]["qa"].setdefault("rounds_detail", [])
        for entry in rd:
            if entry.get("round") == round_num:
                entry.update(patch)
                return
        rd.append({"round": round_num, **patch})

    update_status(_apply)


def _qa_set(field: str, value: Any) -> None:
    update_status(lambda d: d["stages"]["qa"].update({field: value}))


def run_initial_audit_for_qa(project: str, prod_url: str) -> None:
    """Cold-start audit (A+B parallel, then C) when entering the QA loop."""
    log("qa: initial audits (A+B parallel, then C)")
    _qa_set("current_agent", "A+B (init)")
    a_prompt = load_prompt("qa_a", PROJECT=project, ROUND="1", ROUND_MINUS_1="0")
    b_prompt = load_prompt("qa_b", PROJECT=project, PROD_URL=prod_url, ROUND="1", ROUND_MINUS_1="0")

    results: dict[str, int] = {}
    t_a = threading.Thread(target=lambda: results.setdefault("a", run_claude(a_prompt, tag="qa-a#init")))
    t_b = threading.Thread(target=lambda: results.setdefault("b", run_claude(b_prompt, tag="qa-b#init")))
    t_a.start(); t_b.start()
    t_a.join();  t_b.join()

    _qa_set("current_agent", "C (init)")
    c_prompt = load_prompt("qa_c", PROJECT=project, ROUND="1", ROUND_MINUS_1="0")
    run_claude(c_prompt, tag="qa-c#init")
    _qa_set("current_agent", "")


def run_qa_loop(project: str, prod_url: str) -> str:
    set_stage("qa")
    _mark("qa", "running", round=0, total_rounds=0, current_agent="",
          rounds_detail=[], verdict="")

    for round_num in range(1, QA_MAX_ROUNDS + 1):
        _check_paused()
        _qa_set("total_rounds", round_num)
        _qa_set("round", round_num)
        log(f"=== QA Round {round_num}/{QA_MAX_ROUNDS} ===")

        _qa_round_patch(round_num, {
            "started": _dt.datetime.now().strftime("%H:%M:%S"),
            "fix": "running" if round_num > 1 else "pending",
            "a": "pending", "b": "pending", "c": "pending",
            "verdict": "",
        })

        # 1. Fix stage (round 1 has no prior fixes file -> skip fix subprocess)
        if round_num > 1:
            _qa_set("current_agent", f"Fix (round {round_num})")
            fix_prompt = load_prompt("qa_fix", PROJECT=project, ROUND=str(round_num))
            run_claude(fix_prompt, tag=f"qa-fix#{round_num}")
            _qa_round_patch(round_num, {"fix": "done"})
        else:
            _qa_round_patch(round_num, {"fix": "done"})

        # 2. Audit A + Audit B in parallel
        _qa_round_patch(round_num, {"a": "running", "b": "running"})
        _qa_set("current_agent", f"A+B (round {round_num})")

        a_prompt = load_prompt(
            "qa_a", PROJECT=project, ROUND=str(round_num),
            ROUND_MINUS_1=str(round_num - 1),
        )
        b_prompt = load_prompt(
            "qa_b", PROJECT=project, PROD_URL=prod_url, ROUND=str(round_num),
            ROUND_MINUS_1=str(round_num - 1),
        )

        results: dict[str, int] = {}

        def _run_a() -> None:
            results["a"] = run_claude(a_prompt, tag=f"qa-a#{round_num}")
            _qa_round_patch(round_num, {"a": "done"})

        def _run_b() -> None:
            results["b"] = run_claude(b_prompt, tag=f"qa-b#{round_num}")
            _qa_round_patch(round_num, {"b": "done"})

        t_a = threading.Thread(target=_run_a, name=f"qa-a-{round_num}")
        t_b = threading.Thread(target=_run_b, name=f"qa-b-{round_num}")
        t_a.start(); t_b.start()
        t_a.join();  t_b.join()

        # 3. Agent C — synthesizer
        _qa_set("current_agent", f"C (round {round_num})")
        _qa_round_patch(round_num, {"c": "running"})
        c_prompt = load_prompt(
            "qa_c", PROJECT=project, ROUND=str(round_num),
            ROUND_MINUS_1=str(round_num - 1),
        )
        run_claude(c_prompt, tag=f"qa-c#{round_num}")
        _qa_round_patch(round_num, {"c": "done"})

        # 4. Inspect outputs
        ship = (ROOT / "SHIP_READY.md").exists()
        next_fix = (ROOT / f"FINAL_FIXES_R{round_num + 1}.md").exists()

        if ship:
            _qa_round_patch(round_num, {"verdict": "SHIP_READY"})
            _qa_set("current_agent", "")
            _qa_set("verdict", "SHIP_READY")
            _mark("qa", "done", verdict="SHIP_READY")
            update_status(lambda d: d.update({"verdict": "SHIP_READY", "completed": _now()}))
            log(f"QA Round {round_num}: SHIP_READY")
            return "SHIP_READY"

        if not next_fix:
            log(f"qa round {round_num}: neither SHIP_READY nor FINAL_FIXES_R{round_num + 1}.md present")
            log("treating as SHIP_READY-equivalent (no further fixes proposed)")
            _qa_round_patch(round_num, {"verdict": "SHIP_READY"})
            _qa_set("current_agent", "")
            _qa_set("verdict", "SHIP_READY")
            _mark("qa", "done", verdict="SHIP_READY")
            update_status(lambda d: d.update({"verdict": "SHIP_READY", "completed": _now()}))
            return "SHIP_READY"

        _qa_round_patch(round_num, {"verdict": "needs_fixes"})
        log(f"qa round {round_num}: needs_fixes -> continuing to round {round_num + 1}")

    _qa_set("current_agent", "")
    _qa_set("verdict", "needs_fixes")
    _mark("qa", "error", verdict="needs_fixes")
    update_status(lambda d: d.update({"verdict": "needs_fixes", "completed": _now()}))
    log("QA loop exhausted max rounds without SHIP_READY")
    set_paused(f"qa: hit max rounds ({QA_MAX_ROUNDS}) without SHIP_READY")
    return "needs_fixes"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def _default_bundle_id(project_path: str) -> str:
    name = Path(project_path).name.lower()
    name = re.sub(r"[ _\-]", ".", name)
    name = re.sub(r"[^a-z0-9.]", "", name)
    return f"com.{name}.{name}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--target", required=True,
                    choices=["android", "ios", "macos", "windows"])
    ap.add_argument("--prod-url", default="https://extended.npalakurla.com")
    ap.add_argument("--bundle-id", default=None)
    ap.add_argument("--mode", default="full", choices=["full", "delta"])
    ap.add_argument("--changed-files", default=None)
    args = ap.parse_args()

    project = args.project
    target = args.target
    prod_url = args.prod_url
    bundle_id = args.bundle_id or _default_bundle_id(project)

    update_status(lambda d: d.update({
        "project": project,
        "target": target,
        "started": _now(),
        "dashboard_port": DASHBOARD_PORT,
        "paused": False,
        "pause_reason": "",
        "completed": "",
        "verdict": "",
    }))

    log(f"orchestrator started — project={project} target={target} prod={prod_url}")
    log(f"bundle id: {bundle_id}")
    log(f"max retries: {MAX_RETRIES}; qa max rounds: {QA_MAX_ROUNDS}")

    start_dashboard(DASHBOARD_PORT)

    try:
        run_branch(target)
        _check_paused()

        run_audit(project, target, prod_url)
        _check_paused()

        run_plan(project, target, prod_url, bundle_id)
        _check_paused()

        run_vetoes(project)
        _check_paused()

        run_build(project, target, prod_url, bundle_id)
        _check_paused()

        verdict = run_qa_loop(project, prod_url)
        if verdict == "SHIP_READY":
            log("Orchestrator finished: SHIP_READY")
            return 0
        log("Orchestrator finished without SHIP_READY")
        return 1
    except KeyboardInterrupt:
        log("interrupted by user")
        return 130
    except SystemExit:
        raise
    except Exception as e:
        log(f"orchestrator fatal: {e!r}")
        set_paused(f"fatal: {e!r}")
        return 1
    finally:
        log(f"orchestrator process exit — dashboard at port {DASHBOARD_PORT}")


if __name__ == "__main__":
    sys.exit(main())
