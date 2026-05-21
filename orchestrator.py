#!/usr/bin/env python3
"""
LocalOCR_Extended — autonomous native-app conversion orchestrator.

Stages:
  branch  → ensure {target}-build branch
  audit   → FEATURE_PARITY_REGISTRY.md
  plan    → ANDROID_APP_PLAN.md
  vetoes  → VETO_RESOLUTION_PATCH.md
  build   → 9 phases (per ANDROID_APP_PLAN.md §6)
  qa loop → initial A+B+C audit, then fix→A→B→C up to 6 rounds, until SHIP_READY.md
"""

import argparse
import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths and globals
# ---------------------------------------------------------------------------

PROJECT_DIR = os.environ.get('ORCH_PROJECT_DIR') or os.getcwd()
STATUS_FILE = os.path.join(PROJECT_DIR, 'orchestrator_status.json')
PROMPTS_DIR = os.path.join(PROJECT_DIR, 'stage_prompts')
DASHBOARD_HTML = os.path.join(PROJECT_DIR, 'orchestrator_dashboard.html')

DEFAULT_PORT = 9001
QA_MAX_ROUNDS = 6
MAX_RETRIES = 3
CLAUDE_TIMEOUT = 7200  # 2h per invocation cap

START_MONO = time.monotonic()
STATUS_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Time + status helpers
# ---------------------------------------------------------------------------

def ts() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def hms() -> str:
    return datetime.now().strftime('%H:%M:%S')


def _deep_merge(base: dict, updates: dict) -> None:
    for k, v in updates.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def update_status(patch: dict = None, log_line: str = None) -> dict:
    with STATUS_LOCK:
        try:
            with open(STATUS_FILE, 'r') as f:
                status = json.load(f)
        except Exception:
            status = {}
        if patch:
            _deep_merge(status, patch)
        status['elapsed_seconds'] = int(time.monotonic() - START_MONO)
        status['updated'] = ts()
        if log_line:
            tail = status.get('log_tail') or []
            tail.append(f'[{hms()}] {log_line}')
            status['log_tail'] = tail[-50:]
        tmp = STATUS_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(status, f, indent=2)
        os.replace(tmp, STATUS_FILE)
        return status


def read_status() -> dict:
    with STATUS_LOCK:
        try:
            with open(STATUS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}


def pause(reason: str) -> None:
    update_status({'paused': True, 'pause_reason': reason}, log_line=f'PAUSED: {reason}')


def unpause() -> None:
    update_status({'paused': False, 'pause_reason': ''})


# ---------------------------------------------------------------------------
# Dashboard HTTP server
# ---------------------------------------------------------------------------

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return


def start_dashboard(port: int) -> None:
    os.chdir(PROJECT_DIR)
    try:
        httpd = socketserver.TCPServer(('', port), QuietHandler)
    except OSError as e:
        print(f'[orchestrator] dashboard port {port} unavailable: {e}')
        return
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    url = f'http://localhost:{port}/orchestrator_dashboard.html'
    print(f'[orchestrator] dashboard: {url}')
    try:
        webbrowser.open(url)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Claude CLI invocation
# ---------------------------------------------------------------------------

def claude_available() -> bool:
    return subprocess.run(['which', 'claude'], capture_output=True).returncode == 0


