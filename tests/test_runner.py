"""Contract tests use real subprocesses and disposable Git repositories, no model calls."""
import contextlib
import copy
import importlib.util
import io
import json
import os
import shutil
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("runner", ROOT / "skills/claudex-loop/scripts/runner.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
SESSION = "12345678-1234-4567-8123-123456789abc"
GOOD = {"verdict": "APPROVED", "summary": "The supplied acceptance criteria are consistent.",
        "findings": [], "coverage": ["docs/custom plan.md"], "limitations": []}

FAKE_CLI = r'''
import json, os, pathlib, sys, time
if '--version' in sys.argv:
    print('fake-cli 1.0')
    sys.exit(0)
if '--help' in sys.argv:
    print('' if os.environ.get('FAKE_NO_RESTRICTED') else '  --restricted  Restricted mode')
    sys.exit(0)
if sys.argv[1:3] == ['mcp', 'list']:
    if os.environ.get('FAKE_MCP_FAIL'):
        sys.exit(2)
    off = {a.split('.')[1] for a in sys.argv if a.startswith('mcp_servers.') and a.endswith('.enabled=false')}
    sticky = os.environ.get('FAKE_MCP_STICKY', '')
    servers = [('playwright', True), ('tradingview-desktop', True), ('disabled_one', False)]
    servers += [(sticky, True)] if sticky else []
    print(json.dumps([{'name': n, 'enabled': e and (n == sticky or n not in off)} for n, e in servers]))
    sys.exit(0)
if sys.argv[1:3] == ['features', 'list']:
    if os.environ.get('FAKE_FEATURES_FAIL'):
        sys.exit(2)
    if os.environ.get('FAKE_FEATURES_EMPTY'):
        sys.exit(0)
    rows = ['apps  stable  true', 'plugins  stable  true', 'shell_tool  stable  true',
            'view_image  stable  true', 'search_tool  removed  false']
    print('\n'.join(r for r in rows if r.split()[0] != os.environ.get('FAKE_FEATURES_DROP')))
    sys.exit(0)
prompt = sys.stdin.read()
if ('--verbose' in sys.argv or '--ignore-user-config' in sys.argv) and os.environ.get('FAKE_PANEL_DIR'):
    # Panel worker: record what it received, optionally stay alive, then replay its script.
    import re
    worker = re.search(r'^WORKER ID: (\S+)$', prompt, re.M).group(1)
    d = pathlib.Path(os.environ['FAKE_PANEL_DIR'])
    (d / (worker + '.argv.json')).write_text(json.dumps(sys.argv))
    (d / (worker + '.stdin.txt')).write_text(prompt, encoding='utf-8')
    (d / (worker + '.cwd.txt')).write_text(os.getcwd())
    if (d / (worker + '.sleep')).exists():
        end = time.time() + float((d / (worker + '.sleep')).read_text())
        while time.time() < end:
            (d / (worker + '.beat')).write_text(str(time.time()))
            time.sleep(0.05)
    script = d / (worker + '.jsonl')
    sys.stdout.write(script.read_text() if script.exists() else '')
    code = d / (worker + '.exit')
    sys.exit(int(code.read_text()) if code.exists() else 0)
case = os.environ.get('FAKE_CASE', 'ok')
if case == 'timeout':
    time.sleep(30)
if case == 'exit':
    print('Authentication failed', file=sys.stderr)
    sys.exit(7)
if case == 'quota':
    print('Usage limit reached; quota exhausted', file=sys.stderr)
    sys.exit(7)
if case == 'empty':
    sys.exit(0)
if case in ('claude_429', 'claude_result_spoof', 'claude_400'):
    # Shape of a real Claude Code 2.1.277 spend-limit response: the reason text sits in
    # the model-authored `result` field; only api_error_status/terminal_reason are structured.
    value = {'type':'result','subtype':'success','is_error':True,'num_turns':1,
             'session_id':'12345678-1234-4567-8123-123456789abc',
             'result':"You've hit your individual spend limit",
             'terminal_reason':'api_error','api_error_status':429}
    if case == 'claude_result_spoof':
        del value['terminal_reason'], value['api_error_status']
    if case == 'claude_400':
        value['api_error_status'] = 400
    print(json.dumps(value))
    sys.exit(1)
if case == 'mutate_plan':
    pathlib.Path(os.environ['FAKE_PLAN']).write_text('Changed after launch')
if case == 'mutate_code':
    pathlib.Path('new.py').write_text('changed during inspection')
if case == 'build':
    pathlib.Path('built.py').write_text('print(42)\n')
session = '12345678-1234-4567-8123-123456789abc'
if case == 'wrong_session':
    session = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
review = {'verdict':'APPROVED', 'summary':'Inspected supplied plan.',
          'findings':[], 'coverage':['custom plan.md'], 'limitations':[]}
if case == 'revise':
    review.update(verdict='REVISE', findings=[{'id':'R1','severity':'high','path':'plan',
                  'evidence':'Deletion before successful copy loses the only copy.',
                  'fix':'Verify the new copy before removing the old one.'}])
if case == 'blocked':
    review.update(verdict='BLOCKED', coverage=[], limitations=['Required schema unavailable.'])
if case == 'malformed':
    review = {'verdict':'APPROVED'}
if case == 'arrow':
    review['summary'] = 'Sound ' + chr(0x2192) + ' ok'
if 'exec' in sys.argv:
    output = pathlib.Path(sys.argv[sys.argv.index('-o')+1])
    output.write_text('Built; proof passed.' if case == 'build' else json.dumps(review))
    print(json.dumps({'type':'thread.started', 'thread_id':session}))
    if case == 'turn_failed':
        print(json.dumps({'type':'turn.failed', 'error':{'message':'quota'}}))
    elif case != 'incomplete':
        print(json.dumps({'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':5}}))
else:
    value = {'type':'result','subtype':'success','is_error':False,'session_id':session,
             'structured_output':review, 'result':'Built; proof passed.',
             'modelUsage':{'claude-test':{'inputTokens':10}},'usage':{'input_tokens':10}}
    if case == 'turn_failed':
        value.update(subtype='error_during_execution',is_error=True)
    print(json.dumps([{'type':'system','subtype':'init'}, value] if case == 'array' else value))
'''

FAKE_AGY = r'''
import json, os, pathlib, re, sqlite3, sys
home = pathlib.Path(os.environ['HOME'])
case = os.environ.get('FAKE_AGY_CASE', 'ok')
if '--version' in sys.argv:
    if case == 'version_drift':
        marker = pathlib.Path(os.environ['FAKE_AGY_DIR']) / 'version.count'
        count = int(marker.read_text()) + 1 if marker.exists() else 1
        marker.write_text(str(count))
        print('9.9.9' if count > 1 else '1.2.9')
    else:
        print('9.9.9' if case == 'version' else '1.2.9')
    sys.exit(0)
if sys.argv[1:3] == ['mcp', 'list']:
    print('Server configured' if case == 'mcp' else 'No MCP servers configured.')
    sys.exit(0)
if sys.argv[1:3] == ['plugin', 'list']:
    print('Plugin configured' if case == 'plugin' else 'No imported plugins.')
    sys.exit(0)
if sys.argv[1:3] == ['-p', '/usage']:
    print('Authentication required' if case == 'auth' else
          'Gemini Models\tWeekly Limit Remaining\t' + ('0%' if case == 'quota' else '100%') +
          '\t2026-09-30T11:59:45Z\nClaude and GPT models\tWeekly Limit Remaining\t100%\t2026-09-30T14:34:45Z')
    sys.exit(0)
payload = json.loads(sys.stdin.readline())
prompt = payload['message']['content']
worker_match = re.search(r'^WORKER ID: (\S+)$', prompt, re.M)
worker = worker_match.group(1) if worker_match else 'review'
data = pathlib.Path(os.environ['FAKE_AGY_DIR'])
(data / (worker + '.argv.json')).write_text(json.dumps(sys.argv), encoding='utf-8')
(data / (worker + '.stdin.json')).write_text(json.dumps(payload), encoding='utf-8')
(data / (worker + '.cwd.txt')).write_text(os.getcwd(), encoding='utf-8')
(data / (worker + '.home.txt')).write_text(str(home), encoding='utf-8')
session = {'w1':'11111111-1111-4111-8111-111111111111',
           'w2':'22222222-2222-4222-8222-222222222222',
           'review':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'}[worker]
if case == 'wrong_id':
    session = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
model = sys.argv[sys.argv.index('--model') + 1]
url = 'https://example.org/' + worker
claim = {'id':'c1', 'question_id':'q1', 'claim':'A supported statement.',
         'source_type':'web', 'locator':url, 'excerpt':'Verified source text',
         'confidence':'high', 'limitation':''}
value = ({'verdict':'APPROVED', 'summary':'Plan checked.', 'findings':[],
          'coverage':['supplied plan body'], 'limitations':[]} if worker == 'review' else
         {'summary':'Research complete.', 'claims':[claim], 'coverage':['angle'], 'limitations':[]})
tool = 'view_file' if case == 'hostile_tool' else 'read_url_content'
entries = [] if worker == 'review' else [{'name':tool, 'args':{'Url':url, 'toolAction':'read'}}]
root = home / '.gemini' / 'antigravity-cli'
logs = root / 'brain' / session / '.system_generated' / 'logs'
logs.mkdir(parents=True, exist_ok=True)
transcript = [{'step_index':0,'source':'USER_EXPLICIT','type':'USER_INPUT','content':prompt}]
if entries:
    transcript += [{'step_index':1,'source':'MODEL','type':'PLANNER_RESPONSE','tool_calls':entries},
                   {'step_index':2,'source':'MODEL','type':'GENERIC','status':'DONE',
                    'content':'Verified source text'}]
if case != 'missing_transcript':
    scripted_transcript = data / (worker + '.transcript.jsonl')
    (logs / 'transcript_full.jsonl').write_text(
        scripted_transcript.read_text(encoding='utf-8') if scripted_transcript.exists() else
        ''.join(json.dumps(x)+'\n' for x in transcript), encoding='utf-8')
page = data / (worker + '.page.md')
if page.exists():  # read_url_content saves the fetched page here and returns only its path
    steps = root / 'brain' / session / '.system_generated' / 'steps' / '2'
    steps.mkdir(parents=True, exist_ok=True)
    (steps / 'content.md').write_text(page.read_text(encoding='utf-8'), encoding='utf-8')
conversations = root / 'conversations'
conversations.mkdir(exist_ok=True)
(conversations / (session + '.db')).write_text('test', encoding='utf-8')
with sqlite3.connect(root / 'conversation_summaries.db') as db:
    db.execute('CREATE TABLE IF NOT EXISTS conversation_summaries (conversation_id TEXT PRIMARY KEY)')
    db.execute('INSERT OR REPLACE INTO conversation_summaries VALUES (?)', (session,))
scripted_stream = data / (worker + '.stream.jsonl')
if scripted_stream.exists():
    sys.stdout.write(scripted_stream.read_text(encoding='utf-8'))
    scripted_stderr = data / (worker + '.stderr.txt')
    if scripted_stderr.exists():
        sys.stderr.write(scripted_stderr.read_text(encoding='utf-8'))
    sys.exit(0)
print(json.dumps({'event':'init','conversation_id':session,'init':
                  {'model':model,'cwd':os.getcwd(),'tools':[],'permission_mode':'request-review'}}))
if entries:
    print(json.dumps({'event':'step_update','step_update':{'conversation_id':session,
                      'step_index':1,'state':'DONE','step_type':'tool',
                      'tool_name':'search_web' if case == 'stream_disagree' else tool}}))
if case == 'denied':
    print('jetski: no output produced — tool permission auto-denied', file=sys.stderr)
if case == 'api_error':
    print('AGY_ERROR: {"message":"unavailable"}', file=sys.stderr)
print(json.dumps({'event':'result','result':{'conversation_id':session,
                  'status':'ERROR' if case == 'api_error' else 'SUCCESS',
                  'response':'' if case == 'denied' else json.dumps(value),
                  'structured_output':value,'usage':{'input_tokens':3}}}))
sys.exit(3 if case == 'api_error' else 0)
'''


FAKE_DSH = r"""
import json, os, pathlib, subprocess, sys
case = os.environ.get('FAKE_DSH_CASE', 'ok')
d = pathlib.Path(os.environ['FAKE_DSH_DIR'])
with open(d / 'invocations.txt', 'a') as marker:
    marker.write(' '.join(sys.argv[1:]) + '\n')
if sys.argv[1:] == ['--version']:
    print('9.9.9' if case == 'version' else '0.2.1-rc.2')
    sys.exit(0)
if '--dump-config' in sys.argv:
    if case == 'dump_fail':
        sys.exit(2)
    if case == 'dump_patch_warn':
        print('dsh: [p.yml] patch: entry "tool-working-directory" not found', file=sys.stderr)
    patch_path = sys.argv[sys.argv.index('--patch') + 1]
    ids = json.loads(os.environ['FAKE_DSH_IDS'])
    out = ['# == @deepseek-ai/dsh-base'] + ['- id: %s\n  name: x' % i for i in ids]
    out += ['# == @deepseek-ai/dsh-base, patched by ' + patch_path, '- id: tool-bash\n  name: x\n  disabled: true']
    if case == 'user_layer':
        out += ['# == /home/u/.dsh/profiles/headless/cordis.patch.yml', '- id: tool-fs\n  name: x']
    if case == 'extra_plugin':
        out += ['# == @deepseek-ai/dsh-hooks', '- id: hooks-claude-code\n  name: x']
    if case in ('authorization', 'deepseek-account'):
        out += ['# == @deepseek-ai/dsh-base', '- id: %s\n  name: x' % case]
    print('\n'.join(out))
    sys.exit(0)
prompt = sys.stdin.read()
(d / 'argv.json').write_text(json.dumps(sys.argv))
(d / 'env.json').write_text(json.dumps({k: v for k, v in os.environ.items() if k.startswith('DSH_')}))
(d / 'stdin.txt').write_text(prompt, encoding='utf-8')
(d / 'cwd.txt').write_text(os.getcwd())
patch = pathlib.Path(sys.argv[sys.argv.index('--patch') + 1]).read_text()
(d / 'patch.yml').write_text(patch)
sid = 'session-0b5f3c1e-7d2a-4b8e-9f10-2a3b4c5d6e7f'
good = json.dumps({"verdict": "APPROVED", "summary": "Consistent.", "findings": [],
                   "coverage": ["plan"], "limitations": []})
final = {'malformed': 'not json at all', 'final_auth': 'dsh: AUTH: quota exceeded, rate limit',
         'fenced': '```json\n' + good + '\n```'}.get(case, good)
call = {'type': 'tool_call', 'callId': 'c1', 'tool': 'read', 'input': {'file_path': 'existing.py'}}
result = {'type': 'tool_result', 'callId': 'c1', 'status': 'completed', 'result': 'original'}
if case in ('disallowed', 'violation_and_auth'):
    call = {'type': 'tool_call', 'callId': 'c1', 'tool': 'bash', 'input': {'command': 'ls'}}
elif case == 'outside':
    call['input'] = {'file_path': os.environ['FAKE_DSH_OUTSIDE']}
elif case == 'plan_read':
    call['input'] = {'file_path': os.environ['FAKE_DSH_PLAN']}
elif case == 'glob_escape':
    call = {'type': 'tool_call', 'callId': 'c1', 'tool': 'glob', 'input': {'pattern': '**/../../*'}}
elif case == 'escalation':
    call['input'] = {'file_path': 'existing.py', 'sandbox_permissions': 'workspace-write'}
elif case == 'truncated_call':
    call['truncated'] = True
elif case == 'no_input':
    del call['input']
elif case == 'unmatched_result':
    result['callId'] = 'c9'
elif case == 'list_result_id':
    result['callId'] = []
elif case == 'symlink_loop':
    call['input'] = {'file_path': 'loop'}
elif case == 'grep_include':
    call = {'type': 'tool_call', 'callId': 'c1', 'tool': 'grep',
            'input': {'pattern': 'add', 'path': '.', 'include': '*.py'}}
elif case == 'big_result':
    result.update(result='x' * 8192, truncated=True)
if case == 'write':
    (pathlib.Path.cwd() / 'existing.py').write_text('changed\n')
elif case == 'write_modified':
    (pathlib.Path.cwd() / 'existing.py').write_text('modified again\n')
elif case == 'write_untracked':
    (pathlib.Path.cwd() / 'scratch.txt').write_text('changed untracked\n')
elif case == 'index_only':
    subprocess.run(['git', 'add', 'existing.py'], check=True)
events = [{'type': 'session', 'sessionId': sid, 'cwd': os.getcwd()},
          {'type': 'status', 'phase': 'turn_start', 'turn': 1}, call, result,
          {'type': 'status', 'phase': 'step_end', 'turn': 1, 'step': 1,
           'usage': {'inputTokens': 10, 'outputTokens': 5, 'cacheReadTokens': 3}}]
codes = {'server': ('SERVER', 'Internal Server Error'), 'rate': ('RATE_LIMIT', 'Too many requests'),
         'bad_request': ('INVALID_REQUEST', 'The supported API model names are deepseek-flash'),
         'failed_turn': ('AUTH', 'rate limit exceeded')}
if case == 'failed_turn_exit0':
    events.append({'type': 'status', 'phase': 'turn_end', 'turn': 1, 'reason': {'kind': 'error',
                   'error': {'message': 'Internal Server Error', 'code': 'SERVER'}}})
    events.append({'type': 'final', 'text': ''})
    print('\n'.join(json.dumps(e) for e in events))
    sys.exit(0)
if case in codes:
    code, message = codes[case]
    events.append({'type': 'status', 'phase': 'turn_end', 'turn': 1, 'reason': {'kind': 'error',
                   'error': {'message': message, 'code': code}}})
    events.append({'type': 'final', 'text': ''})
    print('\n'.join(json.dumps(e) for e in events))
    print('dsh: %s: %s' % (code, message), file=sys.stderr)
    sys.exit(1)
if case in ('auth', 'violation_and_auth'):
    events.append({'type': 'status', 'phase': 'turn_end', 'turn': 1, 'reason': {'kind': 'error',
                   'error': {'message': 'bad key', 'code': 'AUTH'}}})
    events.append({'type': 'final', 'text': ''})
else:
    events.append({'type': 'final', 'text': final})
if case == 'violation_timeout':
    print(json.dumps(events[0]), flush=True)
    print(json.dumps({'type': 'tool_call', 'callId': 'c1', 'tool': 'bash', 'input': {'command': 'ls'}}), flush=True)
    import time
    time.sleep(30)
if case == 'torn_call':
    print(json.dumps(events[0]))
    print('{"type":"tool_call","callId":"c1","tool":"read","input":{"file_pa')
    print('dsh: AUTH: invalid API key', file=sys.stderr)
    sys.exit(1)
print('\n'.join(json.dumps(e) for e in events))
if case in ('auth', 'violation_and_auth'):
    print('dsh: AUTH: invalid API key', file=sys.stderr)
    sys.exit(1)
if case == 'patch_warn':
    print('dsh: warning: 1 entry did not activate', file=sys.stderr)
"""


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="claudex-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo with spaces"
        self.repo.mkdir()
        self.plan = self.root / "custom plan.md"
        self.plan.write_text("# Work order\nKeep the original until the copy is verified.\n", encoding="utf-8")
        self.artifacts = self.root / "runs"
        self.cli = self.root / "fake_cli.py"
        self.cli.write_text(FAKE_CLI)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        (self.repo / "existing.py").write_text("original\n")
        (self.repo / "delete.py").write_text("delete me\n")
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, stderr=subprocess.PIPE).decode()

    def invoke(self, host="claude", mode="review", case="ok", extra=()):
        args = [mode, "--host", host, "--repo", str(self.repo), "--plan", str(self.plan),
                "--artifacts", str(self.artifacts), *extra]
        old = set(self.artifacts.glob("*/result.json")) if self.artifacts.exists() else set()
        output, error = io.StringIO(), io.StringIO()
        with patch.object(runner, "cli_prefix", return_value=[sys.executable, str(self.cli)]), \
             patch.dict(os.environ, {"FAKE_CASE": case, "FAKE_PLAN": str(self.plan)}), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = runner.main(args)
        new = set(self.artifacts.glob("*/result.json")) - old if self.artifacts.exists() else set()
        path = next(iter(new)) if new else None
        return code, json.loads(path.read_text()) if path else None, path, error.getvalue()

    def test_host_role_defaults_and_builder_override(self):
        self.assertEqual(runner.resolve_roles("claude")["reviewer"], "codex")
        self.assertEqual(runner.resolve_roles("codex")["reviewer"], "claude")
        self.assertEqual(runner.resolve_roles("deepseek"),
                         {"host": "deepseek", "planner": "deepseek", "reviewer": "claude",
                          "builder": "deepseek", "inspector": "claude"})
        roles = runner.resolve_roles("codex", builder="claude")
        self.assertEqual((roles["planner"], roles["builder"], roles["inspector"]), ("codex", "claude", "codex"))
        roles = runner.resolve_roles("deepseek", reviewer="agy", builder="codex")
        self.assertEqual((roles["reviewer"], roles["builder"], roles["inspector"]), ("agy", "codex", "claude"))
        self.assertEqual(runner.resolve_roles("deepseek", builder="claude")["inspector"], "codex")
        with self.assertRaises(runner.RunError):
            runner.resolve_roles("codex", "codex")
        with self.assertRaisesRegex(runner.RunError, "only as the active host"):
            runner.resolve_roles("claude", builder="deepseek")

    def test_roles_command_reports_independent_selections_and_rejects_self_review(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = runner.main(["roles", "--host", "codex", "--reviewer", "deepseek",
                                "--builder", "claude", "--inspector", "codex"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()),
                         {"host": "codex", "planner": "codex", "reviewer": "deepseek",
                          "builder": "claude", "inspector": "codex"})
        for flag in ("--reviewer", "--provider"):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(runner.main(["roles", "--host", "codex", flag, "codex"]), 1)

    def test_both_review_adapters_complete_and_bind_custom_plan(self):
        for host in ("claude", "codex"):
            with self.subTest(host=host):
                code, record, path, _ = self.invoke(host)
                self.assertEqual(code, 0, record)
                self.assertEqual(record["session_id"], SESSION)
                self.assertEqual(record["plan"], str(self.plan))
                self.assertEqual(record["plan_sha256"], runner.digest(self.plan.read_bytes()))
                self.assertIn(str(self.plan), (path.parent / "prompt.txt").read_text())
                self.assertIn("`- [ ]` checkbox", (path.parent / "prompt.txt").read_text())
                self.assertEqual(record["response"]["verdict"], "APPROVED")
                self.assertEqual(record["assurance"], "cross_provider")

    def test_independent_role_selectors_route_the_current_turn(self):
        extra = ("--reviewer", "codex", "--builder", "codex", "--inspector", "deepseek")
        code, review, approval, error = self.invoke(extra=extra)
        self.assertEqual(code, 0, error)
        self.assertEqual(review["provider"], "codex")
        self.assertEqual(review["roles"], {"host": "claude", "planner": "claude", "reviewer": "codex",
                                         "builder": "codex", "inspector": "deepseek"})
        code, build, _, error = self.invoke(mode="build", case="build",
                                          extra=extra + ("--approval", str(approval), "--proof", "test"))
        self.assertEqual(code, 0, error)
        self.assertEqual(build["provider"], "codex")
        self.assertEqual(build["roles"], review["roles"])

    def test_deepseek_host_uses_claude_codex_or_agy_for_review_and_inspection(self):
        code, review, approval, error = self.invoke("deepseek")
        self.assertEqual(code, 0, error)
        self.assertEqual(review["roles"]["host"], "deepseek")
        self.assertEqual((review["provider"], review["roles"]["reviewer"]), ("claude", "claude"))
        self.assertEqual(review["assurance"], "cross_provider")
        code, _, _, error = self.invoke("deepseek", mode="check",
                                        extra=("--approval", str(approval)))
        self.assertEqual(code, 0, error)
        with self.assertRaises(runner.RunError):
            runner.check_approval(review, self.plan, self.repo, "claude")

        for reviewer, inspector in (("codex", "claude"), ("claude", "codex")):
            with self.subTest(reviewer=reviewer, inspector=inspector):
                selection = ("--reviewer", reviewer, "--inspector", inspector)
                code, reviewed, _, error = self.invoke("deepseek", extra=selection)
                self.assertEqual(code, 0, error)
                self.assertEqual(reviewed["provider"], reviewer)
                code, inspected, _, error = self.invoke(
                    "deepseek", mode="inspect", extra=selection + ("--base", self.base))
                self.assertEqual(code, 0, error)
                self.assertEqual((inspected["provider"], inspected["roles"]["inspector"]),
                                 (inspector, inspector))
                self.assertEqual(inspected["roles"]["builder"], "deepseek")

        code, _, build_approval, error = self.invoke(
            "deepseek", extra=("--reviewer", "claude", "--builder", "codex"))
        self.assertEqual(code, 0, error)
        code, build, _, error = self.invoke(
            "deepseek", mode="build", case="build",
            extra=("--builder", "codex", "--approval", str(build_approval), "--proof", "true"))
        self.assertEqual(code, 0, error)
        self.assertEqual((build["provider"], build["roles"]["builder"]), ("codex", "codex"))

    def test_deepseek_host_refuses_self_review_and_delegated_deepseek_build(self):
        cases = (("review", ("--reviewer", "deepseek"), "must differ from the planner"),
                 ("inspect", ("--inspector", "deepseek", "--base", self.base),
                  "must differ from the builder"))
        for mode, extra, message in cases:
            with self.subTest(mode=mode):
                code, record, _, error = self.invoke("deepseek", mode=mode, extra=extra)
                self.assertEqual((code, record), (1, None))
                self.assertIn(message, error)
        code, record, _, error = self.invoke(
            "deepseek", mode="build",
            extra=("--builder", "deepseek", "--unreviewed-spec", "--proof", "true"))
        self.assertEqual((code, record), (1, None))
        self.assertIn("not a runner build target", error)

    def test_deepseek_host_has_no_automatic_fallback_to_itself(self):
        code, failed, primary, error = self.invoke("deepseek", case="quota")
        self.assertEqual(code, 1, error)
        self.assertEqual((failed["failure_kind"], failed["fallback_eligible"]),
                         ("provider_unavailable", True))
        code, record, _, error = self.invoke(
            "deepseek", extra=("--provider", "deepseek", "--fallback-from", str(primary)))
        self.assertEqual((code, record), (1, None))
        self.assertIn("no automatic same-provider fallback", error)
        code, record, _, error = self.invoke(
            "deepseek", extra=("--provider", "claude", "--fallback-from", str(primary)))
        self.assertEqual((code, record), (1, None))
        self.assertIn("no automatic same-provider fallback", error)

    def test_windows_deepseek_refusal_reports_fallback_ineligibility_first(self):
        # Ineligibility is platform-independent; the Windows support limit must not mask it.
        _, _, primary, _ = self.invoke("deepseek", case="quota")
        with patch.object(runner.sys, "platform", "win32"):
            code, record, _, error = self.invoke(
                "deepseek", extra=("--provider", "deepseek", "--fallback-from", str(primary)))
        self.assertEqual((code, record), (1, None))
        self.assertIn("no automatic same-provider fallback", error)

    def test_role_conflicts_and_self_review_are_rejected_before_launch(self):
        cases = (("review", ("--reviewer", "deepseek", "--provider", "codex")),
                 ("inspect", ("--inspector", "deepseek", "--provider", "codex", "--base", self.base)),
                 ("build", ("--builder", "codex", "--provider", "claude")),
                 ("review", ("--reviewer", "claude")),
                 ("inspect", ("--inspector", "claude", "--base", self.base)))
        for mode, extra in cases:
            with self.subTest(mode=mode, extra=extra):
                code, record, _, error = self.invoke(mode=mode, extra=extra)
                self.assertEqual(code, 1)
                self.assertIsNone(record)
                self.assertTrue(error)

    def test_selected_roles_survive_degraded_fallback_and_resume(self):
        selection = ("--reviewer", "claude", "--inspector", "deepseek")
        code, failed, primary, error = self.invoke("codex", case="quota", extra=selection)
        self.assertEqual(code, 1, error)
        fallback = selection + ("--provider", "codex", "--fallback-from", str(primary))
        code, record, previous, error = self.invoke("codex", case="revise", extra=fallback)
        self.assertEqual(code, 0, error)
        self.assertEqual(record["roles"], failed["roles"])
        self.assertEqual(record["assurance"], "degraded_same_provider")
        self.plan.write_text("Updated after review", encoding="utf-8")
        code, record, _, error = self.invoke("codex", extra=fallback + ("--resume", str(previous)))
        self.assertEqual(code, 0, error)
        self.assertEqual(record["fallback_session_state"], "resumed")

    def test_selected_inspector_survives_degraded_fallback(self):
        selection = ("--reviewer", "deepseek", "--inspector", "claude", "--base", self.base)
        code, failed, primary, error = self.invoke("codex", mode="inspect", case="quota", extra=selection)
        self.assertEqual(code, 1, error)
        code, record, _, error = self.invoke(
            "codex", mode="inspect", extra=selection + ("--provider", "codex", "--fallback-from", str(primary)))
        self.assertEqual(code, 0, error)
        self.assertEqual(record["roles"], failed["roles"])
        self.assertEqual(record["assurance"], "degraded_same_provider")

    def test_unpinned_and_explicit_model_selection(self):
        for provider in runner.PROVIDERS:
            args = runner.command(provider, "review", self.root)
            self.assertNotIn("--model", args)
            self.assertNotIn("-m", args)
            pinned = runner.command(provider, "review", self.root, "chosen-model", "high")
            self.assertIn("chosen-model", pinned)

    def test_claude_exposes_only_read_tools_and_no_mcp(self):
        args = runner.command("claude", "review", self.root)
        self.assertEqual(args[args.index("--tools")+1], "Read,Glob,Grep")
        self.assertIn("--safe-mode", args)
        self.assertIn("--strict-mcp-config", args)
        self.assertEqual(args[args.index("--permission-mode")+1], "dontAsk")

    def test_codex_readonly_runs_disable_connector_features_that_exist(self):
        code, record, path, _ = self.invoke("claude")
        self.assertEqual(code, 0, record)
        argv = json.loads((path.parent / "command.json").read_text())
        disabled = [argv[i + 1] for i, arg in enumerate(argv) if arg == "--disable"]
        self.assertEqual(disabled, ["apps", "plugins"])
        self.assertEqual(record["disabled_features"], ["apps", "plugins"])
        self.assertEqual(record["mcp_disabled"], ["playwright", "tradingview-desktop"])
        overrides = [argv[i + 1] for i, arg in enumerate(argv) if arg == "-c" and argv[i + 1].startswith("mcp_servers.")]
        self.assertEqual(overrides, ["mcp_servers.playwright.enabled=false",
                                     "mcp_servers.tradingview-desktop.enabled=false"])
        with patch.dict(os.environ, {"FAKE_FEATURES_EMPTY": "1"}):
            code, record, _, _ = self.invoke("claude")
        self.assertEqual(code, 1)
        self.assertIn("no recognizable features", record["error"])
        with patch.dict(os.environ, {"FAKE_FEATURES_DROP": "apps"}):
            code, record, _, _ = self.invoke("claude")
        self.assertEqual(code, 1)
        self.assertIn("apps", record["error"])
        code, record, path, _ = self.invoke("claude", mode="build", case="build",
                                            extra=("--builder", "codex", "--unreviewed-spec", "--proof", "true"))
        argv = json.loads((path.parent / "command.json").read_text())
        self.assertEqual([argv[i + 1] for i, arg in enumerate(argv) if arg == "--disable"],
                         ["apps", "plugins"])
        self.assertIn("notify=[]", argv)
        with patch.dict(os.environ, {"FAKE_FEATURES_FAIL": "1"}):
            code, record, _, _ = self.invoke("claude")
        self.assertEqual(code, 1)
        self.assertIn("feature probe failed", record["error"])

    def test_codex_mcp_servers_are_off_unless_allowed_and_proven_off(self):
        code, record, path, _ = self.invoke("claude", extra=("--codex-mcp-allow", "playwright"))
        self.assertEqual(code, 0, record)
        self.assertEqual((record["mcp_disabled"], record["mcp_allowed"]), (["tradingview-desktop"], ["playwright"]))
        self.assertNotIn("mcp_servers.playwright.enabled=false", json.loads((path.parent / "command.json").read_text()))
        for env, message in (({"FAKE_MCP_STICKY": "cua_repl"}, "stay enabled"),
                             ({"FAKE_MCP_FAIL": "1"}, "MCP listing failed"),
                             ({"FAKE_MCP_STICKY": "bad.name"}, "Cannot address")):
            with self.subTest(env=env), patch.dict(os.environ, env):
                code, record, _, _ = self.invoke("claude")
                self.assertEqual(code, 1)
                self.assertIn(message, record["error"])

    def test_codex_resume_keeps_read_only_and_explicit_session(self):
        args = runner.command("codex", "review", self.root, session=SESSION)
        self.assertEqual(args[:3], ["exec", "resume", SESSION])
        self.assertIn('sandbox_mode="read-only"', args)
        self.assertNotIn("-s", args)
        self.assertNotIn("--last", args)

    def test_builders_load_no_user_hooks_or_mcp_tools(self):
        claude = runner.command("claude", "build", self.root)
        self.assertEqual(json.loads(claude[claude.index("--settings") + 1]), {"disableAllHooks": True})
        self.assertEqual(claude[claude.index("--mcp-config") + 1], '{"mcpServers":{}}')
        self.assertIn("--strict-mcp-config", claude)
        codex = runner.command("codex", "build", self.root)
        self.assertEqual(codex.count("--disable"), 2)
        self.assertIn("notify=[]", codex)

    def test_codex_records_effective_settings_from_its_rollout(self):
        # Issue #38: the effective model/effort/sandbox live in Codex's session rollout.
        home = self.root / "codex-home"
        day = home / "sessions" / "2026" / "10" / "14"
        day.mkdir(parents=True)
        context = {"type": "turn_context", "payload": {"model": "gpt-test", "effort": "low",
                                                       "sandbox_policy": {"type": "read-only"}}}
        (day / f"rollout-2026-10-14T00-00-00-{SESSION}.jsonl").write_text(
            "\n".join([json.dumps({"type": "session_meta"}), json.dumps(context), ""]), encoding="utf-8")
        with patch.dict(os.environ, {"CODEX_HOME": str(home)}):
            code, record, _, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual((record["effective_model"], record["effective_effort"], record["effective_sandbox"]),
                         ("gpt-test", "low", "read-only"))
        self.assertEqual(record["observed_models"], [])

    def test_codex_run_without_rollout_still_completes(self):
        with patch.dict(os.environ, {"CODEX_HOME": str(self.root / "missing")}):
            code, record, _, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertNotIn("effective_model", record)

    def test_failures_never_approve_and_keep_diagnostics(self):
        for host in ("claude", "codex"):
            for case in ("exit", "empty", "malformed", "turn_failed"):
                with self.subTest(host=host, case=case):
                    code, record, path, _ = self.invoke(host, case=case)
                    self.assertEqual(code, 1)
                    self.assertEqual(record["status"], "failed")
                    self.assertTrue((path.parent / "stderr.txt").exists())
                    if case == "exit":
                        self.assertIn("Authentication failed", (path.parent / "stderr.txt").read_text())

    def test_missing_codex_completion_is_failure(self):
        code, record, _, _ = self.invoke(case="incomplete")
        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "failed")

    def test_claude_array_envelope(self):
        code, record, _, _ = self.invoke("codex", case="array")
        self.assertEqual(code, 0)
        self.assertEqual(record["observed_models"], ["claude-test"])

    def test_revise_and_blocked_are_completed_but_not_approval(self):
        for case in ("revise", "blocked"):
            code, record, _, _ = self.invoke(case=case)
            self.assertEqual(code, 0)
            with self.assertRaises(runner.RunError):
                runner.check_approval(record, self.plan, self.repo)

    def test_empty_findings_allowed_but_contradictory_approval_rejected(self):
        runner.validate_review(copy.deepcopy(GOOD))
        value = copy.deepcopy(GOOD)
        value["findings"] = [{"id":"1", "severity":"high", "path":"plan", "evidence":"data loss", "fix":"retain copy"}]
        with self.assertRaises(runner.RunError):
            runner.validate_review(value)

    def test_changed_plan_invalidates_approval(self):
        _, record, _, _ = self.invoke()
        runner.check_approval(record, self.plan, self.repo)
        self.plan.write_text("Different requirements")
        with self.assertRaises(runner.RunError):
            runner.check_approval(record, self.plan, self.repo)

    def test_changed_plan_during_review_fails(self):
        code, record, _, _ = self.invoke(case="mutate_plan")
        self.assertEqual(code, 1)
        self.assertIn("changed during", record["error"])

    def test_resume_revised_plan_same_session(self):
        _, _, previous, _ = self.invoke(case="revise")
        self.plan.write_text("New revision")
        code, record, _, _ = self.invoke(extra=("--resume", str(previous)))
        self.assertEqual(code, 0, record)
        self.assertEqual(record["session_id"], SESSION)

    def test_wrong_session_is_refused(self):
        _, _, previous, _ = self.invoke()
        code, record, _, _ = self.invoke(case="wrong_session", extra=("--resume", str(previous)))
        self.assertEqual(code, 1)
        self.assertIn("different session", record["error"])

    def test_resume_wrong_provider_or_model_rejected_before_launch(self):
        _, _, previous, _ = self.invoke()
        code, record, _, error = self.invoke("codex", extra=("--resume", str(previous)))
        self.assertEqual(code, 1)
        self.assertIsNone(record)
        self.assertIn("provider", error)
        code, record, _, error = self.invoke(extra=("--resume", str(previous), "--model", "new-model"))
        self.assertEqual(code, 1)
        self.assertIsNone(record)
        self.assertIn("requested_model", error)

    def test_timeout_records_failure(self):
        code, record, _, _ = self.invoke(case="timeout", extra=("--timeout", "1"))
        self.assertEqual(code, 1)
        self.assertIn("timed out", record["error"])
        self.assertEqual(record["failure_kind"], "provider_unavailable")
        self.assertTrue(record["fallback_eligible"])

    def test_quota_failure_allows_honest_fresh_same_provider_review(self):
        code, failed, primary, _ = self.invoke("codex", case="quota")
        self.assertEqual(code, 1)
        self.assertEqual(failed["provider"], "claude")
        self.assertEqual(failed["failure_kind"], "provider_unavailable")
        self.assertTrue(failed["fallback_eligible"])

        code, record, path, _ = self.invoke(
            "codex", extra=("--provider", "codex", "--fallback-from", str(primary)))
        self.assertEqual(code, 0, record)
        self.assertEqual(record["provider"], "codex")
        self.assertEqual(record["assurance"], "degraded_same_provider")
        self.assertEqual(record["fallback_session_state"], "fresh")
        self.assertEqual(record["fallback_from"], str(primary.resolve()))
        self.assertIn("DEGRADED_SAME_PROVIDER", record["response"]["limitations"][-1])
        self.assertIn("DEGRADED SAME-PROVIDER FALLBACK", (path.parent / "prompt.txt").read_text())
        self.assertNotIn("resume", json.loads((path.parent / "command.json").read_text()))

    def test_fallback_reviewer_can_resume_after_plan_revision(self):
        _, _, primary, _ = self.invoke("codex", case="quota")
        extra = ("--provider", "codex", "--fallback-from", str(primary))
        code, record, fallback_result, _ = self.invoke("codex", case="revise", extra=extra)
        self.assertEqual(code, 0, record)
        self.plan.write_text("Revised after fallback findings", encoding="utf-8")
        code, record, _, _ = self.invoke(
            "codex", extra=extra + ("--resume", str(fallback_result)))
        self.assertEqual(code, 0, record)
        self.assertEqual(record["assurance"], "degraded_same_provider")
        self.assertEqual(record["session_id"], SESSION)
        self.assertEqual(record["fallback_session_state"], "resumed")
        self.assertIn("resumed its prior", record["response"]["limitations"][-1])

    def test_non_availability_failure_cannot_authorize_fallback(self):
        code, failed, primary, _ = self.invoke("codex", case="malformed")
        self.assertEqual(code, 1)
        self.assertFalse(failed["fallback_eligible"])
        code, record, _, error = self.invoke(
            "codex", extra=("--provider", "codex", "--fallback-from", str(primary)))
        self.assertEqual(code, 1)
        self.assertIsNone(record)
        self.assertIn("not eligible", error)

    def test_user_interruption_is_not_fallback_eligible(self):
        kind, eligible = runner.classify_failure(
            "Run was interrupted; no approval recorded.", self.root, "codex")
        self.assertEqual(kind, "provider_failure")
        self.assertFalse(eligible)

    def test_review_content_cannot_spoof_fallback_eligibility(self):
        self.root.joinpath("stdout.txt").write_text("quota exhausted", encoding="utf-8")
        kind, eligible = runner.classify_failure("Invalid review verdict.", self.root, "codex")
        self.assertEqual(kind, "provider_failure")
        self.assertFalse(eligible)

    def test_agent_message_cannot_spoof_failed_turn_eligibility(self):
        events = [
            {"type": "agent_message", "text": "The plan discusses a quota."},
            {"type": "turn.failed", "error": {"message": "repository read failed"}},
        ]
        self.root.joinpath("stdout.txt").write_text(
            "\n".join(json.dumps(event) for event in events), encoding="utf-8")
        kind, eligible = runner.classify_failure(
            "Codex reported a failed turn; inspect the captured diagnostics.",
            self.root, "codex")
        self.assertEqual(kind, "provider_failure")
        self.assertFalse(eligible)

    def test_structured_quota_failure_is_fallback_eligible(self):
        event = {"type": "turn.failed", "error": {"message": "usage limit reached"}}
        self.root.joinpath("stdout.txt").write_text(json.dumps(event), encoding="utf-8")
        kind, eligible = runner.classify_failure(
            "Codex reported a failed turn; inspect the captured diagnostics.",
            self.root, "codex")
        self.assertEqual(kind, "provider_unavailable")
        self.assertTrue(eligible)

    def test_claude_structured_429_is_fallback_eligible(self):
        code, failed, primary, _ = self.invoke("codex", case="claude_429")
        self.assertEqual(code, 1)
        self.assertEqual(failed["failure_kind"], "provider_unavailable")
        self.assertTrue(failed["fallback_eligible"])
        code, record, _, _ = self.invoke(
            "codex", extra=("--provider", "codex", "--fallback-from", str(primary)))
        self.assertEqual(code, 0, record)
        self.assertEqual(record["assurance"], "degraded_same_provider")

    def test_claude_result_text_cannot_spoof_fallback_eligibility(self):
        for case in ("claude_result_spoof", "claude_400"):
            with self.subTest(case=case):
                code, failed, _, _ = self.invoke("codex", case=case)
                self.assertEqual(code, 1)
                self.assertEqual(failed["failure_kind"], "provider_failure")
                self.assertFalse(failed["fallback_eligible"])

    def test_claude_api_status_policy(self):
        base = {"type": "result", "subtype": "success", "is_error": True,
                "terminal_reason": "api_error", "result": "model text"}
        for status, expected in ((429, True), (401, True), (500, True), (520, True), (599, True),
                                 (400, False), (403, False), (600, False), ("429", False),
                                 (True, False), ([429], False), ({"code": 429}, False)):
            with self.subTest(status=status):
                self.root.joinpath("stdout.txt").write_text(
                    json.dumps(dict(base, api_error_status=status)), encoding="utf-8")
                kind, eligible = runner.classify_failure(
                    "claude exited 1; inspect stdout.txt and stderr.txt.", self.root, "claude")
                self.assertEqual(eligible, expected)
                self.assertEqual(kind, "provider_unavailable" if expected else "provider_failure")

    def test_quota_failure_allows_fresh_same_provider_inspection(self):
        extra = ("--base", self.base, "--builder", "codex")
        code, failed, primary, _ = self.invoke("codex", mode="inspect", case="quota", extra=extra)
        self.assertEqual(code, 1)
        self.assertEqual(failed["provider"], "claude")
        code, record, _, _ = self.invoke(
            "codex", mode="inspect",
            extra=extra + ("--provider", "codex", "--fallback-from", str(primary)))
        self.assertEqual(code, 0, record)
        self.assertEqual(record["assurance"], "degraded_same_provider")
        self.assertIsNone(record["previous"])

    def test_inspection_fallback_requires_the_failed_snapshot(self):
        extra = ("--base", self.base, "--builder", "codex")
        _, _, primary, _ = self.invoke("codex", mode="inspect", case="quota", extra=extra)
        self.repo.joinpath("after_failure.py").write_text("changed\n", encoding="utf-8")
        code, record, _, error = self.invoke(
            "codex", mode="inspect",
            extra=extra + ("--provider", "codex", "--fallback-from", str(primary)))
        self.assertEqual(code, 1)
        self.assertIsNone(record)
        self.assertIn("Code changed after", error)

    def test_build_preserves_degraded_approval_assurance(self):
        _, _, primary, _ = self.invoke("codex", case="quota")
        _, approval, approval_path, _ = self.invoke(
            "codex", extra=("--provider", "codex", "--fallback-from", str(primary)))
        self.assertEqual(approval["assurance"], "degraded_same_provider")
        code, record, _, _ = self.invoke(
            "codex", mode="build", case="build",
            extra=("--builder", "codex", "--approval", str(approval_path), "--proof", "test"))
        self.assertEqual(code, 0, record)
        self.assertEqual(record["approval_assurance"], "degraded_same_provider")

    def test_unique_artifacts_and_failed_round_does_not_reuse_reply(self):
        _, _, first, _ = self.invoke()
        code, record, second, _ = self.invoke(case="empty")
        self.assertNotEqual(first, second)
        self.assertEqual(code, 1)
        self.assertNotIn("response", record)

    def test_snapshot_covers_staged_unstaged_deleted_and_new_files(self):
        (self.repo / "existing.py").write_text("staged version\n")
        self.git("add", "existing.py")
        (self.repo / "existing.py").write_text("unstaged final version\n")
        (self.repo / "delete.py").unlink()
        (self.repo / "new.py").write_text("brand new\n")
        snap = runner.snapshot(self.repo, self.base)
        self.assertEqual({f["path"] for f in snap["files"]}, {"existing.py", "delete.py", "new.py"})
        self.assertEqual(next(f for f in snap["files"] if f["path"] == "delete.py")["kind"], "deleted")
        self.assertEqual(next(f for f in snap["files"] if f["path"] == "existing.py")["sha256"],
                         runner.digest((self.repo / "existing.py").read_bytes()))

    def test_staged_rename_lists_old_path_as_deleted(self):
        self.git("mv", "delete.py", "moved.py")
        files = {f["path"]: f["kind"] for f in runner.snapshot(self.repo, self.base)["files"]}
        self.assertEqual((files.get("delete.py"), files.get("moved.py")), ("deleted", "file"))

    def test_inspection_requires_other_provider_and_fresh_session(self):
        code, _, _, error = self.invoke(mode="inspect", extra=("--base", self.base, "--provider", "claude"))
        self.assertEqual(code, 1)
        self.assertIn("opposite the builder", error)
        _, _, previous, _ = self.invoke()
        code, _, _, error = self.invoke(mode="inspect", extra=("--base", self.base, "--resume", str(previous)))
        self.assertEqual(code, 1)
        self.assertIn("fresh session", error)

    def test_git_subdirectory_is_refused_as_repo(self):
        # Manifest paths are repository-root relative; a subfolder would misread them.
        sub = self.repo / "sub"
        sub.mkdir()
        code, _, _, error = self.invoke(mode="inspect",
                                        extra=("--base", self.base, "--repo", str(sub)))
        self.assertEqual(code, 1)
        self.assertIn("repository root", error)

    def test_changed_code_during_inspection_fails(self):
        (self.repo / "new.py").write_text("original new file")
        code, record, _, _ = self.invoke(mode="inspect", case="mutate_code", extra=("--base", self.base))
        self.assertEqual(code, 1)
        self.assertIn("Code changed", record["error"])

    def test_build_requires_explicit_review_override_and_clean_tree(self):
        code, _, _, error = self.invoke(mode="build", extra=("--proof", "python -m unittest"))
        self.assertEqual(code, 1)
        self.assertIn("--approval", error)
        (self.repo / "user_work.py").write_text("preserve me")
        code, _, _, error = self.invoke(mode="build", extra=("--unreviewed-spec", "--proof", "test"))
        self.assertEqual(code, 1)
        self.assertIn("clean checkout", error)
        self.assertEqual((self.repo / "user_work.py").read_text(), "preserve me")

    def test_build_rejects_provider_that_contradicts_builder_before_launch(self):
        with patch.object(runner, "execute", wraps=runner.execute) as launch:
            code, record, _, error = self.invoke(
                host="codex", mode="build", case="build",
                extra=("--builder", "codex", "--provider", "claude",
                       "--unreviewed-spec", "--proof", "python -m unittest"))
        self.assertEqual(code, 1, record)
        launch.assert_not_called()
        self.assertIsNone(record)
        self.assertIn("builder", error.lower())
        self.assertFalse((self.repo / "built.py").exists())

    def test_build_accepts_explicit_provider_matching_builder(self):
        code, record, _, _ = self.invoke(
            host="codex", mode="build", case="build",
            extra=("--builder", "codex", "--provider", "codex",
                   "--unreviewed-spec", "--proof", "python -m unittest"))
        self.assertEqual(code, 0, record)
        self.assertEqual(record["provider"], record["roles"]["builder"])
        self.assertTrue((self.repo / "built.py").exists())

    def test_build_dispatches_approved_snapshot_and_rejects_changed_live_plan(self):
        self.plan.write_bytes(b"# Work order\r\nKeep the original until the copy is verified.\r\n")
        approved_bytes = self.plan.read_bytes()
        approved_body = self.plan.read_text(encoding="utf-8")
        _, _, approval, _ = self.invoke(host="codex")
        real_check = runner.check_approval
        unapproved_body = "UNAPPROVED REPLACEMENT: delete the original before verification."

        def change_after_check(*args, **kwargs):
            result = real_check(*args, **kwargs)
            self.plan.write_text(unapproved_body, encoding="utf-8")
            return result

        with patch.object(runner, "check_approval", side_effect=change_after_check):
            code, record, path, _ = self.invoke(
                host="codex", mode="build", case="build",
                extra=("--approval", str(approval), "--proof", "python -m unittest"))
        self.assertIsNotNone(path, record)
        prompt = (path.parent / "prompt.txt").read_text(encoding="utf-8")
        prompt_bytes = (path.parent / "prompt.txt").read_bytes()
        self.assertIn(approved_bytes, prompt_bytes)
        self.assertNotIn(b"\r\r\n", prompt_bytes)
        self.assertNotIn(unapproved_body, prompt)
        self.assertIn(approved_body, prompt)
        self.assertEqual(record["plan_sha256"], runner.digest(approved_bytes))
        self.assertEqual(code, 1, record)
        self.assertEqual(record["status"], "failed")
        self.assertIn("Plan changed during the run", record["error"])
        self.assertTrue((self.repo / "built.py").exists())

    def test_missing_feedback_finalizes_created_run_as_failed(self):
        with patch.object(runner, "execute", wraps=runner.execute) as launch:
            code, record, _, _ = self.invoke(extra=("--feedback", str(self.root / "missing.txt")))
        self.assertEqual(code, 1)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "failed")
        self.assertTrue(record["error"])
        self.assertGreaterEqual(record["elapsed_seconds"], 0)
        launch.assert_not_called()

    def test_invalid_utf8_feedback_finalizes_created_run_as_failed(self):
        feedback = self.root / "feedback.txt"
        feedback.write_bytes(b"Invalid UTF-8: \xff")
        with patch.object(runner, "execute", wraps=runner.execute) as launch:
            code, record, _, _ = self.invoke(extra=("--feedback", str(feedback)))
        self.assertEqual(code, 1)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "failed")
        self.assertTrue(record["error"])
        launch.assert_not_called()

    def test_invalid_utf8_plan_finalizes_created_run_as_failed(self):
        self.plan.write_bytes(b"Invalid UTF-8: \xff")
        with patch.object(runner, "execute", wraps=runner.execute) as launch:
            code, record, _, _ = self.invoke()
        self.assertEqual(code, 1)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "failed")
        self.assertTrue(record["error"])
        launch.assert_not_called()

    def test_completed_round_exits_0_when_stdout_cannot_encode_the_record(self):
        # Issue #31: a reply character outside the console code page turned a saved,
        # completed round into exit 1. U+2192 is outside cp1252 (an em dash is not).
        out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        with patch.object(runner, "cli_prefix", return_value=[sys.executable, str(self.cli)]), \
             patch.dict(os.environ, {"FAKE_CASE": "arrow", "FAKE_PLAN": str(self.plan)}), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = runner.main(["review", "--host", "codex", "--repo", str(self.repo), "--plan",
                                str(self.plan), "--artifacts", str(self.artifacts)])
        record = json.loads(next(self.artifacts.glob("*/result.json")).read_text(encoding="utf-8"))
        self.assertEqual((code, record["status"]), (0, "completed"))

    def test_build_resume_keeps_initial_baseline_and_existing_build_changes(self):
        extra = ("--builder", "codex", "--unreviewed-spec", "--proof", "python -m unittest")
        code, record, path, _ = self.invoke(mode="build", case="build", extra=extra)
        self.assertEqual(code, 0, record)
        self.assertEqual(record["base"], self.base)
        code, record, _, _ = self.invoke(mode="build", case="build", extra=extra+("--resume", str(path)))
        self.assertEqual(code, 0, record)
        self.assertEqual(record["base"], self.base)
        (self.repo / "user_work.py").write_text("intervening edit")
        code, _, _, error = self.invoke(mode="build", case="build", extra=extra+("--resume", str(path)))
        self.assertEqual(code, 1)
        self.assertIn("Checkout changed", error)

    def test_artifacts_cannot_contaminate_target_checkout(self):
        code, _, _, error = self.invoke(extra=("--artifacts", str(self.repo / "runs")))
        self.assertEqual(code, 1)
        self.assertIn("outside", error)


