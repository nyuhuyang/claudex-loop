"""Contract tests use real subprocesses and disposable Git repositories, no model calls."""
import contextlib
import copy
import importlib.util
import io
import json
import os
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
        roles = runner.resolve_roles("codex", builder="claude")
        self.assertEqual((roles["planner"], roles["builder"], roles["inspector"]), ("codex", "claude", "codex"))
        with self.assertRaises(runner.RunError):
            runner.resolve_roles("codex", "codex")

    def test_both_review_adapters_complete_and_bind_custom_plan(self):
        for host in ("claude", "codex"):
            with self.subTest(host=host):
                code, record, path, _ = self.invoke(host)
                self.assertEqual(code, 0, record)
                self.assertEqual(record["session_id"], SESSION)
                self.assertEqual(record["plan"], str(self.plan))
                self.assertEqual(record["plan_sha256"], runner.digest(self.plan.read_bytes()))
                self.assertIn(str(self.plan), (path.parent / "prompt.txt").read_text())
                self.assertEqual(record["response"]["verdict"], "APPROVED")
                self.assertEqual(record["assurance"], "cross_provider")

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
        self.assertNotIn("--disable", json.loads((path.parent / "command.json").read_text()))
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

    def test_inspection_requires_other_provider_and_fresh_session(self):
        code, _, _, error = self.invoke(mode="inspect", extra=("--base", self.base, "--provider", "claude"))
        self.assertEqual(code, 1)
        self.assertIn("opposite the builder", error)
        _, _, previous, _ = self.invoke()
        code, _, _, error = self.invoke(mode="inspect", extra=("--base", self.base, "--resume", str(previous)))
        self.assertEqual(code, 1)
        self.assertIn("fresh session", error)

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

    def call(self, mode="panel", case="ok", extra=()):
        output, error = io.StringIO(), io.StringIO()
        def prefix(name, override=None):
            return [sys.executable, str(self.agy if name == "agy" else self.claude)]
        args = [mode, "--host", "codex", "--repo", str(self.repo), "--plan", str(self.plan),
                "--artifacts", str(self.artifacts), *extra]
        if mode == "panel":
            args += ["--spec", str(self.spec_path)]
        elif mode == "review":
            args += ["--provider", "agy"]
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
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("customization", encoding="utf-8")
                code, record, _, error = self.panel()
                self.assertEqual(code, 1)
                self.assertIsNone(record)
                self.assertIn("agy", error)
                path.unlink()
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

    def test_plan_only_review_resume_and_build_gate(self):
        code, record, _, error = self.call(mode="review")
        self.assertEqual(code, 0, (record, error))
        self.assertEqual(record["assurance"], "cross_provider_plan_only")
        self.assertIn("PLAN_BODY_ONLY", record["response"]["limitations"][-1])
        prompt = json.loads((self.fake / "review.stdin.json").read_text())["message"]["content"]
        self.assertIn("Secret plan detail", prompt)
        self.assertIn("no tools or repository access", prompt)
        with self.assertRaisesRegex(runner.RunError, "PLAN_BODY_ONLY"):
            runner.check_approval(record, self.plan, self.repo)
        result_path = Path(record["artifacts"]) / "result.json"
        code, failed, _, _ = self.call(mode="review", case="wrong_id", extra=("--resume", str(result_path)))
        self.assertEqual(code, 1)
        self.assertFalse(failed["fallback_eligible"])
        self.assertIn("different conversation", failed["error"])

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
        for args in (["build", "--provider", "agy"], ["inspect", "--provider", "agy"]):
            with self.subTest(args=args):
                code, _, _, error = self.call(mode=args[0], extra=args[1:])
                self.assertEqual(code, 1)
                self.assertIn("agy", error)
        self.assertEqual(runner.resolve_roles("codex", "agy")["reviewer"], "agy")
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