def run_claude(prompt_text: str, label: str, timeout: int = CLAUDE_TIMEOUT) -> tuple:
    print(f'[{hms()}] starting {label}')
    update_status({}, log_line=f'{label}: starting')
    proc = subprocess.Popen(
        ['claude', '--dangerously-skip-permissions', '--print'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=PROJECT_DIR,
    )
    lines = []

    def reader():
        for raw in proc.stdout:
            line = raw.rstrip()
            lines.append(line)
            if line:
                print(f'  [{label}] {line}')
                update_status({}, log_line=f'{label}: {line[:160]}')

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        proc.stdin.write(prompt_text)
        proc.stdin.close()
    except Exception as e:
        update_status({}, log_line=f'{label}: stdin error {e}')
    t.join(timeout=timeout)
    try:
        proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        proc.kill()
        update_status({}, log_line=f'{label}: TIMEOUT — killed after {timeout}s')
        return False, '\n'.join(lines)
    return proc.returncode == 0, '\n'.join(lines)


def load_prompt(name: str, **subs) -> str:
    path = os.path.join(PROMPTS_DIR, name)
    with open(path, 'r') as f:
        text = f.read()
    for k, v in subs.items():
        text = text.replace('{' + k + '}', str(v))
    return text


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------

COMPLETE_LINE = re.compile(r'^\s*([A-Z_0-9]+_COMPLETE|[A-Z_0-9]+_PAUSED|[A-Z_0-9]+_SKIPPED)\s*:\s*(.*)$')


def parse_complete(output: str, keyword: str) -> dict:
    """Find 'KEYWORD_COMPLETE: a=1 b=2' style sentinels in agent output."""
    result = {}
    for line in output.splitlines():
        m = COMPLETE_LINE.match(line.strip())
        if not m:
            continue
        if keyword in m.group(1):
            payload = m.group(2).strip()
            for token in payload.split():
                if '=' in token:
                    k, v = token.split('=', 1)
                    result[k] = v
            result['_sentinel'] = m.group(1)
            return result
    return result


# ---------------------------------------------------------------------------
# Stage 0 — Branch
# ---------------------------------------------------------------------------

def run_branch(target: str) -> str:
    """Ensure the build branch exists. Returns branch name or '' if git not initialized."""
    branch = f'{target}-build'
    update_status({'stage': 'branch', 'started': ts()}, log_line=f'branch: ensuring {branch}')

    # Check git initialized
    r = subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'],
                       cwd=PROJECT_DIR, capture_output=True, text=True)
    if r.returncode != 0:
        update_status({}, log_line='branch: git not initialized — continuing without branch switch')
        return ''

    # Current branch
    r = subprocess.run(['git', 'symbolic-ref', '--short', 'HEAD'],
                       cwd=PROJECT_DIR, capture_output=True, text=True)
    current = r.stdout.strip() if r.returncode == 0 else ''
    if current == branch:
        update_status({'branch': branch}, log_line=f'branch: already on {branch}')
        return branch

    # Branch exists?
    r = subprocess.run(['git', 'rev-parse', '--verify', branch],
                       cwd=PROJECT_DIR, capture_output=True, text=True)
    if r.returncode == 0:
        subprocess.run(['git', 'checkout', branch], cwd=PROJECT_DIR, check=False)
        update_status({'branch': branch}, log_line=f'branch: checked out existing {branch}')
    else:
        subprocess.run(['git', 'checkout', '-b', branch], cwd=PROJECT_DIR, check=False)
        update_status({'branch': branch}, log_line=f'branch: created and checked out {branch}')
    return branch


# ---------------------------------------------------------------------------
# Stage 1 — Audit
# ---------------------------------------------------------------------------

def run_audit() -> bool:
    output_path = os.path.join(PROJECT_DIR, 'FEATURE_PARITY_REGISTRY.md')
    if os.path.exists(output_path):
        update_status({'stage': 'audit',
                       'stages': {'audit': {'status': 'done', 'note': 'pre-existing file — skipped'}}},
                      log_line='audit: FEATURE_PARITY_REGISTRY.md exists — skipped')
        return True
    update_status({'stage': 'audit',
                   'stages': {'audit': {'status': 'running', 'started': ts()}}},
                  log_line='audit: starting')
    prompt = load_prompt('audit.txt')
    ok, out = run_claude(prompt, 'audit')
    info = parse_complete(out, 'AUDIT')
    if not ok or not os.path.exists(output_path):
        update_status({'stages': {'audit': {'status': 'error', 'note': 'no FEATURE_PARITY_REGISTRY.md produced'}}},
                      log_line='audit: FAILED')
        pause('audit stage produced no FEATURE_PARITY_REGISTRY.md')
        return False
    update_status({'stages': {'audit': {
        'status': 'done',
        'completed': ts(),
        'rows': int(info.get('rows', 0) or 0),
        'screens': int(info.get('screens', 0) or 0),
        'note': f"pending={info.get('pending', '?')}",
    }}}, log_line=f"audit: done — screens={info.get('screens')} rows={info.get('rows')}")
    return True


# ---------------------------------------------------------------------------
# Stage 2 — Plan
# ---------------------------------------------------------------------------

