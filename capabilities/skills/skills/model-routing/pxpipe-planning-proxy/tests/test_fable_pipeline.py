import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "fable_pipeline.py"
spec = importlib.util.spec_from_file_location("fable_pipeline", MODULE_PATH)
fp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fp)


VALID_PLAN = {
    "contract_version": "1.0",
    "goal": "Create and verify an artifact",
    "summary": "A small verified execution",
    "assumptions": [],
    "constraints": ["Do not delete unrelated files"],
    "execution": {
        "required_toolsets": ["terminal", "file"],
        "max_turns": 8,
        "steps": [
            {
                "id": "S1",
                "title": "Create artifact",
                "objective": "Write the requested file",
                "instructions": ["Create result.txt with the exact requested content"],
                "depends_on": [],
                "expected_evidence": ["File contents"],
                "success_criteria": ["Content matches exactly"],
                "on_failure": "stop",
                "risk": "low",
            }
        ],
    },
    "verification": [{"id": "V1", "method": "Read the file", "pass_condition": "Exact content matches"}],
    "replan_triggers": ["A required path is unavailable"],
    "final_deliverables": ["result.txt"],
    "prohibited_actions": ["Delete unrelated files"],
}


class JsonParsingTests(unittest.TestCase):
    def test_extract_json_from_fence(self):
        raw = "```json\n" + json.dumps(VALID_PLAN) + "\n```"
        self.assertEqual(fp.extract_json_object(raw), VALID_PLAN)

    def test_extract_json_can_select_last_matching_report(self):
        schema = {"report_type": "EXECUTION_REPORT", "status": "completed|blocked|failed"}
        actual = {"report_type": "EXECUTION_REPORT", "status": "completed"}
        raw = f"query {json.dumps(schema)}\nanswer {json.dumps(actual)}"
        self.assertEqual(
            fp.extract_json_object(raw, required_pair=("report_type", "EXECUTION_REPORT")),
            actual,
        )

    def test_validate_plan_accepts_contract(self):
        self.assertEqual(fp.validate_plan(VALID_PLAN), VALID_PLAN)

    def test_validate_plan_rejects_missing_step_evidence(self):
        broken = json.loads(json.dumps(VALID_PLAN))
        del broken["execution"]["steps"][0]["expected_evidence"]
        with self.assertRaisesRegex(fp.ContractError, "expected_evidence"):
            fp.validate_plan(broken)

    def test_validate_plan_rejects_dependency_cycle(self):
        broken = json.loads(json.dumps(VALID_PLAN))
        broken["execution"]["steps"].append({
            **broken["execution"]["steps"][0], "id": "S2", "depends_on": ["S1"]
        })
        broken["execution"]["steps"][0]["depends_on"] = ["S2"]
        with self.assertRaisesRegex(fp.ContractError, "cycle"):
            fp.validate_plan(broken)