def stream(session, calls, response, model="claude-test"):
    """Claude stream-json in the shape observed from Claude Code 2.1.280."""
    events = [{"type": "system", "subtype": "init", "model": model}]
    for index, (name, tool_input, ok, text, structured) in enumerate(calls):
        tool_id = f"toolu_{index}"
        events.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}]}})
        result = {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": tool_id, "content": text,
             "is_error": None if ok else True}]}}
        if structured is not None:
            result["tool_use_result"] = structured
        events.append(result)
    # Claude Code 2.1.280 delivers --json-schema output through an internal tool call.
    events.append({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "toolu_final", "name": "StructuredOutput", "input": response}]}})
    events.append({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "toolu_final", "content": "Structured output provided successfully"}]}})
    events.append({"type": "result", "subtype": "success", "is_error": False, "session_id": session,
                   "structured_output": response, "modelUsage": {model: {}}, "usage": {"input_tokens": 1}})
    return "\n".join(json.dumps(event) for event in events) + "\n"


def codex_stream(thread, searches, value, extra_items=()):
    """Codex JSONL in the shape observed from Codex CLI 0.155.1 with web_search="live"."""
    events = [{"type": "thread.started", "thread_id": thread}, {"type": "turn.started"}]
    for index, (query, results) in enumerate(searches):
        events.append({"type": "item.completed", "item": {
            "id": f"ws{index}", "type": "web_search", "query": query, "action": {"type": "search", "query": query},
            "results": [{"type": "text_result", "url": u, "title": title, "snippet": snippet}
                        for u, title, snippet in results]}})
    events += [{"type": "item.completed", "item": item} for item in extra_items]
    events.append({"type": "item.completed", "item": {"id": "final", "type": "agent_message",
                                                       "text": json.dumps(value)}})
    events.append({"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 2}})
    return "\n".join(json.dumps(event) for event in events) + "\n"


def fetch(url, body, ok=True):
    return ("WebFetch", {"url": url, "prompt": "quote it"}, ok, body, {"url": url, "code": 200, "result": body})


def search(*urls):
    return ("WebSearch", {"query": "q"}, True, "Links: " + json.dumps([{"url": u} for u in urls]), None)


def read(path, content, ok=True):
    return ("Read", {"file_path": str(path)}, ok, "1\t" + content,
            {"type": "text", "file": {"filePath": str(path), "content": content}} if ok else None)


def claim(locator, excerpt, kind="web", question="q1", claim_id="c1"):
    return {"id": claim_id, "question_id": question, "claim": "A supported statement.", "source_type": kind,
            "locator": locator, "excerpt": excerpt, "confidence": "high", "limitation": ""}


def response(*claims):
    return {"summary": "Researched the assigned question.", "claims": list(claims),
            "coverage": ["assigned angle"], "limitations": []}


class PanelTests(unittest.TestCase):
    SESSIONS = {"w1": "11111111-1111-4111-8111-111111111111",
                "w2": "22222222-2222-4222-8222-222222222222",
                "w3": "33333333-3333-4333-8333-333333333333"}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="claudex-panel-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / "existing.py").write_text("original value\n")
        self.plan = self.root / "plan.md"
        self.plan.write_text("# Plan\nSECRET-PLAN-BODY keep the original.\n", encoding="utf-8")
        self.artifacts = self.root / "runs"
        self.fake = self.root / "fake-panel"
        self.fake.mkdir()
        self.cli = self.root / "fake_cli.py"
        self.cli.write_text(FAKE_CLI)
        self.spec = {"questions": [{"id": "q1", "text": "Is alpha stable?"}],
                     "workers": [{"id": "w1", "kind": "web", "angle": "official docs", "question_ids": ["q1"]},
                                 {"id": "w2", "kind": "web", "angle": "community", "question_ids": ["q1"]},
                                 {"id": "w3", "kind": "repo", "angle": "code", "question_ids": ["q1"]}],
                     "wall_clock_seconds": 60}
        self.script("w1", [fetch("https://a.example/doc", "Alpha is stable since 2026.")],
                    response(claim("https://a.example/doc/", "alpha is  STABLE")))
        self.script("w2", [search("https://b.example/x"), fetch("https://b.example/y", "Beta says alpha works.")],
                    response(claim("https://b.example/y", "alpha works")))
        self.script("w3", [read(self.repo / "existing.py", "original value\n")],
                    response(claim("existing.py:1", "original value", "repo")))

    def script(self, worker, calls, value):
        (self.fake / f"{worker}.jsonl").write_text(stream(self.SESSIONS[worker], calls, value))

    def call(self, *args, validated=True, env=None, host="codex"):
        output, error = io.StringIO(), io.StringIO()
        variables = {"FAKE_PANEL_DIR": str(self.fake), **(env or {})}
        with patch.object(runner, "cli_prefix", return_value=[sys.executable, str(self.cli)]), \
             patch.object(runner, "VALIDATED_READ_CONFINEMENT_CLI", ("fake-cli",) if validated else ()), \
             patch.object(runner, "VALIDATED_CODEX_WEB_PANEL_CLI", ("1.0",) if validated else ()), \
             patch.dict(os.environ, variables), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = runner.main(["panel", "--host", host, "--repo", str(self.repo), "--plan", str(self.plan),
                                "--artifacts", str(self.artifacts), *args])
        return code, output.getvalue(), error.getvalue()

    def dry_run(self, spec=None, host="codex"):
        path = self.root / "panel.json"
        path.write_text(json.dumps(spec or self.spec))
        code, out, error = self.call("--spec", str(path), "--dry-run", host=host)
        return code, (json.loads(out) if code == 0 else None), error

    def launch(self, spec=None, extra=(), host="codex", **kwargs):
        code, dry, error = self.dry_run(spec, host)
        self.assertEqual(code, 0, error)
        old = set(self.artifacts.glob("claudex-*/result.json")) if self.artifacts.exists() else set()
        code, _, error = self.call("--spec", str(self.root / "panel.json"),
                                   "--payload-sha256", dry["payload_sha256"], *extra, host=host, **kwargs)
        new = set(self.artifacts.glob("claudex-*/result.json")) - old if self.artifacts.exists() else set()
        self.assertLessEqual(len(new), 1)
        record = json.loads(next(iter(new)).read_text()) if new else None
        return code, record, dry, error

    def test_dry_run_shows_exact_web_payload_without_repository_material(self):
        code, dry, _ = self.dry_run()
        self.assertEqual(code, 0)
        self.assertEqual((dry["launches"], dry["concurrency"]), (3, 2))
        self.assertEqual(set(dry["web_worker_prompts"]), {"w1", "w2"})
        for prompt in dry["web_worker_prompts"].values():
            self.assertNotIn("SECRET-PLAN-BODY", prompt)
            self.assertNotIn(str(self.repo), prompt)
        self.assertEqual(dry["repo_workers"][0]["id"], "w3")
        self.assertFalse(self.artifacts.exists())

    def test_panel_default_workers_are_independent_of_reviewer_and_inspector(self):
        code, record, _, error = self.launch(extra=("--reviewer", "deepseek", "--inspector", "deepseek"))
        self.assertEqual(code, 0, error)
        self.assertEqual(record["provider"], "claude")
        self.assertEqual({w["provider"] for w in record["workers"]}, {"claude"})
        self.assertEqual(record["roles"]["reviewer"], "deepseek")

    def test_deepseek_host_defaults_to_claude_panel_workers(self):
        code, record, _, error = self.launch(host="deepseek")
        self.assertEqual(code, 0, (record, error))
        self.assertEqual(record["provider"], "claude")
        self.assertEqual({w["provider"] for w in record["workers"]}, {"claude"})
        self.assertEqual(record["roles"]["host"], "deepseek")

    def test_launch_requires_matching_payload_digest(self):
        path = self.root / "panel.json"
        path.write_text(json.dumps(self.spec))
        for extra in ((), ("--payload-sha256", "0" * 64)):
            code, _, error = self.call("--spec", str(path), *extra)
            self.assertEqual(code, 1)
            self.assertIn("payload-sha256", error)
        _, dry, _ = self.dry_run()
        self.plan.write_text("# Plan\nChanged after approval.\n", encoding="utf-8")
        code, _, error = self.call("--spec", str(path), "--payload-sha256", dry["payload_sha256"])
        self.assertEqual(code, 1)
        self.assertIn("does not match", error)

    def test_completed_panel_binds_workers_sessions_and_evidence(self):
        code, record, dry, error = self.launch()
        self.assertEqual(code, 0, (record, error))
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["assurance"], "cross_provider_panel")
        self.assertEqual({w["session_id"] for w in record["workers"]}, set(self.SESSIONS.values()))
        self.assertEqual(len({w["artifacts"] for w in record["workers"]}), 3)
        self.assertEqual(record["coverage"], {"q1": {"w1": 1, "w2": 1, "w3": 1}})
        for worker in ("w1", "w2", "w3"):
            argv = json.loads((self.fake / f"{worker}.argv.json").read_text())
            self.assertIn("--restricted", argv)
            self.assertNotIn("--resume", argv)
            self.assertEqual(argv[argv.index("--tools") + 1],
                             "Read,Glob,Grep" if worker == "w3" else "WebSearch,WebFetch")
        for worker in ("w1", "w2"):
            stdin = (self.fake / f"{worker}.stdin.txt").read_text(encoding="utf-8")
            self.assertEqual(stdin, dry["web_worker_prompts"][worker])
            cwd = Path((self.fake / f"{worker}.cwd.txt").read_text()).resolve()
            self.assertTrue(cwd.is_relative_to(self.artifacts.resolve()))
        self.assertEqual(Path((self.fake / "w3.cwd.txt").read_text()).resolve(), self.repo)
        self.assertIn("SECRET-PLAN-BODY", (self.fake / "w3.stdin.txt").read_text(encoding="utf-8"))
        panel = json.loads(Path(record["panel"]).read_text())
        self.assertTrue(panel["untrusted_content"])
        self.assertEqual({c["status"] for c in panel["claims"]}, {"retrieved"})
        with self.assertRaises(runner.RunError):
            runner.check_approval(record, self.plan, self.repo)

    def test_web_citation_statuses(self):
        calls = runner.parse_panel_stream(stream(self.SESSIONS["w1"], [
            fetch("https://a.example/doc", "Alpha is stable."), fetch("https://c.example/", "Gamma text."),
            search("https://s.example/only-searched"),
            fetch("https://d.example/denied", "Hidden text.", ok=False)], response()))["calls"]
        cases = [(claim("https://a.example/doc", "alpha is stable"), "retrieved"),
                 (claim("https://a.example/doc", "not on the page"), "unverified"),
                 (claim("https://s.example/only-searched", "anything"), "unverified"),
                 (claim("https://a.example/doc", "gamma text"), "unverified"),
                 (claim("https://never.example/", "alpha is stable"), "mismatch"),
                 (claim("https://d.example/denied", "hidden text"), "mismatch")]
        statuses = runner.verify_claims([c for c, _ in cases], calls, "web", self.repo)
        self.assertEqual(statuses, [expected for _, expected in cases])

    def test_web_excerpts_match_rendered_markdown(self):
        body = ('## Deprecation\n\n**Deprecated since version 3.12:**\n> Use [`datetime.now()`](#datetime.now '
                '"datetime.now") with [`UTC`](#UTC) instead.')
        calls = runner.parse_panel_stream(stream(self.SESSIONS["w1"], [fetch("https://docs.example/dt", body)],
                                                 response()))["calls"]
        claims = [claim("https://docs.example/dt", "Deprecated since version 3.12: Use datetime.now() with UTC instead."),
                  claim("https://docs.example/dt", "removed in Python 3.14", claim_id="c2")]
        self.assertEqual(runner.verify_claims(claims, calls, "web", self.repo), ["retrieved", "unverified"])

    def test_repo_citation_statuses_use_what_the_worker_read(self):
        (self.repo / "docs").mkdir()
        calls = runner.parse_panel_stream(stream(self.SESSIONS["w3"], [
            read(self.repo / "existing.py", "original value\n"),
            ("Grep", {"pattern": "value"}, True, "docs/grepped.md:3:some value", None)], response()))["calls"]
        (self.repo / "existing.py").write_text("edited after the worker read it\n")
        cases = [(claim("existing.py:1", "original value", "repo"), "retrieved"),
                 (claim("existing.py", "edited after", "repo"), "unverified"),
                 (claim("docs/grepped.md:3", "some value", "repo"), "retrieved"),
                 (claim("docs/grepped.md", "not in the grep line", "repo"), "unverified"),
                 (claim("never_read.py", "original value", "repo"), "mismatch"),
                 (claim("../outside.py", "original value", "repo"), "mismatch"),
                 (claim(str(self.repo / "existing.py"), "original value", "repo"), "mismatch")]
        statuses = runner.verify_claims([c for c, _ in cases], calls, "repo", self.repo)
        self.assertEqual(statuses, [expected for _, expected in cases])

    def test_outside_read_that_succeeds_fails_the_run_without_panel_output(self):
        outside = self.root / "outside-secret.txt"
        self.script("w3", [read(outside, "FAKE-SECRET")], response(claim("existing.py", "x", "repo")))
        code, record, _, _ = self.launch()
        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "failed")
        self.assertNotIn("assurance", record)
        self.assertFalse((Path(record["artifacts"]) / "panel.json").exists())
        self.assertNotIn("FAKE-SECRET", json.dumps(record))

    def test_outside_read_counts_even_when_the_worker_then_crashes(self):
        outside = self.root / "outside-secret.txt"
        truncated = stream(self.SESSIONS["w3"], [read(outside, "FAKE-SECRET")], response())
        (self.fake / "w3.jsonl").write_text(truncated.rsplit("\n", 2)[0] + '\n{"type": "res')
        (self.fake / "w3.exit").write_text("1")
        code, record, _, _ = self.launch()
        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(next(w for w in record["workers"] if w["id"] == "w3")["status"], "confinement_violation")
        self.assertFalse((Path(record["artifacts"]) / "panel.json").exists())

    def test_launch_time_model_or_effort_change_invalidates_the_digest(self):
        path = self.root / "panel.json"
        path.write_text(json.dumps(self.spec))
        code, out, _ = self.call("--spec", str(path), "--dry-run")
        dry = json.loads(out)
        self.assertEqual((dry["model"], dry["effort"]), ("CLI default (unresolved)", "CLI default"))
        for extra in (("--model", "other-model"), ("--effort", "max")):
            code, _, error = self.call("--spec", str(path), "--payload-sha256", dry["payload_sha256"], *extra)
            self.assertEqual(code, 1)
            self.assertIn("does not match", error)

    def test_error_pages_and_unrelated_grep_hits_are_not_evidence(self):
        calls = runner.parse_panel_stream(stream(self.SESSIONS["w1"], [
            ("WebFetch", {"url": "https://e.example/"}, True, "Not Found: alpha is stable",
             {"url": "https://e.example/", "code": 404, "result": "Not Found: alpha is stable"})], response()))["calls"]
        self.assertEqual(runner.verify_claims([claim("https://e.example/", "alpha is stable")], calls, "web",
                                              self.repo), ["unverified"])
        calls = runner.parse_panel_stream(stream(self.SESSIONS["w3"], [
            ("Grep", {"pattern": "x"}, True, "src/foobar.py:3:x = 1", None)], response()))["calls"]
        claims = [claim("bar.py", "x = 1", "repo"), claim("src/foobar.py:3", "x = 1", "repo", claim_id="c2"),
                  claim("src/foobar.py", "y = 2", "repo", claim_id="c3")]
        self.assertEqual(runner.verify_claims(claims, calls, "repo", self.repo),
                         ["mismatch", "retrieved", "unverified"])
        calls = runner.parse_panel_stream(stream(self.SESSIONS["w3"], [
            ("Grep", {"pattern": "x", "output_mode": "files_with_matches"}, True, "Found 2 files\nsrc/foobar.py\nmy-2-file.py",
             None)], response()))["calls"]
        claims = [claim("src/foobar.py", "x = 1", "repo"), claim("my-2-file.py", "x", "repo", claim_id="c2")]
        self.assertEqual(runner.verify_claims(claims, calls, "repo", self.repo), ["unverified", "unverified"])

    def test_denied_outside_read_is_recorded_but_not_fatal(self):
        self.script("w3", [read(Path("/etc/hosts"), "", ok=False), read(self.repo / "existing.py", "original value\n")],
                    response(claim("existing.py", "original value", "repo")))
        code, record, _, _ = self.launch()
        self.assertEqual(code, 0, record)
        attempts = next(w for w in record["workers"] if w["id"] == "w3")["read_confinement_attempts"]
        self.assertEqual(attempts, [{"tool": "Read", "target": str(Path("/etc/hosts")), "succeeded": False}])

    def test_invalid_worker_responses_fail_that_worker_and_make_the_panel_partial(self):
        good = claim("https://b.example/y", "alpha works")
        bad_responses = [
            response(dict(good, excerpt="x" * 301)),
            response(dict(good, extra="field")),
            response(dict(good, question_id="q9")),
            response(dict(good, source_type="repo")),
            dict(response(good), summary="s" * 1001),
            dict(response(good), claims=[dict(good, id=f"c{i}") for i in range(21)]),
        ]
        for value in bad_responses:
            with self.subTest(value=str(value)[:80]):
                self.script("w2", [fetch("https://b.example/y", "Beta says alpha works.")], value)
                code, record, _, _ = self.launch()
                self.assertEqual(code, 1)
                self.assertEqual(record["status"], "partial")
                self.assertEqual(record["failed_workers"], ["w2"])
                self.assertNotIn("assurance", record)

    def test_under_covered_question_is_partial(self):
        self.script("w1", [fetch("https://a.example/doc", "Unrelated.")],
                    response(claim("https://a.example/doc", "alpha is stable")))
        (self.fake / "w3.exit").write_text("1")
        code, record, _, _ = self.launch()
        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "partial")
        self.assertEqual(record["under_covered"], ["q1"])
        panel = json.loads(Path(record["panel"]).read_text())
        self.assertEqual(panel["under_covered"], ["q1"])

    def test_mismatch_claims_are_excluded_and_worker_flagged(self):
        self.script("w2", [fetch("https://b.example/y", "Beta says alpha works.")],
                    response(claim("https://b.example/y", "alpha works"),
                             claim("https://invented.example/", "made up", claim_id="c2")))
        code, record, _, _ = self.launch()
        self.assertEqual(code, 0, record)
        panel = json.loads(Path(record["panel"]).read_text())
        self.assertEqual(panel["flagged_workers"], ["w2"])
        self.assertNotIn("https://invented.example/", json.dumps(panel["claims"]))
        self.assertTrue(all(c["worker_flagged"] for c in panel["claims"] if c["worker_id"] == "w2"))

    def test_spec_errors_are_refused_before_launch(self):
        worker = self.spec["workers"][0]
        broken = {
            "duplicate worker": dict(self.spec, workers=self.spec["workers"] + [worker]),
            "unknown question": dict(self.spec, workers=[dict(worker, question_ids=["q9"])] + self.spec["workers"][1:]),
            "one angle": dict(self.spec, workers=[dict(w, angle="same") for w in self.spec["workers"]]),
            "concurrency": dict(self.spec, concurrency=5),
            "wall clock": dict(self.spec, wall_clock_seconds=30),
            "unknown field": dict(self.spec, retries=2),
            "bad worker id": dict(self.spec, workers=[dict(worker, id="../w1")] + self.spec["workers"][1:]),
        }
        for name, spec in broken.items():
            with self.subTest(name):
                code, _, error = self.dry_run(spec)
                self.assertEqual(code, 1)
                self.assertTrue(error.strip())
        self.assertFalse(self.artifacts.exists())

    def test_cli_gates_restricted_mode_and_repo_canary(self):
        code, record, _, error = self.launch(env={"FAKE_NO_RESTRICTED": "1"})
        self.assertEqual(code, 1)
        self.assertIn("--restricted", error)
        code, _, _, error = self.launch(validated=False)
        self.assertEqual(code, 1)
        self.assertIn("canary", error)
        code, record, _, _ = self.launch(extra=("--allow-unvalidated-cli",), validated=False)
        self.assertEqual(code, 0, record)
        self.assertTrue(record["allow_unvalidated_cli"])
        self.assertFalse(record["cli_validated"])
        web_only = dict(self.spec, workers=self.spec["workers"][:2])
        code, record, _, _ = self.launch(web_only, validated=False)
        self.assertEqual(code, 0, record)

    def test_panel_roles_are_cross_provider_and_codex_repo_workers_refused(self):
        path = self.root / "panel.json"
        path.write_text(json.dumps(self.spec))
        code, _, error = self.call("--spec", str(path), "--dry-run", "--provider", "codex")
        self.assertEqual(code, 1)
        self.assertIn("opposite", error)
        code, _, error = self.call("--spec", str(path), "--dry-run", host="claude")
        self.assertEqual(code, 1)
        self.assertIn("Codex repo workers are refused", error)

    def assert_no_live_workers(self, workers):
        time.sleep(0.4)
        beats = {w: (self.fake / f"{w}.beat").stat().st_mtime for w in workers if (self.fake / f"{w}.beat").exists()}
        time.sleep(0.4)
        for worker, mtime in beats.items():
            self.assertEqual((self.fake / f"{worker}.beat").stat().st_mtime, mtime, f"{worker} still running")

    def test_stopped_before_launch_is_cancelled_without_starting_process(self):
        stop = threading.Event()
        stop.set()
        ctx = {"run_dir": self.artifacts, "provider": "claude", "harness": "claude-code",
               "model": None, "effort": None, "stop": stop, "deadline": time.monotonic() + 60}
        self.artifacts.mkdir()
        with patch.object(runner, "execute") as execute:
            record = runner.run_panel_worker(self.spec["workers"][0], "prompt", 1, ctx)
        self.assertEqual(record["status"], "cancelled")
        # A worker whose aggregate budget is already spent does not start either, even before the
        # coordinator has set the stop signal (another worker's own timeout freed the thread).
        late = dict(ctx, stop=threading.Event(), deadline=time.monotonic() - 0.01)
        with patch.object(runner, "execute") as execute_late:
            record_late = runner.run_panel_worker(self.spec["workers"][1], "prompt", 2, late)
        self.assertEqual(record_late["status"], "cancelled")
        execute_late.assert_not_called()
        self.assertEqual(record["error"], "Panel stopped before this worker launched.")
        self.assertEqual(json.loads((Path(record["artifacts"]) / "result.json").read_text()), record)
        execute.assert_not_called()
        self.assertFalse((Path(record["artifacts"]) / "command.json").exists())

    def test_aggregate_deadline_kills_workers_and_cancels_queue(self):
        for worker in self.SESSIONS:
            (self.fake / f"{worker}.sleep").write_text("30")
        started = time.monotonic()
        with patch.dict(runner.PANEL_LIMITS, {"wall_min": 1}):
            code, record, _, _ = self.launch(dict(self.spec, wall_clock_seconds=2))
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "failed")
        self.assertIn("wall-clock", record["error"])
        self.assertFalse((self.fake / "w3.argv.json").exists())
        self.assertEqual(next(w for w in record["workers"] if w["id"] == "w3")["status"], "cancelled")
        self.assert_no_live_workers(["w1", "w2"])

    def test_interrupt_in_coordinator_kills_every_worker(self):
        for worker in self.SESSIONS:
            (self.fake / f"{worker}.sleep").write_text("30")

        def interrupt_after_launch(pending, timeout):
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not all(
                    (self.fake / f"{w}.beat").exists() for w in ("w1", "w2")):
                time.sleep(0.05)
            raise KeyboardInterrupt

        started = time.monotonic()
        with patch.object(runner, "wait_workers", side_effect=interrupt_after_launch):
            code, record, _, _ = self.launch()
        self.assertLess(time.monotonic() - started, 20, "workers were not killed; shutdown waited for them")
        self.assertEqual(code, 1)
        self.assertEqual(record["error"], "Panel was interrupted.")
        self.assert_no_live_workers(["w1", "w2", "w3"])

    def test_interrupt_cancels_queued_workers_before_killing_running_worker(self):
        for worker in self.SESSIONS:
            (self.fake / f"{worker}.sleep").write_text("30")

        def interrupt_after_launch(pending, timeout):
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not (self.fake / "w1.beat").exists():
                time.sleep(0.05)
            self.assertTrue((self.fake / "w1.beat").exists())
            raise KeyboardInterrupt

        cancelled = []
        cancellations_at_kill = []
        original_cancel = runner.concurrent.futures.Future.cancel
        original_kill = runner.kill_tree

        def track_cancel(future):
            result = original_cancel(future)
            if result:
                cancelled.append(future)
            return result

        def track_kill(proc):
            cancellations_at_kill.append(len(cancelled))
            original_kill(proc)

        started = time.monotonic()
        with patch.object(runner, "wait_workers", side_effect=interrupt_after_launch), \
             patch.object(runner.concurrent.futures.Future, "cancel", track_cancel), \
             patch.object(runner, "kill_tree", side_effect=track_kill):
            code, record, _, _ = self.launch(dict(self.spec, concurrency=1))
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["error"], "Panel was interrupted.")
        self.assertTrue(cancellations_at_kill)
        self.assertTrue(all(count == 2 for count in cancellations_at_kill))
        statuses = {worker["id"]: worker["status"] for worker in record["workers"]}
        self.assertEqual([statuses[worker] for worker in ("w2", "w3")], ["cancelled", "cancelled"])
        for index, worker in enumerate(("w2", "w3"), 2):
            self.assertFalse((self.fake / f"{worker}.argv.json").exists())
            self.assertNotIn("artifacts", next(w for w in record["workers"] if w["id"] == worker))
            self.assertFalse(list(Path(record["artifacts"]).glob(f"w{index:02d}-*")))
        self.assert_no_live_workers(["w1"])

    def codex_web_spec(self):
        return dict(self.spec, workers=self.spec["workers"][:2])

    def codex_script(self, worker, searches, value, extra_items=()):
        (self.fake / f"{worker}.jsonl").write_text(codex_stream(self.SESSIONS[worker], searches, value, extra_items))

    def test_claude_host_runs_locked_down_codex_web_workers(self):
        self.codex_script("w1", [("alpha", [("https://a.example/doc", "Alpha docs", "Alpha is **stable** since 2026.")])],
                          response(claim("https://a.example/doc", "alpha is stable since 2026")))
        self.codex_script("w2", [("alpha", [("https://b.example/y", "Beta", "Beta says alpha works.")])],
                          response(claim("https://b.example/y", "alpha works")))
        code, record, dry, error = self.launch(self.codex_web_spec(), host="claude")
        self.assertEqual(code, 0, (record, error))
        self.assertEqual((record["provider"], record["harness"], record["status"]), ("codex", "codex-cli", "completed"))
        self.assertEqual(record["assurance"], "cross_provider_panel")
        self.assertEqual(record["disabled_features"], ["apps", "plugins", "shell_tool", "view_image"])
        argv = json.loads((self.fake / "w1.argv.json").read_text())
        for flag in ("--ignore-user-config", "--ephemeral", 'web_search="live"', "read-only", "--output-schema"):
            self.assertIn(flag, argv)
        self.assertNotIn("resume", argv)
        self.assertIn("web search only", dry["web_worker_prompts"]["w1"])
        self.assertNotIn("SECRET-PLAN-BODY", (self.fake / "w1.stdin.txt").read_text(encoding="utf-8"))

    def test_codex_citations_bind_to_the_result_snippet_for_that_url(self):
        calls = runner.parse_codex_panel_stream(codex_stream(self.SESSIONS["w1"], [
            ("q", [("https://a.example/", "A", "Alpha is stable."), ("https://b.example/", "B", "Beta text.")])],
            response()))["calls"]
        cases = [(claim("https://a.example/", "alpha is stable"), "retrieved"),
                 (claim("https://a.example", "alpha is stable"), "mismatch"),
                 (claim("https://a.example/", "beta text"), "unverified"),
                 (claim("https://never.example/", "alpha is stable"), "mismatch")]
        self.assertEqual(runner.verify_claims([c for c, _ in cases], calls, "web", self.repo, "codex"),
                         [expected for _, expected in cases])

    def test_any_codex_item_beyond_web_search_fails_the_run(self):
        self.codex_script("w1", [("alpha", [("https://a.example/doc", "A", "Alpha is stable.")])],
                          response(claim("https://a.example/doc", "alpha is stable")),
                          extra_items=[{"id": "e", "type": "error", "message": "provider notice"},
                                       {"id": "x", "type": "command_execution", "command": "cat ~/.ssh/id_rsa",
                                        "aggregated_output": "FAKE-KEY", "exit_code": 0, "status": "completed"}])
        self.codex_script("w2", [("alpha", [("https://b.example/y", "B", "Beta says alpha works.")])],
                          response(claim("https://b.example/y", "alpha works")))
        code, record, _, _ = self.launch(self.codex_web_spec(), host="claude")
        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "failed")
        self.assertFalse((Path(record["artifacts"]) / "panel.json").exists())
        self.assertNotIn("FAKE-KEY", json.dumps(record))

    def test_failed_or_merely_started_disallowed_codex_items_fail_the_run(self):
        good = response(claim("https://b.example/y", "alpha works"))
        searches = [("alpha", [("https://b.example/y", "B", "Beta says alpha works.")])]
        failed_exec = {"id": "x", "type": "command_execution", "command": "cat secret", "status": "failed"}
        self.codex_script("w1", searches, good, extra_items=[failed_exec])
        self.codex_script("w2", searches, good)
        code, record, _, _ = self.launch(self.codex_web_spec(), host="claude")
        self.assertEqual((code, record["status"]), (1, "failed"))
        # An otherwise successful stream whose only trace of the tool is an item.started event.
        lines = codex_stream(self.SESSIONS["w1"], searches, good).splitlines()
        lines.insert(2, json.dumps({"type": "item.started",
                                    "item": {"id": "y", "type": "mcp_tool_call", "status": "in_progress"}}))
        (self.fake / "w1.jsonl").write_text("\n".join(lines) + "\n")
        code, record, _, _ = self.launch(self.codex_web_spec(), host="claude")
        self.assertEqual((code, record["status"]), (1, "failed"))
        worker = next(w for w in record["workers"] if w["id"] == "w1")
        self.assertEqual(worker["status"], "confinement_violation")
        self.assertEqual(worker["read_confinement_attempts"][0]["tool"], "mcp_tool_call")
        self.assertFalse((Path(record["artifacts"]) / "panel.json").exists())

    def test_codex_panel_requires_core_features_in_the_probe(self):
        code, _, _, error = self.launch(self.codex_web_spec(), host="claude", env={"FAKE_FEATURES_DROP": "view_image"})
        self.assertEqual(code, 1)
        self.assertIn("view_image", error)

    def test_unvalidated_codex_cli_is_refused_without_override(self):
        code, _, _, error = self.launch(self.codex_web_spec(), host="claude", validated=False)
        self.assertEqual(code, 1)
        self.assertIn("live web-panel validation", error)


class AgyWindowsTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows-only refusal")
    def test_agy_is_refused_on_windows(self):
        for call in (lambda: runner.agy_profile("web"), runner.create_agy_profile):
            with self.assertRaisesRegex(runner.RunError, "refused on Windows"):
                call()


@unittest.skipIf(os.name == "nt", "agy is refused on Windows until its permission system is validated there")
class AgyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="claudex-agy-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.profile = self.home / ".claudex-loop" / "agy-web"
        self.review_profile = self.home / ".claudex-loop" / "agy-review"
        self.repo = self.root / "repo"
        self.repo.mkdir()
        for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"), ("config", "user.name", "T")):
            runner.git(self.repo, *args)
        (self.repo / "existing.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        (self.repo / "deleted.py").write_text("# old implementation\n", encoding="utf-8")
        runner.git(self.repo, "add", ".")
        runner.git(self.repo, "commit", "-qm", "baseline")
        self.base = runner.git(self.repo, "rev-parse", "HEAD").decode().strip()
        self.plan = self.root / "plan.md"
        self.plan.write_text("# Plan\nSecret plan detail.\n", encoding="utf-8")
        self.artifacts = self.root / "runs"
        self.fake = self.root / "fake"
        self.fake.mkdir()
        self.agy = self.root / "agy.py"
        self.agy.write_text(FAKE_AGY, encoding="utf-8")
        self.claude = self.root / "claude.py"
        self.claude.write_text(FAKE_CLI, encoding="utf-8")
        self.spec = {"questions": [{"id": "q1", "text": "Is the source verified?"}],
                     "workers": [{"id": "w1", "kind": "web", "provider": "agy",
                                  "angle": "official", "question_ids": ["q1"]},
                                 {"id": "w2", "kind": "web", "provider": "agy",
                                  "angle": "independent", "question_ids": ["q1"]}],
                     "wall_clock_seconds": 60}
        self.spec_path = self.root / "spec.json"
        self.spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
        with patch.dict(os.environ, {"HOME": str(self.home)}), \
             patch.object(runner.tempfile, "gettempdir", return_value=str(self.root)), \
             contextlib.redirect_stdout(io.StringIO()):
            runner.create_agy_profile()

    def call(self, mode="panel", case="ok", extra=(), host="codex", provider="agy"):
        output, error = io.StringIO(), io.StringIO()
        def prefix(name, override=None):
            return [sys.executable, str(self.agy if name == "agy" else self.claude)]
        args = [mode, "--host", host, "--repo", str(self.repo), "--plan", str(self.plan),
                "--artifacts", str(self.artifacts), *extra]
        if mode == "panel":
            args += ["--spec", str(self.spec_path)]
        elif mode in ("review", "inspect") and provider:
            args += ["--provider", provider]
        if mode == "inspect":
            args += ["--base", self.base]
        old = set(self.artifacts.glob("*/result.json")) if self.artifacts.exists() else set()
        with patch.object(runner, "cli_prefix", side_effect=prefix), \
             patch.dict(os.environ, {"HOME": str(self.home), "FAKE_AGY_CASE": case,
                                    "FAKE_AGY_DIR": str(self.fake), "FAKE_PANEL_DIR": str(self.fake)}), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = runner.main(args)
        new = set(self.artifacts.glob("*/result.json")) - old if self.artifacts.exists() else set()
        record = json.loads(next(iter(new)).read_text()) if new else None
        return code, record, output.getvalue(), error.getvalue()

    def panel(self, case="ok", extra=()):
        code, _, output, error = self.call(case=case, extra=("--dry-run", *extra))
        self.assertEqual(code, 0, error)
        payload = json.loads(output)["payload_sha256"]
        return self.call(case=case, extra=("--payload-sha256", payload, *extra))

    def script_live_shape(self, worker, tools, value):
        """Trimmed agy 1.2.9 stream/transcript shape from the 2026-09-23 live canary."""
        session = (PanelTests.SESSIONS[worker] if worker != "review" else
                   "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        stream_rows = [{"event": "init", "conversation_id": session,
                        "init": {"model": runner.AGY_MODEL, "permission_mode": "request-review"}}]
        transcript_rows = [{"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT"}]
        for index, (name, args, status, content) in enumerate(tools, 1):
            step = 2 * index
            for state in ("ACTIVE", status):
                stream_rows.append({"event": "step_update", "step_update": {
                    "conversation_id": session, "step_index": step, "step_type": "tool",
                    "state": state, "tool_name": name,
                    "tool_info": {"name": name, "parameters": args}}})
            transcript_rows += [
                {"step_index": step - 1, "source": "MODEL", "type": "PLANNER_RESPONSE",
                 "tool_calls": [{"name": name, "args": args}]},
                {"step_index": step, "source": "MODEL", "type": "GENERIC",
                 "status": status, "content": content},
            ]
        finish_step = 2 * len(tools) + 1
        transcript_rows += [
            {"step_index": finish_step, "source": "MODEL", "type": "PLANNER_RESPONSE",
             "tool_calls": [{"name": "finish", "args": {"answer": json.dumps(value)}}]},
            {"step_index": finish_step + 1, "source": "MODEL", "type": "GENERIC",
             "status": "DONE", "content": "Task is complete."},
        ]
        stream_rows.append({"event": "result", "result": {"conversation_id": session,
                            "status": "SUCCESS", "response": json.dumps(value),
                            "structured_output": value, "usage": {"input_tokens": 3}}})
        (self.fake / f"{worker}.stream.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in stream_rows), encoding="utf-8")
        (self.fake / f"{worker}.transcript.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in transcript_rows), encoding="utf-8")

    def test_profile_and_panel_transport_citations_cleanup(self):
        code, record, _, error = self.panel()
        self.assertEqual(code, 0, (record, error))
        self.assertEqual(record["assurance"], "cross_provider_panel")
        self.assertEqual({w["provider"] for w in record["workers"]}, {"agy"})
        self.assertEqual(record["coverage"]["q1"], {"w1": 1, "w2": 1})
        self.assertTrue(all(w["conversation_id"] == w["session_id"] and
                            w["permission_mode"] == "request-review" for w in record["workers"]))
        for worker in ("w1", "w2"):
            argv = json.loads((self.fake / (worker + ".argv.json")).read_text())
            self.assertEqual(argv[1:5], ["--input-format", "stream-json", "--output-format", "stream-json"])
            self.assertTrue(all(x not in argv for x in ("--agent", "--mode", "--continue", "--sandbox",
                                                          "--add-dir", "--dangerously-skip-permissions")))
            self.assertNotIn("WORKER ID", json.dumps(argv))
            self.assertEqual(Path((self.fake / (worker + ".home.txt")).read_text()), self.profile)
            self.assertNotEqual(Path((self.fake / (worker + ".cwd.txt")).read_text()), self.repo)
            self.assertTrue((self.fake / (worker + ".stdin.json")).exists())
            child = next(self.artifacts.glob(f"*/w*-{worker}"))
            self.assertTrue((child / "transcript_full.jsonl").exists())
            session = PanelTests.SESSIONS[worker]
            self.assertFalse((self.profile / ".gemini/antigravity-cli/brain" / session).exists())
            root = self.profile / ".gemini/antigravity-cli"
            self.assertFalse((root / "conversations" / (session + ".db")).exists())
            with sqlite3.connect(root / "conversation_summaries.db") as db:
                self.assertIsNone(db.execute("SELECT 1 FROM conversation_summaries WHERE conversation_id = ?",
                                             (session,)).fetchone())
        self.assertIn("gemini-3.1-pro-high", json.dumps(record["worker_settings"]))

    def test_agy_denial_api_error_hostile_tool_and_missing_transcript_fail_closed(self):
        for case in ("denied", "api_error", "hostile_tool", "missing_transcript", "stream_disagree"):
            with self.subTest(case=case):
                code, record, _, _ = self.panel(case)
                self.assertEqual(code, 1)
                if case in ("hostile_tool", "missing_transcript", "stream_disagree"):
                    self.assertEqual(record["status"], "failed")
                    self.assertFalse((Path(record["artifacts"]) / "panel.json").exists())
                else:
                    self.assertEqual(record["status"], "partial")

    def test_agy_preflight_failures_and_model_policy(self):
        for case in ("mcp", "plugin", "auth", "version", "quota"):
            with self.subTest(case=case):
                code, record, _, error = self.panel(case)
                self.assertEqual(code, 1)
                self.assertIsNone(record)
                self.assertIn("agy", error)
        code, record, _, error = self.call(extra=("--dry-run", "--agy-model", "claude-test"))
        self.assertEqual(code, 1)
        self.assertIn("gemini-", error)
        settings = self.profile / ".gemini/antigravity-cli/settings.json"
        settings.write_text("{}", encoding="utf-8")
        code, record, _, error = self.panel()
        self.assertEqual(code, 1)
        self.assertIn("settings", error)

    def test_profile_customization_and_permissions_fail_preflight(self):
        profile = self.profile
        hooks = profile / ".gemini/config/hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_text("{}", encoding="utf-8")
        code, record, _, error = self.panel()
        self.assertEqual(code, 1)
        self.assertIsNone(record)
        self.assertIn("forbidden customization", error)
        hooks.unlink()
        profile.chmod(0o755)
        code, record, _, error = self.panel()
        self.assertEqual(code, 1)
        self.assertIn("mode 0700", error)

    def test_profile_mcp_config_and_workspace_ancestor_refuse_launch(self):
        config = self.profile / ".gemini/config/mcp_config.json"
        config.parent.mkdir(parents=True)
        config.write_text('{"mcpServers":{"unsafe":{}}}', encoding="utf-8")
        code, record, _, error = self.panel()
        self.assertEqual(code, 1)
        self.assertIsNone(record)
        self.assertIn("MCP servers", error)
        config.unlink()
        (self.root / ".agents").mkdir()
        code, record, _, _ = self.panel()
        self.assertEqual(code, 1)
        self.assertTrue(all(w["status"] == "failed" for w in record["workers"]))
        self.assertFalse((self.fake / "w1.argv.json").exists())

    def test_realistic_logged_in_profile_passes_and_customizations_fail(self):
        cli_root = self.profile / ".gemini/antigravity-cli"
        log = cli_root / "log/cli-20260923.log"
        log.parent.mkdir(parents=True)
        log.write_text("", encoding="utf-8")
        (cli_root / "cli.log").symlink_to("log/cli-20260923.log")
        skill = cli_root / "builtin/skills/x/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("bundled skill", encoding="utf-8")
        config = self.profile / ".gemini/config"
        config.mkdir()
        mcp = config / "mcp_config.json"
        mcp.write_text("", encoding="utf-8")
        runner.agy_profile_check(self.profile, "web")
        mcp.write_text(" \n\t", encoding="utf-8")
        code, record, _, error = self.panel()
        self.assertEqual(code, 0, (record, error))
        for path in (config / "hooks.json", config / "skills" / "x", cli_root / "plugins" / "x",
                     self.profile / "AGENTS.md"):
            with self.subTest(path=path):
                created = not path.parent.exists()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("customization", encoding="utf-8")
                code, record, _, error = self.panel()
                self.assertEqual(code, 1)
                self.assertIsNone(record)
                self.assertIn("agy", error)
                path.unlink()
                if created:  # a leftover skills/ or plugins/ dir would mask the next check
                    shutil.rmtree(path.parent)
        mcp.write_text('{"mcpServers":{"unsafe":{}}}', encoding="utf-8")
        code, record, _, error = self.panel()
        self.assertEqual(code, 1)
        self.assertIsNone(record)
        self.assertIn("MCP servers", error)

    def test_multi_call_transcript_never_binds_first_result_to_second_url(self):
        session = PanelTests.SESSIONS["w1"]
        path = runner.agy_transcript_path(self.profile, session)
        path.parent.mkdir(parents=True)
        url_a, url_b = "https://example.org/a", "https://example.org/b"
        rows = [{"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE",
                 "tool_calls": [{"name": "read_url_content", "args": {"Url": url_a}},
                                {"name": "read_url_content", "args": {"Url": url_b}}]},
                {"step_index": 2, "source": "MODEL", "type": "GENERIC",
                 "status": "DONE", "content": "Only A contains this excerpt."}]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        calls = runner.agy_transcript(self.profile, session)
        self.assertEqual([call["name"] for call in calls], ["read_url_content", "read_url_content"])
        self.assertEqual(runner.verify_claims([claim(url_b, "Only A contains this excerpt"),
                                               claim(url_b, "**", claim_id="c2")],
                                              calls, "web", self.repo, "agy"),
                         ["unverified", "unverified"])
        rows[0]["tool_calls"] = rows[0]["tool_calls"][:1]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        self.assertEqual(runner.verify_claims([claim(url_a, "Only A contains this excerpt")],
                                              runner.agy_transcript(self.profile, session),
                                              "web", self.repo, "agy"), ["retrieved"])
        path.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(runner.RunError, "no tool result"):
            runner.agy_transcript(self.profile, session)

    def test_agy_effort_choices_reject_xhigh_and_max(self):
        for effort in ("xhigh", "max"):
            with self.subTest(effort=effort), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    runner.main(["panel", "--agy-effort", effort])
                with self.assertRaises(runner.RunError):
                    runner.agy_command("panel", self.root, runner.AGY_MODEL, effort, None, 60)

    def test_usage_probe_allows_network_timeout(self):
        calls = []
        def probe(prefix, flags, cwd, profile, timeout=10):
            calls.append((flags, timeout))
            return {"--version": "1.2.9", "mcp": "No MCP servers configured.",
                    "plugin": "No imported plugins.", "-p": "Gemini remaining quota: 100%"}[flags[0]]
        with patch.object(runner, "agy_probe", side_effect=probe):
            self.assertEqual(runner.agy_preflight(["agy"], self.profile, self.root, False, "web"), ("1.2.9", True))
        self.assertIn((["-p", "/usage"], 30), calls)

    def test_agy_schema_carries_lengths_and_prompt_asks_for_brevity(self):
        schema, limits = runner.AGY_PANEL_SCHEMA, runner.PANEL_LIMITS
        self.assertEqual(schema["properties"]["summary"]["maxLength"], limits["summary"])
        self.assertEqual(schema["properties"]["claims"]["maxItems"], limits["claims"])
        claim = schema["properties"]["claims"]["items"]["properties"]
        self.assertEqual(claim["excerpt"]["maxLength"], limits["excerpt"])
        self.assertEqual(claim["confidence"]["enum"], ["high", "medium", "low"])
        self.assertEqual(schema["required"], runner.PANEL_SCHEMA["required"])
        self.assertNotIn("maxLength", runner.PANEL_SCHEMA["properties"]["summary"])
        worker = {"id": "w", "kind": "web", "angle": "docs", "question_ids": ["q1"]}
        spec = {"questions": [{"id": "q1", "text": "Q?"}]}
        prompt = runner.panel_prompt(spec, worker, self.root, "", "agy")
        self.assertIn("summary at most 600 characters", prompt)
        self.assertNotIn("BE BRIEF", runner.panel_prompt(spec, worker, self.root, "", "codex"))

    def test_preflight_accepts_both_empty_plugin_messages_only(self):
        for listing, ok in (("No imported plugins.", True), ("No plugins installed.", True),
                            ("Plugin configured", False)):
            answers = {"--version": "1.2.9", "mcp": "No MCP servers configured.",
                       "plugin": listing, "-p": "Gemini remaining quota: 100%"}
            with self.subTest(listing=listing), \
                    patch.object(runner, "agy_probe", side_effect=lambda p, f, c, pr, timeout=10: answers[f[0]]):
                if ok:
                    runner.agy_preflight(["agy"], self.profile, self.root, False, "web")
                else:
                    with self.assertRaises(runner.RunError):
                        runner.agy_preflight(["agy"], self.profile, self.root, False, "web")

    def test_review_uses_single_version_probe(self):
        code, record, _, error = self.call(mode="review", case="version_drift")
        self.assertEqual(code, 0, (record, error))
        self.assertEqual((self.fake / "version.count").read_text(), "1")

    def test_worker_rechecks_cli_version_after_preflight(self):
        code, record, _, _ = self.panel("version_drift")
        self.assertEqual(code, 1)
        self.assertTrue(all(w["status"] == "failed" for w in record["workers"]))
        self.assertFalse((self.fake / "w1.argv.json").exists())

    def test_agy_citations_need_exact_read_url_content(self):
        url = "https://example.org/a"
        calls = [{"name": "search_web", "input": {"query": "a"}, "ok": True,
                  "text": "https://example.org/search Verified source text", "structured": None},
                 {"name": "read_url_content", "input": {"Url": url}, "ok": True,
                  "text": "**Verified** source text", "structured": None}]
        claims = [claim(url, "Verified source text"),
                  claim("https://example.org/search", "Verified source text", claim_id="c2"),
                  claim("https://example.org/never", "Verified source text", claim_id="c3")]
        self.assertEqual(runner.verify_claims(claims, calls, "web", self.repo, "agy"),
                         ["retrieved", "unverified", "mismatch"])
        with self.assertRaises(runner.RunError):
            runner.agy_session("../../outside")

    def test_mixed_provider_worker_settings_are_isolated(self):
        self.spec["workers"][1]["provider"] = "claude"
        self.spec["model"] = "claude-test"
        self.spec["effort"] = "high"
        self.spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
        value = response(claim("https://claude.example/doc", "Claude source text"))
        (self.fake / "w2.jsonl").write_text(stream(PanelTests.SESSIONS["w2"],
                                                 [fetch("https://claude.example/doc", "Claude source text")],
                                                 value), encoding="utf-8")
        code, record, _, error = self.panel(extra=("--agy-effort", "low"))
        self.assertEqual(code, 0, (record, error))
        settings = record["worker_settings"]
        self.assertEqual(settings["w1"], {"provider": "agy", "model": runner.AGY_MODEL, "effort": "low"})
        self.assertEqual(settings["w2"], {"provider": "claude", "model": "claude-test", "effort": "high"})
        argv = json.loads((self.fake / "w1.argv.json").read_text())
        self.assertNotIn("claude-test", argv)
        self.assertEqual(argv[argv.index("--effort") + 1], "low")

    def test_repository_review_resume_and_build_gate(self):
        code, record, _, error = self.call(mode="review")
        self.assertEqual(code, 0, (record, error))
        self.assertEqual(record["assurance"], "cross_provider")
        self.assertIn("REPOSITORY_SNAPSHOT", record["response"]["limitations"][-1])
        prompt = json.loads((self.fake / "review.stdin.json").read_text())["message"]["content"]
        self.assertIn("Secret plan detail", prompt)
        self.assertIn("no tools or direct repository access", prompt)
        self.assertIn("return a + b", prompt)
        runner.check_approval(record, self.plan, self.repo, "codex")
        legacy_record = dict(record, assurance="cross_provider_plan_only")
        with self.assertRaisesRegex(runner.RunError, "PLAN_BODY_ONLY"):
            runner.check_approval(legacy_record, self.plan, self.repo)
        result_path = Path(record["artifacts"]) / "result.json"
        code, resumed, _, error = self.call(mode="review", extra=("--resume", str(result_path)))
        self.assertEqual(code, 0, (resumed, error))
        self.assertEqual(resumed["session_id"], record["session_id"])
        code, failed, _, _ = self.call(mode="review", case="wrong_id", extra=("--resume", str(result_path)))
        self.assertEqual(code, 1)
        self.assertFalse(failed["fallback_eligible"])
        self.assertIn("different conversation", failed["error"])

    def test_all_hosts_can_select_agy_for_both_review_roles(self):
        for host in runner.HOSTS:
            for builder in runner.BUILDERS:
                if builder == "deepseek" and host != "deepseek":
                    continue
                with self.subTest(host=host, builder=builder):
                    selection = ("--reviewer", "agy", "--builder", builder, "--inspector", "agy")
                    code, review, _, error = self.call("review", host=host, provider=None, extra=selection)
                    self.assertEqual(code, 0, (review, error))
                    approval = Path(review["artifacts"]) / "result.json"
                    code, _, _, error = self.call("check", host=host, provider=None,
                                                 extra=selection + ("--approval", str(approval)))
                    self.assertEqual(code, 0, error)
                    code, inspection, _, error = self.call("inspect", host=host, provider=None, extra=selection)
                    self.assertEqual(code, 0, (inspection, error))
                    self.assertEqual(inspection["roles"], review["roles"])
                    self.assertEqual(inspection["provider"], "agy")
                    self.assertEqual(inspection["assurance"], "cross_provider")
                    self.assertEqual(inspection["snapshot"], runner.snapshot(self.repo, self.base))

    def test_inspection_receives_complete_text_context_manifest_and_diff(self):
        (self.repo / "existing.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        runner.git(self.repo, "add", "existing.py")
        (self.repo / "deleted.py").unlink()
        (self.repo / "new file.py").write_text("# untracked implementation\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
        (self.repo / "ignored.txt").write_text("PRIVATE_IGNORED_CONTENT\n", encoding="utf-8")
        code, record, _, error = self.call("inspect")
        self.assertEqual(code, 0, (record, error))
        context = json.loads((Path(record["artifacts"]) / "repository-context.json").read_text())
        self.assertEqual(context["sha256"], record["repository_context_sha256"])
        files = {f["path"]: f for f in context["files"]}
        self.assertIn("return a - b", files["existing.py"]["content"])
        self.assertEqual(files["deleted.py"]["kind"], "deleted")
        self.assertEqual(files["new file.py"]["content"], "# untracked implementation\n")
        prompt = json.loads((self.fake / "review.stdin.json").read_text())["message"]["content"]
        self.assertIn("TRACKED DIFF:", prompt)
        self.assertIn("-    return a + b", prompt)
        self.assertIn("CHANGE MANIFEST", prompt)
        self.assertNotIn("PRIVATE_IGNORED_CONTENT", prompt)
        self.assertNotIn("--conversation", json.loads((self.fake / "review.argv.json").read_text()))
        self.assertNotEqual(Path((self.fake / "review.cwd.txt").read_text()), self.repo)

    def test_context_omissions_are_explicit_and_symlinks_are_not_followed(self):
        outside = self.root / "outside.txt"
        outside.write_text("PRIVATE_OUTSIDE_CONTENT", encoding="utf-8")
        (self.repo / "link").symlink_to(outside)
        (self.repo / "binary.dat").write_bytes(b"\x00binary")
        code, record, _, error = self.call("review")
        self.assertEqual(code, 0, (record, error))
        prompt = (Path(record["artifacts"]) / "prompt.txt").read_text()
        self.assertNotIn("PRIVATE_OUTSIDE_CONTENT", prompt)
        self.assertIn("Binary/non-UTF-8 content omitted: binary.dat", record["response"]["limitations"])
        self.assertIn("Symlink target not followed: link", record["response"]["limitations"])

    def test_context_and_final_prompt_limits_fail_before_launch(self):
        for target in (self.repo / "large.txt", self.root / "feedback.txt"):
            with self.subTest(target=target):
                target.write_text("x" * runner.AGY_MAX_PROMPT_BYTES, encoding="utf-8")
                extra = ("--feedback", str(target)) if target.parent != self.repo else ()
                with patch.object(runner, "execute") as execute:
                    code, record, _, error = self.call("review", extra=extra)
                self.assertEqual(code, 1, (record, error))
                self.assertIn("limit", record["error"] if record else error)
                execute.assert_not_called()
                target.unlink()

    def test_repository_changes_on_success_and_timeout_reject_verdict(self):
        execute = runner.execute
        for mode, timeout in (("review", False), ("inspect", False), ("inspect", True)):
            with self.subTest(mode=mode, timeout=timeout):
                def mutate(*args, **kwargs):
                    result = execute(*args, **kwargs)
                    (self.repo / "existing.py").write_text(str(time.time()), encoding="utf-8")
                    if timeout:
                        raise subprocess.TimeoutExpired(args[0], 1)
                    return result
                with patch.object(runner, "execute", side_effect=mutate):
                    code, record, _, error = self.call(mode)
                self.assertEqual(code, 1, (record, error))
                self.assertEqual(record["failure_kind"], "confinement_violation")
                self.assertFalse(record["fallback_eligible"])
                self.assertNotIn("response", record)

    def test_inspection_stays_fresh_and_has_no_same_provider_fallback(self):
        code, record, _, error = self.call("inspect")
        self.assertEqual(code, 0, (record, error))
        path = Path(record["artifacts"]) / "result.json"
        for extra in (("--resume", str(path)), ("--fallback-from", str(path))):
            with self.subTest(extra=extra), patch.object(runner, "execute") as execute:
                code, _, _, error = self.call("inspect", extra=extra)
                self.assertEqual(code, 1)
                execute.assert_not_called()

    def test_web_only_plan_edit_invalidates_digest(self):
        code, _, output, _ = self.call(extra=("--dry-run",))
        self.assertEqual(code, 0)
        digest = json.loads(output)["payload_sha256"]
        self.plan.write_text("# Revised plan\n", encoding="utf-8")
        code, _, _, error = self.call(extra=("--payload-sha256", digest))
        self.assertEqual(code, 1)
        self.assertIn("does not match", error)

    def test_profile_subcommand_and_role_boundaries(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"HOME": str(self.home)}), \
             patch.object(runner.tempfile, "gettempdir", return_value=str(self.root)), \
             contextlib.redirect_stdout(output):
            self.assertEqual(runner.main(["agy-profile"]), 0)
        self.assertIn("One-time login:", output.getvalue())
        self.assertIn(str(self.profile), output.getvalue())
        for args in (["build", "--provider", "agy"],):
            with self.subTest(args=args):
                code, _, _, error = self.call(mode=args[0], extra=args[1:])
                self.assertEqual(code, 1)
                self.assertIn("agy", error)
        self.assertEqual(runner.resolve_roles("codex", "agy")["reviewer"], "agy")
        self.assertEqual(runner.resolve_roles("claude", inspector="agy")["inspector"], "agy")
        with self.assertRaises(runner.RunError):
            runner.resolve_roles("agy")

    def test_post_login_settings_security_contract(self):
        settings = self.profile / ".gemini/antigravity-cli/settings.json"
        # Shape of settings-after-login.json: agy dropped default-valued keys and added trustedWorkspaces.
        brain = self.profile / ".gemini/antigravity-cli/brain"
        logged_in = {"enableTerminalSandbox": True,
                     "permissions": {"allow": ["read_url(*)", f"read_file({brain})"],
                                     "deny": ["write_file(*)", "command(*)",
                                              "unsandboxed(*)", "mcp(*)", "execute_url(*)"]},
                     "toolPermission": "request-review",
                     "trustedWorkspaces": [str(self.root / "login")]}
        settings.write_text(json.dumps(logged_in), encoding="utf-8")
        runner.agy_profile_check(self.profile, "web")
        permitted = copy.deepcopy(logged_in)
        permitted["permissions"]["ask"] = ["write_url(*)"]
        settings.write_text(json.dumps(permitted), encoding="utf-8")
        runner.agy_profile_check(self.profile, "web")
        with self.assertRaisesRegex(runner.RunError, "rerun agy-profile"):
            runner.agy_profile_check(self.profile, "review")
        review = self.review_profile / ".gemini/antigravity-cli/settings.json"
        review_settings = {"enableTerminalSandbox": True, "toolPermission": "request-review",
                           "permissions": {"deny": ["read_file(*)", "read_url(*)", "write_file(*)",
                                                    "command(*)", "unsandboxed(*)", "mcp(*)",
                                                    "execute_url(*)"]}}
        review.write_text(json.dumps(review_settings), encoding="utf-8")
        runner.agy_profile_check(self.review_profile, "review")  # agy may drop the empty allow list
        del review_settings["toolPermission"]  # live: agy also drops the default request-review preset
        review.write_text(json.dumps(review_settings), encoding="utf-8")
        runner.agy_profile_check(self.review_profile, "review")
        review_settings["toolPermission"] = "request-review"
        for name, change in {"web allowed": lambda x: x["permissions"].update(allow=["read_url(*)"]),
                             "web not denied": lambda x: x["permissions"]["deny"].remove("read_url(*)"),
                             "files not denied": lambda x: x["permissions"]["deny"].remove("read_file(*)")}.items():
            with self.subTest(review=name):
                altered = copy.deepcopy(review_settings)
                change(altered)
                review.write_text(json.dumps(altered), encoding="utf-8")
                with self.assertRaisesRegex(runner.RunError, "rerun agy-profile"):
                    runner.agy_profile_check(self.review_profile, "review")
        variants = {
            "always-proceed": lambda x: x.update(toolPermission="always-proceed"),
            "strict": lambda x: x.update(toolPermission="strict"),
            "extra allow": lambda x: x["permissions"]["allow"].append("command(*)"),
            "missing deny": lambda x: x["permissions"]["deny"].remove("command(*)"),
            "outside access": lambda x: x.update(allowNonWorkspaceAccess=True),
            "unknown key": lambda x: x.update(enableTelemetry=False),
        }
        for name, change in variants.items():
            with self.subTest(name=name):
                altered = copy.deepcopy(logged_in)
                change(altered)
                settings.write_text(json.dumps(altered), encoding="utf-8")
                with self.assertRaisesRegex(runner.RunError, "rerun agy-profile"):
                    runner.agy_profile_check(self.profile, "web")

    SENTENCE = "This module offers classes representing filesystem paths"

    def saved_page(self, worker, sentence=SENTENCE):
        """Live shape: read_url_content returns only the path of the page it saved in the brain dir."""
        page = (self.profile / ".gemini/antigravity-cli/brain" / PanelTests.SESSIONS[worker] /
                ".system_generated/steps/2/content.md")
        (self.fake / f"{worker}.page.md").write_text(f"# pathlib\n\n{sentence}.\n", encoding="utf-8")
        return page, ("Title: Cached Content\n\nOG Description: Fetched from cache\n\n"
                      "The full content of the article at https://docs.python.org/3/library/pathlib.html "
                      f"has been saved to: {page}\n\nYou can use the view_file tool to read specific sections.")

    def test_live_shape_web_denials_and_cached_content_citation(self):
        url = "https://docs.python.org/3/library/pathlib.html"
        for worker in ("w1", "w2"):
            page, saved = self.saved_page(worker)
            tools = [
                ("search_web", {"query": "Python pathlib", "toolAction": "search"}, "DONE",
                 f'The search for "Python pathlib" returned the following summary: {url}'),
                ("read_url_content", {"Url": url, "toolAction": "Reading pathlib docs page"}, "DONE", saved),
                ("view_file", {"AbsolutePath": str(page)}, "DONE", f"1: {self.SENTENCE}."),
                ("view_file", {"AbsolutePath": "/outside/secret"}, "ERROR",
                 "Encountered error in step execution: permission denied"),
                ("run_command", {"CommandLine": "cat ../secret"}, "ERROR",
                 "Encountered error in step execution: permission denied"),
                ("run_command", {"CommandLine": "cat linked-secret"}, "ERROR",
                 "Encountered error in step execution: permission denied"),
            ]
            self.script_live_shape(worker, tools, response(claim(url, self.SENTENCE)))
        code, record, _, error = self.panel()
        self.assertEqual(code, 0, (record, error))
        for worker in record["workers"]:
            self.assertEqual(worker["denied_attempts"], ["view_file", "run_command", "run_command"])
            self.assertTrue((Path(worker["artifacts"]) / "steps/2/content.md").is_file())
        panel = json.loads(Path(record["panel"]).read_text(encoding="utf-8"))
        self.assertEqual([item["status"] for item in panel["claims"]], ["retrieved", "retrieved"])

    def test_saved_page_is_the_only_file_a_web_worker_may_read(self):
        url = "https://docs.python.org/3/library/pathlib.html"
        page, saved = self.saved_page("w1")
        builtin = self.profile / ".gemini/antigravity-cli/builtin/skills/x/SKILL.md"
        other = self.profile / ".gemini/antigravity-cli/brain" / PanelTests.SESSIONS["w2"] / "logs/t.jsonl"
        for name, tools in {
            "bundled skill read": [("read_url_content", {"Url": url}, "DONE", saved),
                                   ("view_file", {"AbsolutePath": str(builtin)}, "DONE", "1: skill")],
            "other conversation": [("view_file", {"AbsolutePath": str(other)}, "DONE", "1: plan")],
            "page outside conversation": [("read_url_content", {"Url": url}, "DONE",
                                           saved.replace(str(page), str(other)))],
        }.items():
            with self.subTest(name=name):
                for worker in ("w1", "w2"):
                    self.script_live_shape(worker, tools, response(claim(url, self.SENTENCE)))
                code, record, _, error = self.panel()
                self.assertEqual(code, 1, (record, error))
                self.assertEqual(record["status"], "failed")
                self.assertFalse((Path(record["artifacts"]) / "panel.json").exists())

    def test_agy_review_severity_case_is_normalized_but_unknown_values_fail(self):
        finding = {"id": "f1", "path": "Step 6", "evidence": "finish is not allowed", "fix": "allow it"}
        for severity, expected in (("HIGH", 0), ("critical", 1)):
            with self.subTest(severity=severity):
                value = {"verdict": "REVISE", "summary": "Stale step.", "coverage": ["Step 6"],
                         "limitations": [], "findings": [dict(finding, severity=severity)]}
                self.script_live_shape("review", [], value)
                code, record, _, error = self.call("review")
                self.assertEqual(code, expected, (record, error))
                if not expected:
                    self.assertEqual(record["response"]["findings"][0]["severity"], "high")

    def test_review_uses_the_offline_review_profile(self):
        code, record, _, error = self.call("review")
        self.assertEqual(code, 0, (record, error))
        self.assertEqual(Path((self.fake / "review.home.txt").read_text()), self.review_profile)
        settings = json.loads((self.review_profile / ".gemini/antigravity-cli/settings.json").read_text())
        self.assertIn("read_url(*)", settings["permissions"]["deny"])
        self.assertIn("read_file(*)", settings["permissions"]["deny"])
        self.assertEqual(settings["permissions"]["allow"], [])

    def test_live_shape_review_finish_and_denied_attempts(self):
        value = {"verdict": "APPROVED", "summary": "Plan body checked.", "findings": [],
                 "coverage": ["supplied plan body"], "limitations": []}
        self.script_live_shape("review", [], value)
        code, record, _, error = self.call(mode="review")
        self.assertEqual(code, 0, (record, error))
        self.assertEqual(record["denied_attempts"], [])
        self.script_live_shape("review", [
            ("view_file", {"AbsolutePath": "/outside/secret"}, "ERROR",
             "Encountered error in step execution: permission denied")], value)
        code, record, _, error = self.call(mode="review")
        self.assertEqual(code, 0, (record, error))
        self.assertEqual(record["denied_attempts"], ["view_file"])

    def test_live_shape_forbidden_done_fails_and_read_error_is_not_evidence(self):
        url = "https://docs.python.org/3/library/pathlib.html"
        value = response(claim(url, "Title: Cached Content"))
        self.script_live_shape("w1", [
            ("view_file", {"AbsolutePath": "/outside/secret"}, "DONE", "secret")], value)
        code, record, _, _ = self.panel()
        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "failed")
        self.assertFalse((Path(record["artifacts"]) / "panel.json").exists())
        self.script_live_shape("w1", [
            ("read_url_content", {"Url": url}, "ERROR", "Title: Cached Content")], value)
        self.script_live_shape("w2", [
            ("read_url_content", {"Url": url}, "ERROR", "Title: Cached Content")], value)
        code, record, _, _ = self.panel()
        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "partial")
        panel = json.loads(Path(record["panel"]).read_text(encoding="utf-8"))
        self.assertFalse(panel["claims"])
        self.assertFalse(any(record["coverage"]["q1"].values()))


if __name__ == "__main__":
    unittest.main()


class DeepSeekWindowsTests(unittest.TestCase):
    def test_deepseek_is_refused_on_windows(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(runner.sys, "platform", "win32"), \
                contextlib.redirect_stderr(io.StringIO()) as error:
            plan = Path(temp) / "plan.md"
            plan.write_text("# Plan\n", encoding="utf-8")
            code = runner.main(["review", "--host", "claude", "--provider", "deepseek",
                                "--repo", temp, "--plan", str(plan)])
        self.assertEqual(code, 1)
        self.assertIn("not validated on Windows", error.getvalue())


@unittest.skipIf(sys.platform == "win32", "DeepSeek runs are refused on Windows")
class DeepSeekTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="claudex-dsh-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.plan = self.root / "plan.md"
        self.plan.write_text("# Plan\nDocument add.\n", encoding="utf-8")
        self.outside = self.root / "outside.txt"
        self.outside.write_text("secret\n")
        self.artifacts = self.root / "runs"
        self.fake = self.root / "fake"
        self.fake.mkdir()
        self.dsh = self.root / "dsh.py"
        self.dsh.write_text(FAKE_DSH, encoding="utf-8")
        for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"), ("config", "user.name", "T")):
            self.git(*args)
        (self.repo / "existing.py").write_text("original\n")
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, stderr=subprocess.PIPE).decode()

    def call(self, mode="review", case="ok", extra=(), provider="deepseek", validated=True, host="claude",
             ids=None):
        args = [mode, "--host", host, "--repo", str(self.repo), "--plan", str(self.plan),
                "--artifacts", str(self.artifacts), *extra]
        if provider:
            args += ["--provider", provider]
        if mode == "inspect":
            args += ["--base", self.base]
        old = set(self.artifacts.glob("*/result.json")) if self.artifacts.exists() else set()
        output, error = io.StringIO(), io.StringIO()
        with patch.object(runner, "cli_prefix", return_value=[sys.executable, str(self.dsh)]), \
             patch.object(runner, "VALIDATED_DSH_CLI", ("0.2.1-rc.2",) if validated else ()), \
             patch.dict(os.environ, {"FAKE_DSH_CASE": case, "FAKE_DSH_DIR": str(self.fake),
                                     "FAKE_DSH_IDS": json.dumps(ids or sorted(runner.DSH_ENABLED_ALLOWLIST)),
                                     "FAKE_DSH_OUTSIDE": str(self.outside), "FAKE_DSH_PLAN": str(self.plan)}), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = runner.main(args)
        new = set(self.artifacts.glob("*/result.json")) - old if self.artifacts.exists() else set()
        path = next(iter(new)) if new else None
        return code, json.loads(path.read_text()) if path else None, path, error.getvalue()

    def assert_violation(self, case):
        code, record, _, error = self.call(case=case)
        self.assertEqual(code, 1, error)
        self.assertEqual((record["failure_kind"], record["fallback_eligible"]), ("confinement_violation", False))
        self.assertNotIn("response", record)
        return record

    def test_review_and_inspection_succeed_with_lockdown(self):
        code, record, _, error = self.call()
        self.assertEqual(code, 0, error)
        self.assertEqual((record["provider"], record["assurance"]), ("deepseek", "cross_provider"))
        self.assertEqual(record["roles"]["reviewer"], "deepseek")
        self.assertEqual(record["tool_calls_audited"], 1)
        self.assertEqual(record["usage"], {"input_tokens": 10, "output_tokens": 5, "cached_input_tokens": 3})
        argv = json.loads((self.fake / "argv.json").read_text())
        self.assertEqual(argv[1:4], ["--profile", "headless", "--patch"])
        self.assertEqual(argv[-2:], ["--json", "-"])
        env = json.loads((self.fake / "env.json").read_text())
        self.assertEqual({key: env[key] for key in
                          ("DSH_PERMISSION_MODE", "DSH_TOOLS_MODE", "DSH_TELEMETRY_MODE")},
                         {"DSH_PERMISSION_MODE": "read-only", "DSH_TOOLS_MODE": "native",
                          "DSH_TELEMETRY_MODE": "DISABLED"})
        for key in ("DSH_SESSION_ID", "DSH_PROFILE", "DSH_PROFILE_DIR", "DSH_SHELL"):
            self.assertNotIn(key, env)
        patch_text = (self.fake / "patch.yml").read_text()
        self.assertEqual(patch_text.count("disabled: true"), len(runner.DSH_DISABLE))
        for entry in ("tool-working-directory", "web-deepseek-api"):
            self.assertIn(f"- id: {entry}\n  disabled: true\n", patch_text)
        self.assertIn("- id: credentials\n  disabled: false\n", patch_text)
        self.assertNotIn("bash-sandbox", patch_text.replace("pwsh-sandbox", ""))
        self.assertNotIn("agent-default-model", patch_text)
        self.assertEqual(Path((self.fake / "cwd.txt").read_text()).resolve(), self.repo)
        stdin = (self.fake / "stdin.txt").read_text()
        self.assertIn(f"Your repository root is {self.repo}", stdin)
        self.assertIn('"verdict"', stdin)
        code, record, _, error = self.call(host="codex")
        self.assertEqual(code, 0, error)
        self.assertEqual((record["roles"]["host"], record["roles"]["reviewer"]), ("codex", "deepseek"))
        code, record, _, error = self.call(mode="inspect")
        self.assertEqual(code, 0, error)
        self.assertEqual((record["roles"]["inspector"], record["provider"]), ("deepseek", "deepseek"))
        self.assertIsNotNone(record["snapshot"])

    def test_reviewer_environment_drops_host_session_controls(self):
        ambient = {"DSH_SESSION_ID": "session-host", "DSH_PROFILE": "web",
                   "DSH_PROFILE_DIR": "/tmp/host-profile", "DSH_SHELL": "1",
                   "DSH_TOOLS_MODE": "dangerous", "DSH_HOME": str(self.root / "dsh-home")}
        with patch.dict(os.environ, ambient):
            code, record, _, error = self.call()
        self.assertEqual(code, 0, error)
        env = json.loads((self.fake / "env.json").read_text())
        for key in ("DSH_SESSION_ID", "DSH_PROFILE", "DSH_PROFILE_DIR", "DSH_SHELL"):
            self.assertNotIn(key, env)
        self.assertEqual(env["DSH_HOME"], ambient["DSH_HOME"])
        self.assertEqual({key: env[key] for key in
                          ("DSH_PERMISSION_MODE", "DSH_TOOLS_MODE", "DSH_TELEMETRY_MODE")},
                         {"DSH_PERMISSION_MODE": "read-only", "DSH_TOOLS_MODE": "native",
                          "DSH_TELEMETRY_MODE": "DISABLED"})

    def test_explicit_roles_select_deepseek_without_execution_override(self):
        for host in runner.PROVIDERS:
            for builder in runner.PROVIDERS:
                with self.subTest(host=host, builder=builder):
                    selection = ("--reviewer", "deepseek", "--builder", builder, "--inspector", "deepseek")
                    code, review, approval, error = self.call(host=host, provider=None, extra=selection)
                    self.assertEqual(code, 0, error)
                    self.assertEqual(review["provider"], "deepseek")
                    code, _, _, error = self.call(mode="check", host=host, provider=None,
                                                 extra=selection + ("--approval", str(approval)))
                    self.assertEqual(code, 0, error)
                    code, inspection, _, error = self.call(mode="inspect", host=host, provider=None, extra=selection)
                    self.assertEqual(code, 0, error)
                    self.assertEqual(inspection["provider"], "deepseek")
                    self.assertEqual(inspection["roles"], review["roles"])
                    self.assertIsNotNone(inspection["snapshot"])

    def assert_resume_refused(self, path, **kwargs):
        marker = self.fake / "invocations.txt"
        marker.unlink(missing_ok=True)
        before = set(self.artifacts.glob("*/result.json"))
        code, record, _, error = self.call(extra=("--resume", str(path), *kwargs.pop("extra", ())), **kwargs)
        self.assertEqual((code, record), (1, None))
        self.assertIn("never resume", error)
        self.assertEqual(set(self.artifacts.glob("*/result.json")), before)
        self.assertFalse(marker.exists())

    def test_resume_is_refused_before_launch(self):
        # dsh persists `cd` in a session, so a resumed reviewer could read outside the repository.
        code, _, path, error = self.call()
        self.assertEqual(code, 0, error)
        self.assert_resume_refused(path)
        self.assert_resume_refused(path, mode="inspect")
        with self.assertRaisesRegex(runner.RunError, "never resume"):
            runner.dsh_command("review", self.artifacts, None, "session-0b5f3c1e-7d2a-4b8e-9f10-2a3b4c5d6e7f")

    def test_resume_refuses_changed_roles(self):
        code, _, path, error = self.call()
        self.assertEqual(code, 0, error)
        for extra, host in ((("--builder", "codex"), "claude"), ((), "codex")):
            with self.subTest(host=host, extra=extra):
                self.assert_resume_refused(path, extra=extra, host=host)

    def test_malformed_and_fenced_final(self):
        code, record, path, _ = self.call(case="malformed")
        self.assertEqual((code, record["failure_kind"], record["fallback_eligible"]), (1, "provider_failure", False))
        self.assert_resume_refused(path)
        code, record, _, error = self.call(case="fenced")
        self.assertEqual(code, 0, error)
        self.assertEqual(record["response"]["verdict"], "APPROVED")

    def test_confinement_violations(self):
        for case in ("disallowed", "outside", "glob_escape", "escalation", "truncated_call", "no_input",
                     "unmatched_result", "write"):
            with self.subTest(case=case):
                self.git("checkout", "-q", "--", ".")
                self.assert_violation(case)
        record = self.assert_violation("violation_and_auth")
        self.assertEqual(record["disallowed_tool_calls"], ["bash"])
        record = self.assert_violation("torn_call")
        self.assertTrue(any("not a complete JSON object" in e for e in record["unauditable_tool_events"]))
        code, record, _, _ = self.call(case="violation_timeout", extra=("--timeout", "2"))
        self.assertEqual((record["failure_kind"], record["fallback_eligible"]), ("confinement_violation", False))

    def test_audit_crash_inputs_become_recorded_violations(self):
        os.symlink("loop", self.repo / "loop")
        self.git("add", "loop")
        self.git("commit", "-qm", "loop")
        for case in ("symlink_loop", "list_result_id"):
            with self.subTest(case=case):
                record = self.assert_violation(case)
                self.assertEqual(record["status"], "failed")

    def test_change_to_already_dirty_files_or_index_is_detected(self):
        (self.repo / "existing.py").write_text("dirty before review\n")
        self.assertTrue(self.assert_violation("write_modified")["working_tree_changed"])
        (self.repo / "scratch.txt").write_text("untracked before review\n")
        self.assert_violation("write_untracked")
        (self.repo / "existing.py").write_text("dirty before review\n")
        self.assert_violation("index_only")

    def test_allowed_reads_pass(self):
        for case in ("plan_read", "big_result", "grep_include"):
            with self.subTest(case=case):
                code, record, _, error = self.call(case=case)
                self.assertEqual(code, 0, error)

    def test_failure_classification(self):
        code, record, _, _ = self.call(case="auth")
        self.assertEqual((record["failure_kind"], record["fallback_eligible"]), ("provider_unavailable", True))
        code, record, _, _ = self.call(case="final_auth")
        self.assertEqual((record["failure_kind"], record["fallback_eligible"]), ("provider_failure", False))
        for case, kind in (("server", "provider_unavailable"), ("rate", "provider_unavailable"),
                           ("bad_request", "provider_failure")):
            with self.subTest(case=case):
                code, record, _, _ = self.call(case=case)
                self.assertEqual((code, record["failure_kind"]), (1, kind))
                self.assertEqual(record["fallback_eligible"], kind == "provider_unavailable")
        code, record, _, _ = self.call(case="failed_turn_exit0")
        self.assertIn("reported a failed turn", record["error"])
        self.assertEqual(record["failure_kind"], "provider_unavailable")
        code, record, _, _ = self.call(case="patch_warn")
        self.assertEqual((code, record["failure_kind"]), (1, "provider_failure"))
        self.assertIn("lockdown patch", record["error"])

    def test_refusals(self):
        code, failed, path, _ = self.call(case="auth")
        for mode, extra, provider, message in (
                ("review", ("--fallback-from", str(path)), "deepseek", "no same-provider fallback"),
                ("review", ("--fallback-from", str(path)), "claude", "default reviewer"),
                ("review", ("--effort", "high"), "deepseek", "--effort"),
                ("build", (), "deepseek", "review and inspect"),
                ("panel", (), "deepseek", "review and inspect")):
            with self.subTest(mode=mode, provider=provider):
                code, _, _, error = self.call(mode=mode, extra=extra, provider=provider)
                self.assertEqual(code, 1)
                self.assertIn(message, error)
        code, record, _, error = self.call(validated=False)
        self.assertEqual(code, 1)
        self.assertIn("not validated", record["error"])
        code, record, _, error = self.call(validated=False, extra=("--allow-unvalidated-cli",))
        self.assertEqual(code, 0, error)
        self.assertEqual((record["cli_validated"], record["allow_unvalidated_cli"]), (False, True))

    def test_profile_composition_is_verified_before_launch(self):
        for case, message in (("user_layer", "non-vendor layer"), ("extra_plugin", "hooks-claude-code"),
                              ("dump_fail", "--dump-config failed"), ("dump_patch_warn", "unknown plugin id"),
                              ("authorization", "authorization"), ("deepseek-account", "deepseek-account")):
            with self.subTest(case=case):
                code, record, _, _ = self.call(case=case)
                self.assertEqual((code, record["failure_kind"], record["fallback_eligible"]),
                                 (1, "provider_failure", False))
                self.assertIn(message, record["error"])
                self.assertFalse((self.fake / "argv.json").exists())

    def test_spike_composition_of_validated_version_is_accepted(self):
        self.assertEqual(runner.VALIDATED_DSH_CLI, ("0.2.1-rc.2",))
        # Enabled ids from `dsh --profile headless --patch dsh-patch.yml --dump-config`, dsh 0.2.1-rc.2.
        spike = ["plugin-manager", "timer", "llm", "deepseek-llm-api-extensions", "session",
                 "session-log-deepseek", "typert", "typert-loader", "typert-gateway", "remote-access", "agent",
                 "plugin-package-inventory-deepseek", "agent-default-model", "llm-retry", "config-editor",
                 "settings", "credentials", "llm-pi-ai", "session-persistence-jsonl", "attachment-local",
                 "session-query-sqlite", "working-directory", "session-projection", "storage", "storage-json",
                 "storage-domain", "session-projection-cache", "subprocess", "sandbox", "sandbox-policy",
                 "bash-sandbox", "approval", "permission", "shell-env", "fs-observation-policy", "tool-fs",
                 "tool-fs-search", "commands", "command-feedback", "token-meter", "compaction-basic",
                 "command-compact", "subagent", "subagent-spawn-in-process", "subagent-fork-in-process",
                 "timeout-policy", "spill-local", "spill-policy", "session-checkpoint-policy",
                 "tool-result-pruner", "image-offload", "repeat-tool-reminder", "tools", "system-prompt",
                 "agent-loop", "fs-sandbox", "llm-deepseek", "llm-deepseek-account", "headless-startup",
                 "headless-runner"]
        # The allowlist is exactly the validated composition: an extra entry would widen the boundary.
        self.assertEqual(runner.DSH_ENABLED_ALLOWLIST, frozenset(spike))
        code, record, _, error = self.call(ids=spike)
        self.assertEqual(code, 0, error)
        self.assertEqual(record["dsh_enabled_entries"], len(spike))
        code, record, _, _ = self.call(ids=spike + ["tool-new-model-facing"])
        self.assertEqual(code, 1)
        self.assertIn("tool-new-model-facing", record["error"])

    def test_fingerprint_failure_keeps_violation_evidence(self):
        real = runner.dsh_fingerprint
        calls = []
        def flaky(repo):
            calls.append(repo)
            if len(calls) > 1:
                raise runner.RunError("git timed out")
            return real(repo)
        with patch.object(runner, "dsh_fingerprint", side_effect=flaky):
            record = self.assert_violation("disallowed")
        self.assertEqual(record["disallowed_tool_calls"], ["bash"])
        self.assertTrue(any("working-tree check failed" in e for e in record["unauditable_tool_events"]))

    def test_non_git_is_refused(self):
        shutil.rmtree(self.repo / ".git")
        code, record, _, error = self.call()
        self.assertEqual(code, 1)
        self.assertIn("git repository", error)

    def test_model_patch_and_roles(self):
        code, record, _, error = self.call(extra=("--model", "deepseek-v4-pro"))
        self.assertEqual(code, 0, error)
        self.assertIn("model: deepseek-v4-pro", (self.fake / "patch.yml").read_text())
        code, _, _, error = self.call(extra=("--model", "x\n- id: tool-bash"))
        self.assertEqual(code, 1)
        self.assertEqual(runner.resolve_roles("claude", "deepseek")["reviewer"], "deepseek")
        self.assertEqual(runner.resolve_roles("claude", inspector="deepseek")["inspector"], "deepseek")
        with self.assertRaises(runner.RunError):
            runner.resolve_roles("claude", builder="codex", inspector="codex")
        self.assertEqual(runner.resolve_roles("deepseek"),
                         {"host": "deepseek", "planner": "deepseek", "reviewer": "claude",
                          "builder": "deepseek", "inspector": "claude"})
        with self.assertRaises(runner.RunError):
            runner.resolve_roles("deepseek", reviewer="deepseek")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.main(["roles", "--host", "claude", "--provider", "deepseek"]), 0)
        self.assertEqual(json.loads(output.getvalue())["reviewer"], "deepseek")
        self.assertIsNone(runner.PROVIDER_ADAPTERS["claude"]["review_env"]({}))
        self.assertIsNone(runner.PROVIDER_ADAPTERS["codex"]["review_env"]({}))

    def test_approval_bound_to_host(self):
        code, record, path, error = self.call()
        self.assertEqual(code, 0, error)
        runner.check_approval(record, self.plan, self.repo, "claude")
        with self.assertRaises(runner.RunError):
            runner.check_approval(record, self.plan, self.repo, "codex")