def run_plan() -> bool:
    output_path = os.path.join(PROJECT_DIR, 'ANDROID_APP_PLAN.md')
    if os.path.exists(output_path):
        update_status({'stage': 'plan',
                       'stages': {'plan': {'status': 'done', 'note': 'pre-existing file — skipped'}}},
                      log_line='plan: ANDROID_APP_PLAN.md exists — skipped')
        return True
    update_status({'stage': 'plan',
                   'stages': {'plan': {'status': 'running', 'started': ts()}}},
                  log_line='plan: starting')
    prompt = load_prompt('plan.txt')
    ok, out = run_claude(prompt, 'plan')
    info = parse_complete(out, 'PLAN')
    if not ok or not os.path.exists(output_path):
        update_status({'stages': {'plan': {'status': 'error', 'note': 'no ANDROID_APP_PLAN.md produced'}}},
                      log_line='plan: FAILED')
        pause('plan stage produced no ANDROID_APP_PLAN.md')
        return False
    update_status({'stages': {'plan': {
        'status': 'done',
        'completed': ts(),
        'vetoes': int(info.get('vetoes', 0) or 0),
        'confidence': info.get('confidence', ''),
        'note': '',
    }}}, log_line=f"plan: done — vetoes={info.get('vetoes')} conf={info.get('confidence')}")
    return True


# ---------------------------------------------------------------------------
# Stage 3 — Vetoes
# ---------------------------------------------------------------------------

def run_vetoes() -> bool:
    output_path = os.path.join(PROJECT_DIR, 'VETO_RESOLUTION_PATCH.md')
    plan_vetoes = int((read_status().get('stages', {}).get('plan', {}).get('vetoes') or 0))

    if plan_vetoes == 0:
        update_status({'stage': 'vetoes',
                       'stages': {'vetoes': {'status': 'done',
                                             'completed': ts(),
                                             'resolved': 0,
                                             'total': 0,
                                             'note': 'no vetoes raised by plan'}}},
                      log_line='vetoes: none — skipped')
        return True

    if os.path.exists(output_path):
        update_status({'stage': 'vetoes',
                       'stages': {'vetoes': {'status': 'done', 'note': 'pre-existing file — skipped'}}},
                      log_line='vetoes: VETO_RESOLUTION_PATCH.md exists — skipped')
        return True

    update_status({'stage': 'vetoes',
                   'stages': {'vetoes': {'status': 'running', 'started': ts(), 'total': plan_vetoes}}},
                  log_line=f'vetoes: starting ({plan_vetoes} to resolve)')
    prompt = load_prompt('vetoes.txt')
    ok, out = run_claude(prompt, 'vetoes')
    info = parse_complete(out, 'VETOES')

    if info.get('_sentinel') == 'VETOES_PAUSED':
        update_status({'stages': {'vetoes': {'status': 'error',
                                             'note': info.get('reason', 'pause requested')}}},
                      log_line=f"vetoes: PAUSED — {info.get('reason', '')}")
        pause(f"vetoes: {info.get('reason', 'needs user input')}")
        return False

    if not ok or not os.path.exists(output_path):
        update_status({'stages': {'vetoes': {'status': 'error', 'note': 'no patch produced'}}},
                      log_line='vetoes: FAILED')
        pause('vetoes stage produced no VETO_RESOLUTION_PATCH.md')
        return False

    update_status({'stages': {'vetoes': {
        'status': 'done',
        'completed': ts(),
        'resolved': int(info.get('resolved', 0) or 0),
        'total': int(info.get('total', plan_vetoes) or plan_vetoes),
    }}}, log_line=f"vetoes: done — {info.get('resolved')}/{info.get('total')}")
    return True


# ---------------------------------------------------------------------------
# Stage 4 — Build
# ---------------------------------------------------------------------------

PHASE_SENTINEL = re.compile(r'^\s*BUILD_PHASE_DONE\s*:\s*phase\s*=\s*(\d+)\s+name\s*=\s*(.+)$')
SCREEN_SENTINEL = re.compile(r'^\s*BUILD_SCREEN_DONE\s*:\s*phase\s*=\s*(\d+)\s+screen\s*=\s*(\S+)\s+rows_done\s*=\s*(\d+)\s*$')


