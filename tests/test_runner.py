"""Contract tests use real subprocesses and disposable Git repositories, no model calls."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
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
prompt = sys.stdin.read()
if '--verbose' in sys.argv and os.environ.get('FAKE_PANEL_DIR'):
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

    def call(self, *args, validated=True, env=None):
        output, error = io.StringIO(), io.StringIO()
        variables = {"FAKE_PANEL_DIR": str(self.fake), **(env or {})}
        with patch.object(runner, "cli_prefix", return_value=[sys.executable, str(self.cli)]), \
             patch.object(runner, "VALIDATED_READ_CONFINEMENT_CLI", ("fake-cli",) if validated else ()), \
             patch.dict(os.environ, variables), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = runner.main(["panel", "--host", "codex", "--repo", str(self.repo), "--plan", str(self.plan),
                                "--artifacts", str(self.artifacts), *args])
        return code, output.getvalue(), error.getvalue()

    def dry_run(self, spec=None):
        path = self.root / "panel.json"
        path.write_text(json.dumps(spec or self.spec))
        code, out, error = self.call("--spec", str(path), "--dry-run")
        return code, (json.loads(out) if code == 0 else None), error

    def launch(self, spec=None, extra=(), **kwargs):
        code, dry, error = self.dry_run(spec)
        self.assertEqual(code, 0, error)
        old = set(self.artifacts.glob("claudex-*/result.json")) if self.artifacts.exists() else set()
        code, _, error = self.call("--spec", str(self.root / "panel.json"),
                                   "--payload-sha256", dry["payload_sha256"], *extra, **kwargs)
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
        self.assertEqual(attempts, [{"tool": "Read", "target": "/etc/hosts", "succeeded": False}])

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
        self.assertFalse(record["read_confinement_validated"])
        web_only = dict(self.spec, workers=self.spec["workers"][:2])
        code, record, _, _ = self.launch(web_only, validated=False)
        self.assertEqual(code, 0, record)

    def test_panel_roles_are_cross_provider_and_claude_only(self):
        path = self.root / "panel.json"
        path.write_text(json.dumps(self.spec))
        code, _, error = self.call("--spec", str(path), "--dry-run", "--provider", "codex")
        self.assertEqual(code, 1)
        self.assertIn("opposite", error)
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = runner.main(["panel", "--host", "claude", "--repo", str(self.repo), "--plan", str(self.plan),
                                "--spec", str(path), "--dry-run"])
        self.assertEqual(code, 1)
        self.assertIn("not yet supported", error.getvalue())

    def assert_no_live_workers(self, workers):
        time.sleep(0.4)
        beats = {w: (self.fake / f"{w}.beat").stat().st_mtime for w in workers if (self.fake / f"{w}.beat").exists()}
        time.sleep(0.4)
        for worker, mtime in beats.items():
            self.assertEqual((self.fake / f"{worker}.beat").stat().st_mtime, mtime, f"{worker} still running")

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


if __name__ == "__main__":
    unittest.main()
