#!/usr/bin/env python3
"""
Metadata-contract tests for action.yml

These tests parse action.yml directly (never analyse_terraform.py) and assert
that the public input/output contract matches the v2, Foundry-only design:
every supported input is wired to the runtime environment, retired
Azure/GitHub Models provider inputs are gone, and the source-size limits
have exactly one canonical default.
"""

import os
import unittest
from pathlib import Path

import yaml

ACTION_YAML_PATH = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "action.yml"


def load_action_yaml():
    """Load and parse action.yml into a plain dict"""
    return yaml.safe_load(ACTION_YAML_PATH.read_text())


class TestActionMetadata(unittest.TestCase):
    """Test the v2 composite action contract defined in action.yml"""

    def test_foundry_inputs_and_runtime_wiring_are_present(self):
        action = load_action_yaml()
        self.assertEqual(action["inputs"]["ai-provider"]["default"], "foundry-openai")
        for name in ("foundry-api-key", "foundry-endpoint", "foundry-deployment"):
            self.assertIn(name, action["inputs"])

        runtime = next(step for step in action["runs"]["steps"] if step["name"] == "Run AI Analysis")
        self.assertEqual(runtime["env"]["FOUNDRY_API_KEY"], "${{ inputs.foundry-api-key }}")
        self.assertEqual(runtime["env"]["FOUNDRY_ENDPOINT"], "${{ inputs.foundry-endpoint }}")
        self.assertEqual(runtime["env"]["FOUNDRY_DEPLOYMENT"], "${{ inputs.foundry-deployment }}")
        self.assertEqual(runtime["env"]["ANALYSIS_DEPTH"], "${{ inputs.analysis-depth }}")
        self.assertEqual(runtime["env"]["FAIL_ON_SEVERITY"], "${{ inputs.fail-on-severity }}")

    def test_only_the_supported_v2_review_controls_are_public(self):
        action = load_action_yaml()
        self.assertIn("fail-on-severity", action["inputs"])
        self.assertEqual(action["inputs"]["fail-on-severity"]["default"], "none")
        self.assertFalse(action["inputs"]["github-token"]["required"])
        self.assertNotIn("github-models-token", action["inputs"])
        self.assertNotIn("github-models-model", action["inputs"])
        self.assertNotIn("azure-openai-api-key", action["inputs"])
        self.assertNotIn("azure-openai-endpoint", action["inputs"])
        self.assertNotIn("azure-openai-api-version", action["inputs"])
        self.assertNotIn("azure-openai-deployment", action["inputs"])
        self.assertNotIn("mcp-server-timeout", action["inputs"])
        self.assertNotIn("show-mcp-details", action["inputs"])
        self.assertNotIn("analysis-focus", action["inputs"])
        self.assertNotIn("enable-data-scrubbing", action["inputs"])

    def test_source_limits_have_one_canonical_default(self):
        action = load_action_yaml()
        self.assertEqual(action["inputs"]["max-file-size-mb"]["default"], "10")
        self.assertEqual(action["inputs"]["max-total-size-mb"]["default"], "50")
        self.assertEqual(action["inputs"]["max-files"]["default"], "100")

    def test_review_scope_and_reporting_controls_are_retained(self):
        action = load_action_yaml()
        self.assertEqual(action["inputs"]["analysis-mode"]["default"], "plan-only")
        for name in (
            "terraform-plan-path",
            "terraform-directory",
            "analysis-preset",
            "analysis-mode",
            "analysis-depth",
            "analysis-style",
            "disable-pr-comment",
            "github-token",
        ):
            self.assertIn(name, action["inputs"])

    def test_action_outputs_expose_result_and_gate_signals(self):
        action = load_action_yaml()
        for name in ("analysis-result", "has-issues", "recommendations-count", "highest-severity"):
            self.assertIn(name, action["outputs"])

    def test_mcp_server_image_is_pinned_to_a_digest(self):
        action = load_action_yaml()
        mcp_step = next(step for step in action["runs"]["steps"] if step["name"] == "Start Terraform MCP Server")
        self.assertIn("hashicorp/terraform-mcp-server@sha256:", mcp_step["run"])
        self.assertNotIn("hashicorp/terraform-mcp-server:latest", mcp_step["run"])

    def test_analysis_output_uses_random_collision_checked_delimiter(self):
        action = load_action_yaml()
        runtime = next(step for step in action["runs"]["steps"] if step["name"] == "Run AI Analysis")
        self.assertIn("secrets.token_hex", runtime["run"])
        self.assertIn("while delimiter in analysis", runtime["run"])
        self.assertNotIn("ANALYSIS_EOF", runtime["run"])

    def test_virtual_environment_is_created_and_removed_outside_the_workspace(self):
        action = load_action_yaml()
        install = next(step for step in action["runs"]["steps"] if step["name"] == "Install dependencies")
        cleanup = next(step for step in action["runs"]["steps"] if step["name"] == "Cleanup")
        self.assertIn('mktemp -d "${RUNNER_TEMP:?}/terraform-ai-review.XXXXXX"', install["run"])
        self.assertIn("TERRAFORM_AI_VENV", install["run"])
        self.assertIn('"${RUNNER_TEMP:?}"/terraform-ai-review.*', cleanup["run"])
        self.assertNotIn("rm -rf terraform-ai-venv", cleanup["run"])


