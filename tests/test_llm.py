"""Offline runner and guard checks: uv run python tests/test_llm.py."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from earworm import llm


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        self.agent = self.root / "source-agent"
        self.agent.mkdir()
        self.ledger = self.root / "usage.jsonl"
        self.configure()

    def configure(self, extra=""):
        (self.root / "config" / "llm.toml").write_text(
            '[llm]\npi_bin="/usr/bin/true"\nopenrouter_wrapper="/usr/bin/true"\n'
            f'agent_dir="{self.agent}"\n' + extra)

    def fake_execute(self, command, *, root, env, deadline):
        self.command = command
        self.env = env
        settings = json.loads((Path(env["PI_CODING_AGENT_DIR"]) / "settings.json").read_text())
        self.assertFalse(settings["retry"]["enabled"])
        self.assertEqual(settings["retry"]["provider"]["maxRetries"], 0)
        limits = json.loads(Path(env["EARWORM_LIMITS"]).read_text())
        Path(limits["audit_path"]).write_text(json.dumps({"type": "request", "canary": False, "reserved_usd": .02}) + "\n")
        out, err = root / "events.jsonl", root / "stderr.txt"
        out.write_text('safe preflight output\n' + json.dumps({"type": "message_end", "message": {
            "role": "assistant", "provider": "openrouter", "model": limits["model"],
            "responseId": "gen-test", "stopReason": "stop",
            "content": [{"type": "thinking", "thinking": "private reasoning"}, {"type": "text", "text": "Episode text"}],
            "usage": {"cost": {"total": .001}},
        }}) + "\n")
        err.write_text("")
        return 0, out, err

    def test_atomic_artifact_and_actual_cost_not_catalog_estimate(self):
        target = self.root / "script.md"
        target.write_text("old")
        with patch.object(llm, "_execute", self.fake_execute), patch.object(llm, "_actual_cost", return_value=.005):
            result = llm.run("Input", cwd=self.root, expect_file=target, ledger_path=self.ledger, stage="script")
        self.assertEqual(target.read_text(), "Episode text\n")
        self.assertEqual(result["actual_cost_usd"], .005)
        self.assertEqual(llm._committed(llm._events(self.ledger)), .005)
        self.assertIn("--no-builtin-tools", self.command)
        self.assertIn("--no-tools", self.command)
        self.assertEqual(self.command[0], "/usr/bin/true")  # configured required guard
        self.assertEqual(self.env["PI_CANARY_ATTEMPTS"], "3")
        records = llm._events(self.ledger)
        self.assertEqual(records[-1]["artifact_path"], str(target))
        self.assertEqual(len(records[-1]["prompt_sha256"]), 64)

    def test_full_source_cache_survives_temporary_session_cleanup(self):
        def execute(command, **kw):
            cache = kw["root"] / "source-cache"
            cache.mkdir()
            llm._json_write(cache / "source.json", {"url": "https://example.com", "text": "Complete extracted source"})
            return self.fake_execute(command, **kw)
        with patch.object(llm, "_execute", execute), patch.object(llm, "_actual_cost", return_value=.001):
            llm.run_text("Input", cwd=self.root, ledger_path=self.ledger)
        artifact = Path(llm._events(self.ledger)[-1]["artifacts_path"])
        self.assertEqual(json.loads((artifact / "source-cache/source.json").read_text())["text"], "Complete extracted source")

    def test_unknown_actual_cost_keeps_upper_bound(self):
        with patch.object(llm, "_execute", self.fake_execute), patch.object(llm, "_actual_cost", return_value=None):
            llm.run_text("Input", cwd=self.root, ledger_path=self.ledger)
        row = llm._events(self.ledger)[-1]
        self.assertIsNone(row["actual_cost_usd"])
        self.assertEqual(row["budget_charge_usd"], .02)

    def test_partial_charges_and_explicit_reconciliation(self):
        messages = [{"actual_cost_usd": .003, "response_id": "known"}, {"actual_cost_usd": None, "response_id": "late"}]
        requests = [{"type": "request", "canary": True, "reserved_usd": .001},
                    {"type": "request", "canary": False, "reserved_usd": .1},
                    {"type": "request", "canary": False, "reserved_usd": .2}]
        settlement = llm._settlement(messages, requests, 1)
        self.assertAlmostEqual(settlement["budget_charge_usd"], .204)
        self.assertIsNone(settlement["actual_cost_usd"])
        llm._ledger_append(self.ledger, {"type": "settle", "attempt_id": "attempt", "stage": "research", "provider": "openrouter",
                                       "messages": messages, "request_audit": requests, **settlement})
        with patch.object(llm, "_actual_cost", return_value=.004) as cost, patch.object(llm, "_execute") as execute:
            result = llm.reconcile_ledger(self.ledger, cwd=self.root)
        execute.assert_not_called()
        self.assertEqual(cost.call_count, 1)
        self.assertEqual(result["updated_attempts"], 1)
        self.assertAlmostEqual(result["budget_charge_usd"], .008)
        self.assertEqual(len(llm._events(self.ledger)), 2)
        self.assertIsNone(llm._events(self.ledger)[-1]["canary_actual_cost_usd"])

    def test_retained_evidence_deduplicates_and_marks_partial_packet(self):
        artifacts = self.root / "artifacts"
        artifacts.mkdir()
        row = {"tool": "web_fetch", "args": {"url": "https://example.com", "offset": 0}, "is_error": False,
               "result": {"content": [{"type": "text", "text": "Source: https://example.com\nCharacters 0-8000 of 12000. Continue at offset 8000.\n\n" + "Evidence. " * 800}]}}
        llm._json_write(artifacts / "sources.json", [row, row, {"tool": "web_fetch", "args": {"url": "https://failed.test"}, "is_error": False, "result": {"content": [{"type": "text", "text": "No source content retrieved."}]}}])
        llm._ledger_append(self.ledger, {"type": "settle", "attempt_id": "failed", "stage": "research", "failure": "input_limit", "artifacts_path": str(artifacts), "budget_charge_usd": .1})
        text = llm.retained_evidence(self.ledger, "research")
        self.assertEqual(text.count("Source: https://example.com"), 1)
        self.assertNotIn("failed.test", text)
        limited = llm.retained_evidence(self.ledger, "research", max_chars=1000)
        self.assertLessEqual(len(limited), 1000)
        self.assertIn("Recovery packet is partial", limited)
        self.assertIn("Characters 0-8000 of 12000", limited)

    def test_recovery_merges_attempts_and_represents_later_sources(self):
        for number, url in enumerate(("https://first.test", "https://later.test", None)):
            artifacts = self.root / f"artifacts-{number}"
            artifacts.mkdir()
            rows = [] if url is None else [{"tool": "web_fetch", "args": {"url": url}, "result": {
                "content": [{"type": "text", "text": f"Source: {url}\nCharacters 0-8000 of 8000. End of source.\n\n" + "Evidence. " * 800}]}}]
            llm._json_write(artifacts / "sources.json", rows)
            llm._ledger_append(self.ledger, {"type": "settle", "attempt_id": str(number), "stage": "research", "failure": "input_limit", "artifacts_path": str(artifacts), "budget_charge_usd": 0})
        text = llm.retained_evidence(self.ledger, "research", 2000)
        self.assertIn("https://first.test", text)
        self.assertIn("https://later.test", text)
        self.assertEqual(text.count("Excerpt clipped"), 2)
        self.assertLessEqual(len(text), 2000)

    def test_retrieved_sources_stay_out_of_usage_ledger(self):
        sources = llm._sources([
            {"type": "tool_execution_start", "toolCallId": "one", "toolName": "web_fetch", "args": {"url": "https://example.com/paper"}},
            {"type": "tool_execution_end", "toolCallId": "one", "toolName": "web_fetch", "result": {"content": [{"type": "text", "text": "Primary source evidence"}]}, "isError": False},
        ])
        with patch.object(llm, "_attempt", return_value={"result": "Brief", "failure": None, "budget_charge_usd": .01, "source_records": sources}):
            llm.run_text("Input", cwd=self.root, stage="research", ledger_path=self.ledger)
        self.assertNotIn("Primary source evidence", self.ledger.read_text())
        row = llm._events(self.ledger)[-1]
        stored = json.loads((Path(row["artifacts_path"]) / "sources.json").read_text())
        self.assertEqual(stored[0]["args"]["url"], "https://example.com/paper")
        self.assertFalse(stored[0]["storage_truncated"])
        safe = llm._safe_error("HTTP 401 Authorization: Bearer sk-example-secret api_key=secret-value")
        self.assertNotIn("sk-example-secret", safe)
        self.assertNotIn("secret-value", safe)

    def test_no_coding_or_implicit_web_tools(self):
        for stage, tools in (("script", ["WebFetch"]), ("research", ["Read"]), ("text", ["web_search"])):
            with self.assertRaises(llm.LLMError):
                llm.run_text("Input", cwd=self.root, stage=stage, allowed_tools=tools)
        self.assertEqual(llm._tools(["WebSearch", "WebFetch"], "research"), ["web_fetch", "web_search"])
        self.assertEqual(llm._tools(["web_fetch"], "ingest_fetch"), ["web_fetch"])

    def test_config_and_input_fail_before_dispatch(self):
        self.configure('max_input_bytes=3\n')
        with patch.object(llm, "_execute") as execute, self.assertRaises(llm.LLMError):
            llm.run_text("long input", cwd=self.root)
        execute.assert_not_called()
        self.configure('provider="anthropic"\n')
        with self.assertRaises(llm.LLMError):
            llm.run_text("Input", cwd=self.root)
        self.configure('unknown_option=true\n')
        with self.assertRaises(llm.LLMError):
            llm._config(self.root, "text", None)
        (self.root / "config" / "llm.toml").unlink()
        with self.assertRaisesRegex(llm.LLMError, "Copy config/llm.example.toml"):
            llm._config(self.root, "research", None)

    def test_sample_web_stages_have_room_for_tool_results(self):
        sample = Path(__file__).resolve().parents[1] / "config" / "llm.example.toml"
        (self.root / "config" / "llm.toml").write_text(sample.read_text())
        for stage in ("research", "review", "autogen", "ingest_fetch"):
            self.assertGreater(llm._config(self.root, stage, None)["max_requests"], 1)

    def test_only_one_transport_alternate_shares_budget_and_deadline(self):
        self.configure('fallback_provider="deepseek"\nfallback_model="deepseek-v4-pro"\n')
        seen = []
        def attempt(prompt, **kw):
            seen.append(kw)
            return {"result": "Success", "failure": "transport" if len(seen) == 1 else None, "budget_charge_usd": .1}
        with patch.object(llm, "_attempt", attempt):
            self.assertEqual(llm.run_text("Input", cwd=self.root, ledger_path=self.ledger), "Success")
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0]["deadline"], seen[1]["deadline"])
        self.assertAlmostEqual(seen[1]["allowance"], seen[0]["allowance"] - .1)
        self.assertEqual(seen[1]["config"]["provider"], "deepseek")

    def test_guard_refusal_never_falls_back_or_overwrites_artifact(self):
        self.configure('fallback_provider="deepseek"\nfallback_model="deepseek-v4-pro"\n')
        target = self.root / "script.md"
        target.write_text("old")
        with patch.object(llm, "_attempt", return_value={"result": "bad", "failure": "configuration_auth_or_budget", "budget_charge_usd": .01}) as attempt:
            with self.assertRaises(llm.LLMError):
                llm.run("Input", cwd=self.root, expect_file=target, ledger_path=self.ledger)
        self.assertEqual(attempt.call_count, 1)
        self.assertEqual(target.read_text(), "old")
        self.assertEqual(llm._classification(1, [], "preflight refused: HTTP 503"), "configuration_auth_or_budget")
        self.assertEqual(llm._classification(1, [], "HTTP 402 insufficient credits"), "configuration_auth_or_budget")

    def test_crashed_reservation_counts_towards_run_budget(self):
        self.configure('run_budget_usd=1.0\n')
        llm._ledger_append(self.ledger, {"type": "reserve", "attempt_id": "crashed", "budget_charge_usd": 1.0})
        with patch.object(llm, "_attempt") as attempt, self.assertRaises(llm.LLMError):
            llm.run_text("Input", cwd=self.root, ledger_path=self.ledger)
        attempt.assert_not_called()

    def test_empty_clean_review_only(self):
        for stage in ("script_review", "script"):
            with patch.object(llm, "_attempt", return_value={"result": "", "failure": None, "budget_charge_usd": 0}):
                if stage == "script_review":
                    llm.run("Input", cwd=self.root, expect_file=self.root / "empty.md", stage=stage)
                    self.assertEqual((self.root / "empty.md").read_text(), "")
                else:
                    with self.assertRaises(llm.LLMError):
                        llm.run_text("Input", cwd=self.root, stage=stage)

    def test_route_auth_is_isolated_and_claude_is_not_copied(self):
        (self.agent / "auth.json").write_text(json.dumps({"anthropic": {"key": "fake-not-copied"}, "openrouter": {"key": "fake-route"}}))
        (self.agent / "models.json").write_text(json.dumps({"providers": {"openrouter": {"models": []}, "unrelated": {"models": []}}}))
        isolated = self.root / "isolated"
        isolated.mkdir()
        import time
        agent, launcher = llm._isolate(isolated, llm._config(self.root, "text", None), time.monotonic() + 30)
        self.assertEqual(set(json.loads((agent / "auth.json").read_text())), {"openrouter"})
        self.assertEqual((agent / "auth.json").stat().st_mode & 0o777, 0o600)
        self.assertIn("EARWORM_CANARY", launcher.read_text())


@unittest.skipUnless(shutil.which("bun"), "Bun is required for offline extension checks")
class GuardTests(unittest.TestCase):
    def check(self, code, *, budget=1, canary=False, tools=False, requests=1, exhausted=False, effort=""):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            limits = {"provider": "openrouter", "model": "google/gemini-3.1-pro-preview", "max_output_tokens": 2000,
                      "max_input_bytes": 10000, "max_requests": requests, "max_tool_calls": 1,
                      "max_price_input": 2.2, "max_price_output": 13.2,
                      "budget_usd": budget, "deadline_ms": 9999999999999,
                      "audit_path": str(root / "audit.jsonl"), "tools": ["web_fetch"] if tools else [],
                      "request_reasoning_effort": effort}
            llm._json_write(root / "limits.json", limits)
            if exhausted:
                (root / "audit.jsonl").write_text('{"type":"retrieval_budget_exhausted"}\n')
            extension = llm._HERE / "pi_bounds.ts"
            source = f'import init from {json.dumps(str(extension))};\n' + '''
const handlers = {};
init({on:(name, fn)=>{handlers[name]=fn;}});
const event = {payload:{messages:[{role:"user",content:"test"}],max_completion_tokens:99999}};
const ctx = {model:{provider:"openrouter",id:"google/gemini-3.1-pro-preview",api:"openai-completions",cost:{input:2,output:12}}};
''' + code
            process = subprocess.run([shutil.which("bun"), "-e", source], text=True, capture_output=True,
                env={**os.environ, "EARWORM_LIMITS": str(root / "limits.json"), "EARWORM_CANARY": "1" if canary else "0"}, timeout=10)
            return process

    def test_payload_caps_and_canary_caps(self):
        for canary, expected in ((False, 2000), (True, 128)):
            proc = self.check('console.log(JSON.stringify(handlers.before_provider_request(event,ctx)));', canary=canary)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["max_tokens"], expected)
            self.assertNotIn("max_completion_tokens", payload)
            self.assertTrue(payload["provider"]["require_parameters"])
            self.assertFalse(payload["provider"]["allow_fallbacks"])
            self.assertEqual(payload["provider"]["max_price"], {"prompt": 2.2, "completion": 13.2})

    def test_explicit_reasoning_off_reaches_backend_without_removing_caps(self):
        proc = self.check('console.log(JSON.stringify(handlers.before_provider_request(event,ctx)));', effort="none")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["reasoning_effort"], "none")
        self.assertEqual(payload["max_tokens"], 2000)
        self.assertTrue(payload["provider"]["require_parameters"])
        proc = self.check('handlers.before_provider_request(event,ctx);', effort="invalid")
        self.assertEqual(proc.returncode, 1)

    def test_fail_closed_invariants_exit_instead_of_throwing(self):
        for code in (
            'ctx.model.provider="anthropic"; handlers.before_provider_request(event,ctx);',
            'handlers.before_provider_request(event,ctx); handlers.before_provider_request(event,ctx);',
            'handlers.tool_call({toolName:"bash"});',
            'ctx.model.api="google-generative-ai"; handlers.before_provider_request(event,ctx);',
            'event.payload.messages[0].content="x".repeat(10001); handlers.before_provider_request(event,ctx);',
        ):
            proc = self.check('try {' + code + '} catch {console.log("CAUGHT FAIL OPEN");}')
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertNotIn("CAUGHT", proc.stdout)
            self.assertIn("EARWORM_GUARD", proc.stderr)
        self.assertEqual(self.check('handlers.before_provider_request(event,ctx);', budget=.000001).returncode, 1)

    def test_last_request_and_exhausted_retrieval_force_final_artifact(self):
        for options in ({"requests": 1}, {"requests": 5, "exhausted": True}, {"requests": 5, "budget": .055}):
            proc = self.check('console.log(JSON.stringify(handlers.before_provider_request(event,ctx)));', tools=True, **options)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["tool_choice"], "none")
            self.assertIn("Write the final requested artifact now", payload["messages"][-1]["content"])
        proc = self.check('handlers.tool_call({toolName:"web_fetch"}); console.log(JSON.stringify(handlers.before_provider_request(event,ctx)));', tools=True, requests=5)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["tool_choice"], "none")


class ResearchTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("bun") and (Path.home() / ".pi/agent/npm/node_modules/pi-web-access").exists(), "Installed Pi parser dependencies required")
    def test_html_table_headers_and_spans_survive_article_extraction(self):
        # The LOC table has adjacent Preferred/Acceptable columns. Plain
        # textContent places both headings before both cells and loses the link.
        fixture = """<html><body><article><h1>Dataset preservation</h1>