class RequestTests(unittest.TestCase):
    def test_planner_request_keeps_task_and_schema_in_text(self):
        body = fp.build_planner_request(
            task="Create /tmp/result.txt exactly",
            context="REFERENCE\n" * 3000,
            model="claude-fable-5",
        )
        self.assertEqual(body["model"], "claude-fable-5")
        self.assertIn("REFERENCE", body["system"])
        user_text = body["messages"][-1]["content"]
        self.assertIn("Create /tmp/result.txt exactly", user_text)
        self.assertIn('"contract_version"', user_text)
        self.assertIn("Return one JSON object", user_text)

    def test_kie_http_200_error_envelope_is_rejected(self):
        with self.assertRaisesRegex(fp.KieError, "Unauthorized"):
            fp.validate_kie_response({"code": 401, "msg": "Unauthorized"})

    def test_load_context_is_explicit_and_does_not_auto_pad(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "spec.md"
            p.write_text("useful context", encoding="utf-8")
            rendered = fp.load_context([p])
            self.assertIn("useful context", rendered)
            self.assertNotIn("walter-operating-mode", rendered)


class ExecutorTests(unittest.TestCase):
    def test_run_executor_stops_only_the_proxy_it_started(self):
        plan = json.loads(json.dumps(VALID_PLAN))
        completed = __import__("subprocess").CompletedProcess(
            args=["hermes"], returncode=0,
            stdout='{"report_type":"EXECUTION_REPORT","status":"completed","completed_steps":["S1"],"evidence":[],"deliverables":[],"errors":[],"replan_needed":false}',
            stderr="",
        )
        seen = {}

        def fake_run(command, **kwargs):
            seen["command"] = command
            home = Path(kwargs["env"]["HERMES_HOME"])
            seen["config"] = json.loads((home / "config.yaml").read_text(encoding="utf-8"))
            return completed

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(fp, "_start_pxpipe_if_needed", return_value=object()) as start, \
             patch.object(fp, "_stop_own_process") as stop, \
             patch.object(fp.subprocess, "run", side_effect=fake_run):
            report, _ = fp.run_executor(
                plan, workdir=Path(tmp), provider="custom:kie-pxpipe",
                usage_file=Path(tmp) / "usage.json",
            )
        self.assertEqual(report["status"], "completed")
        command = seen["command"]
        self.assertEqual(command[0:4], ["hermes", "chat", "-Q", "-q"])
        self.assertTrue(command[4].startswith("You are the execution agent"))
        self.assertEqual(command[command.index("--provider") + 1], "custom:kie-pxpipe")
        self.assertEqual(command[command.index("-m") + 1], "claude-sonnet-5")
        self.assertEqual(command[command.index("--max-turns") + 1], "8")
        self.assertEqual(seen["config"]["agent"]["max_turns"], 8)
        self.assertEqual(
            seen["config"]["providers"]["kie-pxpipe"]["api_mode"],
            "anthropic_messages",
        )
        start.assert_called_once()
        stop.assert_called_once()

    def test_executor_prompt_requires_tools_and_evidence(self):
        prompt = fp.build_executor_prompt(VALID_PLAN)
        self.assertIn("actually use tools", prompt)
        self.assertIn("EXECUTION_REPORT", prompt)
        self.assertIn("Create artifact", prompt)

    def test_toolsets_are_allowlisted(self):
        self.assertEqual(fp.executor_toolsets(VALID_PLAN), ["file", "terminal"])
        broken = json.loads(json.dumps(VALID_PLAN))
        broken["execution"]["required_toolsets"] = ["terminal", "computer-use"]
        with self.assertRaisesRegex(fp.ContractError, "toolset"):
            fp.executor_toolsets(broken)


class ReplanTests(unittest.TestCase):
    @staticmethod
    def _args(tmp, *, max_replans=1):
        return SimpleNamespace(
            task="Create and verify an artifact", task_file=None, context=[],
            planner_model="claude-fable-5", pxpipe_url="http://127.0.0.1:47822",
            workdir=tmp, plan_output=str(Path(tmp) / "plan.json"),
            report=str(Path(tmp) / "report.json"), usage_file=None,
            executor_model="claude-sonnet-5", executor_provider="custom:kie-pxpipe",
            max_replans=max_replans,
        )

    def test_major_blocker_replans_once_then_completes(self):
        blocked = {
            "report_type": "EXECUTION_REPORT", "status": "blocked",
            "completed_steps": [], "failed_step": "S1", "evidence": [],
            "errors": ["required path unavailable"], "deliverables": [],
            "replan_needed": True, "replan_reason": "major blocker",
        }
        completed = {
            "report_type": "EXECUTION_REPORT", "status": "completed",
            "completed_steps": ["S1"], "failed_step": None, "evidence": [],
            "errors": [], "deliverables": ["result.txt"],
            "replan_needed": False, "replan_reason": None,
        }
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(fp, "call_planner", side_effect=[(VALID_PLAN, {"round": 1}), (VALID_PLAN, {"round": 2})]) as planner, \
             patch.object(fp, "run_executor", side_effect=[(blocked, "blocked"), (completed, "completed")]) as executor:
            result = fp.cmd_run(self._args(tmp))
            saved_plan = json.loads((Path(tmp) / "plan.json").read_text())
            saved_report = json.loads((Path(tmp) / "report.json").read_text())
            saved_replan = json.loads((Path(tmp) / "report.replan-1.json").read_text())
        self.assertEqual(result, 0)
        self.assertEqual(planner.call_count, 2)
        self.assertEqual(executor.call_count, 2)
        self.assertEqual(saved_plan["replan"], 1)
        self.assertEqual(saved_report["status"], "completed")
        self.assertEqual(saved_replan["execution_report"]["status"], "blocked")
        self.assertEqual(saved_replan["previous_plan"], VALID_PLAN)

    def test_retryable_failure_does_not_trigger_strategic_replan(self):
        failed = {
            "report_type": "EXECUTION_REPORT", "status": "failed",
            "completed_steps": [], "failed_step": "S1", "evidence": [],
            "errors": ["retryable command error"], "deliverables": [],
            "replan_needed": False, "replan_reason": None,
        }
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(fp, "call_planner", return_value=(VALID_PLAN, {"round": 1})) as planner, \
             patch.object(fp, "run_executor", return_value=(failed, "failed")) as executor:
            result = fp.cmd_run(self._args(tmp))
        self.assertEqual(result, 2)
        planner.assert_called_once()
        executor.assert_called_once()


if __name__ == "__main__":
    unittest.main()