class TestMultiCloudWorkflow(unittest.TestCase):
    def test_ci_runs_four_foundry_fixture_reviews_and_combines_results(self):
        workflow_path = ACTION_YAML_PATH.parent / ".github/workflows/ci.yml"
        workflow = yaml.safe_load(workflow_path.read_text())
        review = workflow["jobs"]["multi-cloud-review"]
        matrix = review["strategy"]["matrix"]["include"]
        self.assertEqual({item["slug"] for item in matrix}, {"azure", "aws", "gcp", "other"})
        self.assertTrue(all(item["plan"].startswith("examples/terraform-plan-json/") for item in matrix))
        action_step = next(step for step in review["steps"] if step.get("uses") == "./")
        self.assertEqual(action_step["with"]["foundry-api-key"], "${{ secrets.AZURE_OPENAI_API_KEY }}")
        self.assertEqual(action_step["with"]["foundry-endpoint"], "${{ secrets.AZURE_OPENAI_ENDPOINT }}")
        self.assertEqual(action_step["with"]["foundry-deployment"], "${{ secrets.AZURE_OPENAI_DEPLOYMENT }}")
        self.assertEqual(action_step["with"]["disable-pr-comment"], "true")
        artifact_step = next(step for step in review["steps"] if step.get("uses") == "actions/upload-artifact@v7")
        self.assertIn("${{ github.run_attempt }}", artifact_step["with"]["name"])
        combine = workflow["jobs"]["combine-multi-cloud-review"]
        download_step = next(step for step in combine["steps"] if step.get("uses") == "actions/download-artifact@v8")
        self.assertIn("${{ github.run_attempt }}", download_step["with"]["pattern"])

    def test_ci_runs_domain_comprehensive_source_and_plan_review(self):
        workflow_path = ACTION_YAML_PATH.parent / ".github/workflows/ci.yml"
        workflow = yaml.safe_load(workflow_path.read_text())
        review = workflow["jobs"]["domain-comprehensive-review"]
        action_step = next(step for step in review["steps"] if step.get("uses") == "./")
        inputs = action_step["with"]
        self.assertEqual(inputs["analysis-mode"], "comprehensive")
        self.assertEqual(inputs["analysis-preset"], "complete")
        self.assertEqual(inputs["analysis-depth"], "detailed")
        self.assertEqual(inputs["analysis-style"], "domain")
        self.assertEqual(inputs["terraform-directory"], "examples")
        self.assertTrue(inputs["terraform-plan-path"].endswith("large_azure_100_resources_plan.json"))
        self.assertEqual(inputs["api-timeout-seconds"], "300")
        self.assertEqual(inputs["disable-pr-comment"], "true")
        publisher = workflow["jobs"]["publish-comprehensive-review"]
        self.assertEqual(publisher["needs"], ["domain-comprehensive-review"])
        script_step = next(step for step in publisher["steps"] if step.get("name") == "Publish comprehensive review")
        self.assertIn("60000", script_step["with"]["script"])
        self.assertIn("terraform-ai-azure-100-review", script_step["with"]["script"])

    def test_ci_gives_comprehensive_capability_fixture_a_longer_timeout(self):
        workflow_path = ACTION_YAML_PATH.parent / ".github/workflows/ci.yml"
        workflow = yaml.safe_load(workflow_path.read_text())
        review = workflow["jobs"]["capability-review"]
        matrix = review["strategy"]["matrix"]["include"]
        timeouts = {item["slug"]: item["timeout"] for item in matrix}
        self.assertEqual(timeouts["production"], "300")
        self.assertTrue(all(timeout == "120" for slug, timeout in timeouts.items() if slug != "production"))
        action_step = next(step for step in review["steps"] if step.get("uses") == "./")
        self.assertEqual(action_step["with"]["api-timeout-seconds"], "${{ matrix.timeout }}")


class TestDocumentationContract(unittest.TestCase):
    @staticmethod
    def _docs() -> str:
        return "\n".join(
            path.read_text()
            for path in [
                ACTION_YAML_PATH.parent / "README.md",
                *(ACTION_YAML_PATH.parent / "docs").glob("*.md"),
            ]
        )

    def test_docs_do_not_advertise_removed_provider_inputs(self):
        docs = self._docs()
        self.assertNotIn("github-models-token", docs)
        self.assertNotIn("azure-openai-api-key", docs)
        self.assertIn("foundry-deployment", docs)

    def test_docs_cover_every_public_input_and_output(self):
        action = load_action_yaml()
        docs = self._docs()
        for name in [*action["inputs"], *action["outputs"]]:
            self.assertIn(f"`{name}`", docs, name)


if __name__ == "__main__":
    unittest.main()