<table><tr><td></td><td>Preferred</td><td>Acceptable</td></tr>
<tr><th scope="row">A. Formats</th><td><ol><li>Platform-independent open formats: <b>SQLite</b>, .db, .sqlite3</li></ol></td><td><p>CDF and HDF</p></td></tr></table>
<table><caption>Grouped recommendations</caption><thead>
<tr><th rowspan="2">Category</th><th colspan="2" scope="colgroup">Preferred</th><th rowspan="2">Acceptable</th></tr>
<tr><th scope="col">Text</th><th scope="col">Database</th></tr></thead>
<tbody><tr><th scope="row">Format</th><td>CSV</td><td>SQLite grouped</td><td>CDF grouped</td></tr></tbody></table>
<table><tr><th>Unclear</th><td rowspan="0">Do not infer this span</td></tr></table>
</article></body></html>"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            llm._json_write(root / "limits.json", {"web_access_path": str(Path.home() / ".pi/agent/npm/node_modules/pi-web-access"),
                "deadline_ms": 9999999999999, "tools": ["web_fetch"], "source_cache": str(root / "source-cache"),
                "max_tool_calls": 24, "audit_path": str(root / "audit.jsonl")})
            source = f'import init from {json.dumps(str(llm._HERE / "pi_research.ts"))};\n' + f'const fixture={json.dumps(fixture)};\n' + '''
const tools = {};
await init({registerTool:tool=>{tools[tool.name]=tool;}});
globalThis.fetch=async()=>new Response(fixture,{headers:{"content-type":"text/html"}});
const result=await tools.web_fetch.execute("table",{url:"https://1.1.1.1/table"});
console.log(JSON.stringify(result));
'''
            process = subprocess.run([shutil.which("bun"), "-e", source], text=True, capture_output=True, timeout=20,
                env={**os.environ, "EARWORM_LIMITS": str(root / "limits.json"), "NODE_PATH": str(Path.home() / ".bun/install/global/node_modules")})
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(process.stdout)
            text = result["content"][0]["text"]
            self.assertIn("column 2: Preferred; row labels", text)
            self.assertIn("column 3: Acceptable; row labels", text)
            preferred = text.split("column 2: Preferred; row labels", 1)[1].split("[rows", 1)[0]
            acceptable = text.split("column 3: Acceptable; row labels", 1)[1].split("[END TABLE", 1)[0]
            self.assertIn("SQLite", preferred)
            self.assertNotIn("CDF", preferred)
            self.assertIn("CDF and HDF", acceptable)
            self.assertNotIn("SQLite", acceptable)
            self.assertIn("column 3: Preferred > Database", text)
            self.assertIn("Value spans the stated rows/columns together", text)
            self.assertIn("AMBIGUOUS TABLE", text)
            cached = json.loads((root / "source-cache" / result["details"]["cached_source_file"]).read_text())
            self.assertIn("column 2: Preferred", cached["text"])

    @unittest.skipUnless(shutil.which("bun") and (Path.home() / ".pi/agent/npm/node_modules/pi-web-access").exists(), "Installed Pi parser dependencies required")
    def test_explicit_retrieval_without_hidden_model_or_local_fetch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            llm._json_write(root / "limits.json", {"web_access_path": str(Path.home() / ".pi/agent/npm/node_modules/pi-web-access"),
                "deadline_ms": 9999999999999, "tools": ["web_search", "web_fetch"], "source_cache": str(root / "source-cache"),
                "max_tool_calls": 24, "audit_path": str(root / "audit.jsonl")})
            source = f'import init from {json.dumps(str(llm._HERE / "pi_research.ts"))};\n' + '''
const tools = {};
await init({registerTool: tool => {tools[tool.name] = tool;}});
let calls = [];
globalThis.fetch = async (url, init) => {
  calls.push(String(url));
  if (String(url).includes("mcp.exa.ai")) return new Response(JSON.stringify({result:{content:[{type:"text",text:"Title: Paper\\nURL: https://example.com\\nText: Evidence"}]}}), {headers:{"content-type":"application/json"}});
  return new Response("<html><body><article><h1>Source paper</h1><p>"+"Important source sentence. ".repeat(900)+"</p></article></body></html>", {headers:{"content-type":"text/html"}});
};
const search = await tools.web_search.execute("one",{query:"source evidence"});
const page = await tools.web_fetch.execute("two",{url:"https://1.1.1.1/paper"});
const next = await tools.web_fetch.execute("next",{url:"https://1.1.1.1/paper",offset:8000});
const blocked = await tools.web_fetch.execute("three",{url:"http://127.0.0.1/secret"});
const emitted = [search,page,next,blocked];
for (let i=0;i<8;i++) emitted.push(await tools.web_fetch.execute("repeat"+i,{url:"https://1.1.1.1/paper"}));
const afterBudget = await tools.web_fetch.execute("over-budget",{url:"https://1.1.1.1/should-not-fetch"});
emitted.push(afterBudget);
console.log(JSON.stringify({calls,search,page,next,blocked,afterBudget,totalCharacters:emitted.reduce((n,r)=>n+r.content[0].text.length,0)}));
'''
            process = subprocess.run([shutil.which("bun"), "-e", source], text=True, capture_output=True, timeout=20,
                env={**os.environ, "EARWORM_LIMITS": str(root / "limits.json"), "NODE_PATH": str(Path.home() / ".bun/install/global/node_modules")})
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(process.stdout)
            self.assertEqual(len(result["calls"]), 2)
            self.assertIn("Evidence", result["search"]["content"][0]["text"])
            self.assertIn("Continue at offset 8000", result["page"]["content"][0]["text"])
            self.assertTrue(result["next"]["details"]["cache_hit"])
            cache = json.loads((root / "source-cache" / result["page"]["details"]["cached_source_file"]).read_text())
            self.assertGreater(len(cache["text"]), 16000)
            self.assertIn("No source content retrieved", result["blocked"]["content"][0]["text"])
            self.assertLessEqual(result["totalCharacters"], 40000)
            self.assertIn("Retrieval evidence budget exhausted", result["afterBudget"]["content"][0]["text"])
            self.assertIn("retrieval_budget_exhausted", (root / "audit.jsonl").read_text())


if __name__ == "__main__":
    unittest.main()