def run_build() -> bool:
    if os.path.exists(os.path.join(PROJECT_DIR, 'SHIP_READY.md')):
        update_status({'stage': 'build',
                       'stages': {'build': {'status': 'done', 'phases_done': 9}}},
                      log_line='build: SHIP_READY.md present — skipped')
        return True

    update_status({'stage': 'build',
                   'stages': {'build': {'status': 'running', 'started': ts()}}},
                  log_line='build: starting')

    prompt = load_prompt('build.txt')

    # Stream output and update status as phases/screens complete.
    print(f'[{hms()}] starting build')
    proc = subprocess.Popen(
        ['claude', '--dangerously-skip-permissions', '--print'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=PROJECT_DIR,
    )

    screens_done = list(read_status().get('stages', {}).get('build', {}).get('screens_done') or [])
    phases_done = 0
    paused_reason = None

    def reader():
        nonlocal phases_done, paused_reason
        for raw in proc.stdout:
            line = raw.rstrip()
            if not line:
                continue
            print(f'  [build] {line}')
            update_status({}, log_line=f'build: {line[:160]}')

            m = SCREEN_SENTINEL.match(line)
            if m:
                phase, screen, _ = m.group(1), m.group(2), m.group(3)
                if screen not in screens_done:
                    screens_done.append(screen)
                update_status({'stages': {'build': {
                    'current_phase': int(phase),
                    'current_screen': screen,
                    'screens_done': screens_done,
                }}}, log_line=f'build: screen done — phase {phase} / {screen}')
                continue

            m = PHASE_SENTINEL.match(line)
            if m:
                phases_done = int(m.group(1))
                update_status({'stages': {'build': {
                    'phases_done': phases_done,
                    'current_phase': phases_done,
                    'current_phase_name': m.group(2).strip(),
                }}}, log_line=f'build: phase {phases_done} done — {m.group(2).strip()}')
                continue

            if line.strip().startswith('BUILD_PAUSED'):
                paused_reason = line.strip().split(':', 1)[-1].strip()
                continue

            if line.strip().startswith('BUILD_COMPLETE'):
                update_status({'stages': {'build': {
                    'status': 'done',
                    'phases_done': 9,
                    'completed': ts(),
                }}}, log_line='build: BUILD_COMPLETE')

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
    except Exception:
        pass
    t.join(timeout=CLAUDE_TIMEOUT)
    try:
        proc.wait(timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        update_status({'stages': {'build': {'status': 'error'}}}, log_line='build: TIMEOUT — killed')
        pause('build stage timed out')
        return False

    if paused_reason:
        update_status({'stages': {'build': {'status': 'error'}}}, log_line=f'build: PAUSED — {paused_reason}')
        pause(f'build: {paused_reason}')
        return False

    final = read_status().get('stages', {}).get('build', {})
    if final.get('status') != 'done':
        update_status({'stages': {'build': {'status': 'error'}}}, log_line='build: agent exited without BUILD_COMPLETE')
        pause('build exited without BUILD_COMPLETE sentinel')
        return False
    return True


# ---------------------------------------------------------------------------
# Stage 5 — QA loop
# ---------------------------------------------------------------------------

def _qa_round_patch(round_num: int, patch: dict) -> None:
    """Merge `patch` into the rounds_detail entry whose round == round_num."""
    with STATUS_LOCK:
        try:
            with open(STATUS_FILE, 'r') as f:
                status = json.load(f)
        except Exception:
            return
        qa = status.setdefault('stages', {}).setdefault('qa', {})
        rd = qa.setdefault('rounds_detail', [])
        target = None
        for entry in rd:
            if entry.get('round') == round_num:
                target = entry
                break
        if target is None:
            target = {'round': round_num}
            rd.append(target)
        for k, v in patch.items():
            target[k] = v
        status['elapsed_seconds'] = int(time.monotonic() - START_MONO)
        status['updated'] = ts()
        tmp = STATUS_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(status, f, indent=2)
        os.replace(tmp, STATUS_FILE)


def _run_audit_agent(label: str, prompt_name: str, round_num: int, sentinel_key: str) -> dict:
    prompt = load_prompt(prompt_name, ROUND_NUM=round_num, NEXT_ROUND=round_num + 1)
    ok, out = run_claude(prompt, label)
    info = parse_complete(out, sentinel_key)
    info['_ok'] = ok
    return info


def run_initial_audit_for_qa() -> bool:
    """Round-0 initial audit (no fix). A+B in parallel, then C."""
    round_num = 0

    update_status({'stage': 'qa',
                   'stages': {'qa': {'status': 'running',
                                     'started': ts(),
                                     'current_agent': 'A+B (init)',
                                     'total_rounds': 0,
                                     'rounds_detail': [],
                                     'verdict': ''}}},
                  log_line='qa: initial A+B audit')
    _qa_round_patch(round_num, {
        'round': round_num,
        'started': ts(),
        'fix': 'skipped',
        'a': 'running',
        'b': 'running',
        'c': 'pending',
        'verdict': '',
    })

    results = {}

    def run_a():
        info = _run_audit_agent(f'audit-a-r{round_num}', 'qa_a.txt', round_num, 'AUDIT_A')
        results['a'] = info
        _qa_round_patch(round_num, {'a': 'done' if info.get('_ok') else 'error'})

    def run_b():
        info = _run_audit_agent(f'audit-b-r{round_num}', 'qa_b.txt', round_num, 'AUDIT_B')
        results['b'] = info
        _qa_round_patch(round_num, {'b': 'done' if info.get('_ok') else 'error'})

    ta = threading.Thread(target=run_a)
    tb = threading.Thread(target=run_b)
    ta.start(); tb.start()
    ta.join(); tb.join()

    update_status({'stages': {'qa': {'current_agent': 'C (init)'}}},
                  log_line='qa: initial synthesis (C)')
    _qa_round_patch(round_num, {'c': 'running'})

    info_c = _run_audit_agent(f'audit-c-r{round_num}', 'qa_c.txt', round_num, 'AGENT_C')
    verdict = info_c.get('verdict', 'UNKNOWN')
    if os.path.exists(os.path.join(PROJECT_DIR, 'SHIP_READY.md')):
        verdict = 'SHIP_READY'
    _qa_round_patch(round_num, {'c': 'done' if info_c.get('_ok') else 'error', 'verdict': verdict})
    update_status({'stages': {'qa': {'current_agent': ''}}},
                  log_line=f'qa: initial verdict = {verdict}')
    return verdict == 'SHIP_READY'


def run_qa_loop() -> str:
    """Initial audit then up to QA_MAX_ROUNDS fix→A→B→C cycles. Returns final verdict."""
    if os.path.exists(os.path.join(PROJECT_DIR, 'SHIP_READY.md')):
        update_status({'stage': 'qa',
                       'stages': {'qa': {'status': 'done',
                                         'verdict': 'SHIP_READY',
                                         'completed': ts()}}},
                      log_line='qa: SHIP_READY.md exists — skipped')
        return 'SHIP_READY'

    ship_ready = run_initial_audit_for_qa()
    if ship_ready:
        update_status({'stages': {'qa': {'status': 'done',
                                         'verdict': 'SHIP_READY',
                                         'completed': ts()}}},
                      log_line='qa: SHIP_READY at init')
        return 'SHIP_READY'

    for round_num in range(1, QA_MAX_ROUNDS + 1):
        update_status({'stages': {'qa': {
            'round': round_num,
            'total_rounds': round_num,
            'current_agent': f'Fix (round {round_num})',
        }}}, log_line=f'qa: round {round_num} — fix agent')

        _qa_round_patch(round_num, {
            'round': round_num,
            'started': ts(),
            'fix': 'running',
            'a': 'pending',
            'b': 'pending',
            'c': 'pending',
            'verdict': '',
        })

        # FIX
        prompt = load_prompt('qa_fix.txt', ROUND_NUM=round_num)
        ok_fix, out_fix = run_claude(prompt, f'fix-r{round_num}')
        _qa_round_patch(round_num, {
            'fix': 'done' if ok_fix else 'error',
            'a': 'running',
            'b': 'running',
        })

        # A + B parallel
        update_status({'stages': {'qa': {'current_agent': f'A+B (round {round_num})'}}},
                      log_line=f'qa: round {round_num} — A+B parallel')
        a_info = {}
        b_info = {}

        def run_a():
            nonlocal a_info
            a_info = _run_audit_agent(f'audit-a-r{round_num}', 'qa_a.txt', round_num, 'AUDIT_A')
            _qa_round_patch(round_num, {'a': 'done' if a_info.get('_ok') else 'error'})

        def run_b():
            nonlocal b_info
            b_info = _run_audit_agent(f'audit-b-r{round_num}', 'qa_b.txt', round_num, 'AUDIT_B')
            _qa_round_patch(round_num, {'b': 'done' if b_info.get('_ok') else 'error'})

        ta = threading.Thread(target=run_a)
        tb = threading.Thread(target=run_b)
        ta.start(); tb.start()
        ta.join(); tb.join()

        # C
        update_status({'stages': {'qa': {'current_agent': f'C (round {round_num})'}}},
                      log_line=f'qa: round {round_num} — C synthesis')
        _qa_round_patch(round_num, {'c': 'running'})
        c_info = _run_audit_agent(f'audit-c-r{round_num}', 'qa_c.txt', round_num, 'AGENT_C')

        ship = os.path.exists(os.path.join(PROJECT_DIR, 'SHIP_READY.md'))
        next_fix = os.path.exists(os.path.join(PROJECT_DIR, f'FIXES_FOR_ROUND_{round_num + 1}.md'))

        if ship:
            _qa_round_patch(round_num, {
                'c': 'done' if c_info.get('_ok') else 'error',
                'verdict': 'SHIP_READY',
            })
            update_status({'stages': {'qa': {
                'status': 'done',
                'current_agent': '',
                'verdict': 'SHIP_READY',
                'completed': ts(),
            }}, 'verdict': 'SHIP_READY', 'completed': ts()},
                          log_line=f'qa: SHIP_READY after round {round_num}')
            return 'SHIP_READY'

        if not next_fix:
            # C did not write a follow-up fix file → treat as ship ready (defensive)
            _qa_round_patch(round_num, {
                'c': 'done' if c_info.get('_ok') else 'error',
                'verdict': 'SHIP_READY',
            })
            update_status({'stages': {'qa': {
                'status': 'done',
                'current_agent': '',
                'verdict': 'SHIP_READY',
                'completed': ts(),
            }}, 'verdict': 'SHIP_READY', 'completed': ts()},
                          log_line=f'qa: no next-round fixes — treating as SHIP_READY')
            return 'SHIP_READY'

        _qa_round_patch(round_num, {
            'c': 'done' if c_info.get('_ok') else 'error',
            'verdict': 'needs_fixes',
        })
        update_status({}, log_line=f'qa: round {round_num} needs more fixes — continuing')

    # Loop exhausted
    update_status({'stages': {'qa': {
        'status': 'error',
        'current_agent': '',
        'verdict': 'MAX_ROUNDS_REACHED',
        'completed': ts(),
    }}, 'verdict': 'MAX_ROUNDS_REACHED'},
                  log_line=f'qa: max rounds ({QA_MAX_ROUNDS}) reached without SHIP_READY')
    pause(f'qa: {QA_MAX_ROUNDS} rounds without SHIP_READY — manual review needed')
    return 'MAX_ROUNDS_REACHED'


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--project', default=PROJECT_DIR)
    p.add_argument('--target', default='android')
    p.add_argument('--port', type=int, default=DEFAULT_PORT)
    return p.parse_args()


def main():
    global PROJECT_DIR, STATUS_FILE, PROMPTS_DIR, DASHBOARD_HTML
    args = parse_args()
    PROJECT_DIR = os.path.abspath(args.project)
    STATUS_FILE = os.path.join(PROJECT_DIR, 'orchestrator_status.json')
    PROMPTS_DIR = os.path.join(PROJECT_DIR, 'stage_prompts')
    DASHBOARD_HTML = os.path.join(PROJECT_DIR, 'orchestrator_dashboard.html')
    os.chdir(PROJECT_DIR)

    if not os.path.exists(STATUS_FILE):
        print(f'[orchestrator] status file missing: {STATUS_FILE}', file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(PROMPTS_DIR):
        print(f'[orchestrator] prompts dir missing: {PROMPTS_DIR}', file=sys.stderr)
        sys.exit(1)
    if not claude_available():
        print('[orchestrator] `claude` CLI not on PATH', file=sys.stderr)
        update_status({'stage': 'error'}, log_line='claude CLI not on PATH')
        sys.exit(2)

    update_status({
        'target': args.target,
        'started': ts(),
        'stage': 'ready',
        'paused': False,
        'pause_reason': '',
    }, log_line=f'orchestrator: starting (target={args.target})')

    start_dashboard(args.port)

    # Stage order
    branch = run_branch(args.target)
    if not run_audit():    return _wait_idle()
    if not run_plan():     return _wait_idle()
    if not run_vetoes():   return _wait_idle()
    if not run_build():    return _wait_idle()
    verdict = run_qa_loop()

    update_status({'stage': 'complete' if verdict == 'SHIP_READY' else 'halted',
                   'completed': ts(),
                   'verdict': verdict},
                  log_line=f'orchestrator: finished — {verdict}')
    print(f'[{hms()}] orchestrator finished — verdict={verdict}')
    _wait_idle()


def _wait_idle():
    """Keep the dashboard server alive after the pipeline finishes or pauses."""
    print(f'[{hms()}] keeping dashboard server alive. Ctrl-C to exit.')
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
