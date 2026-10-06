#!/usr/bin/env python3
"""
Unit tests for Terraform Analyser
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock
from types import SimpleNamespace

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyse_terraform import (
    AnalysisConfig,
    CloudProviderDetector,
    TerraformAnalyser,
    load_config_from_env,
    normalise_plan_change,
    resolve_analysis_preset,
    severity_gate,
    summarise_report,
)


class TestCloudProviderDetector(unittest.TestCase):
    """Test cloud provider detection"""

    def test_detect_aws_from_tf_files(self):
        """Test AWS provider detection from Terraform files"""
        tf_files = {
            "main.tf": 'resource "aws_instance" "test" {}'
        }
        providers = CloudProviderDetector.detect_providers(tf_files)
        self.assertIn('aws', providers)

    def test_detect_azure_from_tf_files(self):
        """Test Azure provider detection from Terraform files"""
        tf_files = {
            "main.tf": 'resource "azurerm_resource_group" "test" {}'
        }
        providers = CloudProviderDetector.detect_providers(tf_files)
        self.assertIn('azure', providers)

    def test_detect_gcp_from_tf_files(self):
        """Test GCP provider detection from Terraform files"""
        tf_files = {
            "main.tf": 'resource "google_compute_instance" "test" {}'
        }
        providers = CloudProviderDetector.detect_providers(tf_files)
        self.assertIn('gcp', providers)

    def test_detect_from_plan_data(self):
        """Test provider detection from plan data when no TF files"""
        plan_data = {
            "resource_changes": [
                {"type": "aws_instance"},
                {"type": "aws_s3_bucket"}
            ]
        }
        providers = CloudProviderDetector.detect_providers({}, plan_data)
        self.assertIn('aws', providers)

    def test_primary_provider_single(self):
        """Test primary provider selection with single provider"""
        primary = CloudProviderDetector.get_primary_provider(['aws'])
        self.assertEqual(primary, 'aws')

    def test_primary_provider_multiple(self):
        """Test primary provider selection with multiple providers"""
        primary = CloudProviderDetector.get_primary_provider(['kubernetes', 'aws', 'azure'])
        self.assertEqual(primary, 'aws')

    def test_detect_unknown_provider_from_plan(self):
        """Test dynamic detection of unknown providers from plan data"""
        plan_data = {
            "resource_changes": [
                {"type": "datadog_monitor"},
                {"type": "datadog_dashboard"}
            ]
        }
        providers = CloudProviderDetector.detect_providers({}, plan_data)
        self.assertIn('datadog', providers)

    def test_detect_mixed_known_and_unknown_providers(self):
        """Test detection of both known and unknown providers"""
        plan_data = {
            "resource_changes": [
                {"type": "aws_instance"},
                {"type": "vault_generic_secret"},
                {"type": "random_string"}
            ]
        }
        providers = CloudProviderDetector.detect_providers({}, plan_data)
        self.assertIn('aws', providers)
        self.assertIn('vault', providers)
        self.assertIn('random', providers)

    def test_ignore_terraform_meta_types(self):
        """Test that Terraform meta types are ignored"""
        plan_data = {
            "resource_changes": [
                {"type": "data.aws_ami.latest"},
                {"type": "aws_instance"}
            ]
        }
        providers = CloudProviderDetector.detect_providers({}, plan_data)
        self.assertIn('aws', providers)
        self.assertNotIn('data', providers)

    def test_providers_sorted_alphabetically(self):
        """Test that providers are returned in sorted order"""
        plan_data = {
            "resource_changes": [
                {"type": "kubernetes_deployment"},
                {"type": "aws_instance"},
                {"type": "azurerm_resource_group"}
            ]
        }
        providers = CloudProviderDetector.detect_providers({}, plan_data)
        self.assertEqual(providers, sorted(providers))


class TestAnalysisConfig(unittest.TestCase):
    """Test analysis configuration"""

    def test_default_analysis_focus(self):
        """Test default analysis focus areas"""
        config = AnalysisConfig(ai_provider="foundry-openai", foundry_api_key="test-key", foundry_endpoint="https://test.services.ai.azure.com", foundry_deployment="review-model")
        self.assertEqual(
            config.analysis_focus,
            ['security', 'cost', 'best-practices', 'deployment']
        )

    def test_custom_analysis_focus(self):
        """Test custom analysis focus areas"""
        config = AnalysisConfig(
            ai_provider="foundry-openai",
            foundry_api_key="test-key",
            foundry_endpoint="https://test.services.ai.azure.com",
            foundry_deployment="review-model",
            analysis_focus=['security', 'compliance']
        )
        self.assertEqual(config.analysis_focus, ['security', 'compliance'])


class TestAnalysisPresets(unittest.TestCase):
    """Test analysis preset resolution"""

    def test_security_audit_preset(self):
        """Test security audit preset"""
        focus = resolve_analysis_preset("security-audit", "")
        self.assertEqual(focus, "security,compliance,governance")

    def test_cost_optimisation_preset(self):
        """Test cost optimisation preset"""
        focus = resolve_analysis_preset("cost-optimisation", "")
        self.assertEqual(focus, "cost,performance,data")

    def test_production_ready_preset(self):
        """Test production ready preset"""
        focus = resolve_analysis_preset("production-ready", "")
        self.assertEqual(focus, "security,reliability,deployment,observability,performance")

    def test_quick_check_preset(self):
        """Test quick check preset"""
        focus = resolve_analysis_preset("quick-check", "")
        self.assertEqual(focus, "security,best-practices")

    def test_complete_preset(self):
        """Test complete preset"""
        focus = resolve_analysis_preset("complete", "")
        expected = "security,cost,best-practices,deployment,compliance,performance,reliability,observability,networking,data,governance"
        self.assertEqual(focus, expected)

    def test_unknown_preset_fallback(self):
        """Test unknown preset falls back to explicit focus"""
        focus = resolve_analysis_preset("unknown-preset", "security,cost")
        self.assertEqual(focus, "security,cost")

    def test_empty_preset_uses_explicit(self):
        """Test empty preset uses explicit focus"""
        focus = resolve_analysis_preset("", "security,cost")
        self.assertEqual(focus, "security,cost")


class TestTerraformAnalyser(unittest.TestCase):
    """Test Terraform analyser functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.config = AnalysisConfig(
            ai_provider="foundry-openai",
            foundry_api_key="test-key",
            foundry_endpoint="https://test.services.ai.azure.com",
            foundry_deployment="review-model",
            terraform_plan_path="test_plan.json"
        )

    def test_format_plan_changes(self):
        """Test plan changes formatting"""
        plan_data = {
            "resource_changes": [
                {
                    "type": "aws_instance",
                    "name": "test",
                    "address": "aws_instance.test",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"ami": "ami-123"}
                    }
                }
            ]
        }
        
        with patch.object(TerraformAnalyser, '_init_openai_client', return_value=Mock()), \
             patch.object(TerraformAnalyser, '_validate_inputs', return_value=None):
            analyser = TerraformAnalyser(self.config)
            changes, resource_types, action_counts = analyser.format_plan_changes(plan_data)
            
            self.assertEqual(len(changes), 1)
            self.assertIn('aws_instance', resource_types)
            self.assertEqual(action_counts['create'], 1)

    def test_format_plan_replace_action(self):
        """Test detection of replace actions"""
        plan_data = {
            "resource_changes": [
                {
                    "type": "aws_instance",
                    "name": "test",
                    "address": "aws_instance.test",
                    "change": {
                        "actions": ["delete", "create"],
                        "before": {"ami": "ami-old"},
                        "after": {"ami": "ami-new"}
                    }
                }
            ]
        }
        
        with patch.object(TerraformAnalyser, '_init_openai_client', return_value=Mock()), \
             patch.object(TerraformAnalyser, '_validate_inputs', return_value=None):
            analyser = TerraformAnalyser(self.config)
            changes, _, action_counts = analyser.format_plan_changes(plan_data)
            
            self.assertEqual(action_counts['replace'], 1)
            self.assertEqual(changes[0]['action'], 'replace')


class TestTerraformEvidence(unittest.TestCase):
    """Test scrubbed, change-level Terraform evidence normalisation"""

    def setUp(self):
        """Set up test fixtures"""
        self.config = AnalysisConfig(
            ai_provider="foundry-openai",
            foundry_api_key="test-key",
            foundry_endpoint="https://test.services.ai.azure.com",
            foundry_deployment="review-model",
            terraform_plan_path="test_plan.json"
        )

    # -- normalise_plan_change --------------------------------------------

    def test_normalise_plan_change_masks_sensitive_and_unknown_values(self):
        """Sensitive values are redacted and unknown planned values are masked"""
        item = normalise_plan_change({
            "address": "aws_db_instance.primary", "type": "aws_db_instance",
            "change": {"actions": ["update"],
                       "before": {"password": "old", "allocated_storage": 20},
                       "after": {"password": "new", "allocated_storage": 40, "endpoint": None},
                       "before_sensitive": {"password": True},
                       "after_sensitive": {"password": True},
                       "after_unknown": {"endpoint": True}},
        })
        self.assertEqual(item["before"]["password"], "<redacted-sensitive>")
        self.assertEqual(item["after"]["password"], "<redacted-sensitive>")
        self.assertEqual(item["after"]["endpoint"], "<unknown-until-apply>")
        self.assertIn("allocated_storage", item["changed_paths"])

    def test_normalise_plan_change_returns_expected_shape(self):
        """Return value exposes exactly the interface described by the task"""
        item = normalise_plan_change({
            "address": "aws_instance.web", "type": "aws_instance",
            "change": {"actions": ["update"],
                       "before": {"instance_type": "t2.micro"},
                       "after": {"instance_type": "t2.small"}},
        })
        self.assertEqual(
            set(item.keys()),
            {"address", "resource_type", "action", "changed_paths", "before", "after"}
        )
        self.assertEqual(item["address"], "aws_instance.web")
        self.assertEqual(item["resource_type"], "aws_instance")
        self.assertEqual(item["action"], "update")

    def test_normalise_plan_change_collapses_delete_create_to_replace(self):
        """A delete+create action pair normalises to a single replace action"""
        item = normalise_plan_change({
            "address": "aws_instance.web", "type": "aws_instance",
            "change": {"actions": ["delete", "create"],
                       "before": {"ami": "ami-old"},
                       "after": {"ami": "ami-new"}},
        })
        self.assertEqual(item["action"], "replace")

    def test_normalise_plan_change_excludes_noop(self):
        """No-op changes are excluded entirely (return None)"""
        item = normalise_plan_change({
            "address": "aws_instance.web", "type": "aws_instance",
            "change": {"actions": ["no-op"],
                       "before": {"ami": "ami-1"},
                       "after": {"ami": "ami-1"}},
        })
        self.assertIsNone(item)

    def test_normalise_plan_change_nested_changed_paths(self):
        """Nested list/dict diffs produce dotted+bracketed paths"""
        item = normalise_plan_change({
            "address": "aws_instance.web", "type": "aws_instance",
            "change": {
                "actions": ["update"],
                "before": {"network_interface": [{"private_ip": "10.0.0.1"}]},
                "after": {"network_interface": [{"private_ip": "10.0.0.2"}]},
            },
        })
        self.assertIn("network_interface[0].private_ip", item["changed_paths"])

    def test_normalise_plan_change_masks_nested_sensitive_values(self):
        """Sensitive marks nested inside lists/dicts are still masked"""
        item = normalise_plan_change({
            "address": "aws_secretsmanager_secret_version.creds",
            "type": "aws_secretsmanager_secret_version",
            "change": {
                "actions": ["update"],
                "before": {"secret_list": [{"value": "old-secret"}]},
                "after": {"secret_list": [{"value": "new-secret"}]},
                "before_sensitive": {"secret_list": [{"value": True}]},
                "after_sensitive": {"secret_list": [{"value": True}]},
            },
        })
        self.assertEqual(item["before"]["secret_list"][0]["value"], "<redacted-sensitive>")
        self.assertEqual(item["after"]["secret_list"][0]["value"], "<redacted-sensitive>")

    def test_normalise_plan_change_excludes_unchanged_fields_from_evidence(self):
        """Evidence is reduced to changed fields only, keeping it bounded"""
        item = normalise_plan_change({
            "address": "aws_db_instance.primary", "type": "aws_db_instance",
            "change": {
                "actions": ["update"],
                "before": {"password": "old", "allocated_storage": 20, "engine": "postgres"},
                "after": {"password": "new", "allocated_storage": 40, "engine": "postgres"},
            },
        })
        self.assertNotIn("engine", item["before"])
        self.assertNotIn("engine", item["after"])
        self.assertIn("allocated_storage", item["before"])
        self.assertIn("allocated_storage", item["after"])

    # -- create_analysis_prompt evidence blocks ----------------------------

    def test_prompt_contains_change_values_but_not_sensitive_secret(self):
        """The prompt surfaces changed values but never the raw sensitive value"""
        normalised_change = normalise_plan_change({
            "address": "aws_db_instance.primary", "type": "aws_db_instance",
            "change": {"actions": ["update"],
                       "before": {"password": "old-secret-value", "allocated_storage": 20},
                       "after": {"password": "new-secret-value", "allocated_storage": 40, "endpoint": None},
                       "before_sensitive": {"password": True},
                       "after_sensitive": {"password": True},
                       "after_unknown": {"endpoint": True}},
        })
        counts = {"create": 0, "update": 1, "delete": 0, "replace": 0, "no-op": 0}

        with patch.object(TerraformAnalyser, '_init_openai_client', return_value=Mock()), \
             patch.object(TerraformAnalyser, '_validate_inputs', return_value=None):
            analyser = TerraformAnalyser(self.config)
            prompt = analyser.create_analysis_prompt({}, {}, [normalised_change], [], counts, ["aws"])

        self.assertIn("allocated_storage", prompt)
        self.assertIn("<redacted-sensitive>", prompt)
        self.assertIn("<unknown-until-apply>", prompt)
        self.assertNotIn("old-secret-value", prompt)
        self.assertNotIn("new-secret-value", prompt)

    def test_prompt_includes_every_accepted_change(self):
        """A single review request must account for every accepted plan change."""
        normalised_changes = [
            normalise_plan_change({
                "address": f"aws_instance.web{i}", "type": "aws_instance",
                "change": {"actions": ["update"],
                           "before": {"instance_type": "t2.micro"},
                           "after": {"instance_type": f"t2.small{i}"}},
            })
            for i in range(15)
        ]
        counts = {"create": 0, "update": 15, "delete": 0, "replace": 0, "no-op": 0}

        with patch.object(TerraformAnalyser, '_init_openai_client', return_value=Mock()), \
             patch.object(TerraformAnalyser, '_validate_inputs', return_value=None):
            analyser = TerraformAnalyser(self.config)
            prompt = analyser.create_analysis_prompt({}, {}, normalised_changes, [], counts, ["aws"])

        for i in range(15):
            self.assertIn(f"aws_instance.web{i}", prompt)
        self.assertNotIn("more changes", prompt)

    def test_prompt_packing_preserves_all_changes_and_respects_resource_cap(self):
        changes = [normalise_plan_change({
            "address": f"aws_instance.web{index}", "type": "aws_instance",
            "change": {"actions": ["create"], "before": None, "after": {"name": f"web-{index}"}},
        }) for index in range(201)]
        config = AnalysisConfig(
            foundry_api_key="key", foundry_endpoint="https://example.services.ai.azure.com",
            foundry_deployment="review-model", max_resources_per_request=100,
        )
        counts = {"create": 201, "update": 0, "delete": 0, "replace": 0, "no-op": 0}
        with patch.object(TerraformAnalyser, '_init_openai_client', return_value=Mock()), \
             patch.object(TerraformAnalyser, '_validate_inputs', return_value=None):
            analyser = TerraformAnalyser(config)
            batches = analyser.build_prompt_batches({}, changes, ["aws_instance"], counts, ["aws"], {})
        self.assertEqual(len(batches), 3)
        self.assertTrue(all(len(batch) <= 120000 for batch in batches))
        combined = "\n".join(batches)
        for index in range(201):
            self.assertEqual(combined.count(f"**Resource:** aws_instance.web{index}\n"), 1)

    def test_completed_review_writes_renderable_coverage_metadata(self):
        plan = {
            "resource_changes": [
                {
                    "address": f"aws_instance.web{index}", "type": "aws_instance",
                    "change": {"actions": ["create"], "before": None,
                               "after": {"instance_type": "t3.micro"}},
                }
                for index in range(12)
            ]
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            plan_path = os.path.join(tmp_dir, "plan.json")
            with open(plan_path, "w") as plan_file:
                json.dump(plan, plan_file)
            config = AnalysisConfig(
                foundry_api_key="key", foundry_endpoint="https://example.services.ai.azure.com",
                foundry_deployment="review-model", terraform_plan_path=plan_path,
                analysis_preset="production-ready", analysis_focus=["security", "reliability"],
                analysis_mode="comprehensive", analysis_depth="detailed", analysis_style="domain",
            )
            previous_directory = os.getcwd()
            try:
                os.chdir(tmp_dir)
                with patch.object(TerraformAnalyser, '_validate_inputs', return_value=None), \
                     patch.object(TerraformAnalyser, '_init_openai_client', return_value=Mock()), \
                     patch.object(TerraformAnalyser, 'read_terraform_files', return_value={"main.tf": "resource \"aws_instance\" \"web\" {}"}), \
                     patch.object(TerraformAnalyser, 'analyse_with_ai', return_value="## Recommendations (🔵)\n- Review complete"):
                    result = TerraformAnalyser(config).run_analysis()
            finally:
                os.chdir(previous_directory)
        summary = result["summary"]
        self.assertEqual(summary["review_status"], "complete")
        self.assertEqual(summary["reviewed_resource_changes"], 12)
        self.assertEqual(summary["resource_changes"], 12)
        self.assertEqual(summary["review_batches"], 1)
        self.assertEqual(summary["source_files_included"], 1)
        self.assertEqual(summary["review_configuration"]["analysis_preset"], "production-ready")

    def test_comprehensive_prompt_includes_every_selected_source_file(self):
        """Every file accepted by source limits reaches the Foundry prompt."""
        tf_files = {f"{index}.tf": f"resource-{index}-" + ("x" * 1600) for index in range(6)}
        counts = {"create": 0, "update": 0, "delete": 0, "replace": 0, "no-op": 0}
        self.config.analysis_mode = "comprehensive"
        with patch.object(TerraformAnalyser, '_init_openai_client', return_value=Mock()), \
             patch.object(TerraformAnalyser, '_validate_inputs', return_value=None):
            analyser = TerraformAnalyser(self.config)
            prompt = analyser.create_analysis_prompt(tf_files, {}, [], [], counts, ["aws"])
        self.assertIn("5.tf", prompt)
        self.assertIn("resource-5-", prompt)
        self.assertIn("x" * 1600, prompt)

    def test_domain_style_changes_requested_report_organisation(self):
        counts = {"create": 0, "update": 0, "delete": 0, "replace": 0, "no-op": 0}
        config = AnalysisConfig(
            foundry_api_key="key",
            foundry_endpoint="https://example.services.ai.azure.com",
            foundry_deployment="review-model",
            analysis_style="domain",
        )
        with patch.object(TerraformAnalyser, '_init_openai_client', return_value=Mock()), \
             patch.object(TerraformAnalyser, '_validate_inputs', return_value=None):
            analyser = TerraformAnalyser(config)
            prompt = analyser.create_analysis_prompt({}, {}, [], [], counts, ["aws"])
        self.assertIn("level-two headings for each requested analysis domain", prompt)
        self.assertNotIn("`## Critical Issues (🔴)`", prompt)

    def test_prompt_includes_evidence_limits_notice(self):
        """The prompt tells the model evidence is bounded to what is included"""
        counts = {"create": 0, "update": 0, "delete": 0, "replace": 0, "no-op": 0}

        with patch.object(TerraformAnalyser, '_init_openai_client', return_value=Mock()), \
             patch.object(TerraformAnalyser, '_validate_inputs', return_value=None):
            analyser = TerraformAnalyser(self.config)
            prompt = analyser.create_analysis_prompt({}, {}, [], [], counts, ["aws"])

        self.assertIn(
            "Evidence limits: only included changes and source files may support findings",
            prompt
        )

    def test_source_scrubbing_cannot_be_disabled_by_environment(self):
        with patch.object(TerraformAnalyser, '_init_openai_client', return_value=Mock()), \
             patch.object(TerraformAnalyser, '_validate_inputs', return_value=None), \
             patch.dict(os.environ, {"SCRUB_SENSITIVE_DATA": "false"}):
            analyser = TerraformAnalyser(self.config)
            scrubbed = analyser._scrub_sensitive_data('password = "plaintext-secret"')
        self.assertNotIn("plaintext-secret", scrubbed)

    # -- source-file selection ---------------------------------------------

    def test_changed_terraform_directory_does_not_alter_source_file_selection(self):
        """A legacy changed_terraform/ directory in cwd must not affect file selection"""
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                os.chdir(tmp_dir)

                tf_dir = os.path.join(tmp_dir, "infra")
                os.makedirs(tf_dir)
                with open(os.path.join(tf_dir, "main.tf"), "w") as f:
                    f.write('resource "aws_instance" "test" {}')

                # Legacy changed_terraform directory, unrelated to terraform_directory
                os.makedirs("changed_terraform")
                with open(os.path.join("changed_terraform", "main.tf"), "w") as f:
                    f.write('resource "aws_instance" "should_not_appear" {}')

                config = AnalysisConfig(
                    ai_provider="foundry-openai",
                    foundry_api_key="test-key",
                    foundry_endpoint="https://test.services.ai.azure.com",
                    foundry_deployment="review-model",
                    terraform_plan_path="test_plan.json",
                    terraform_directory=tf_dir,
                    analysis_mode="comprehensive",
                )

                with patch.object(TerraformAnalyser, '_init_openai_client', return_value=Mock()), \
                     patch.object(TerraformAnalyser, '_validate_inputs', return_value=None):
                    analyser = TerraformAnalyser(config)
                    tf_files = analyser.read_terraform_files()

                self.assertEqual(list(tf_files.keys()), ["main.tf"])
                self.assertNotIn("should_not_appear", tf_files["main.tf"])
            finally:
                os.chdir(original_cwd)


class TestFoundryConfiguration(unittest.TestCase):
    def test_foundry_client_disables_sdk_retries(self):
        config = AnalysisConfig(
            foundry_api_key="key",
            foundry_endpoint="https://example.services.ai.azure.com",
            foundry_deployment="review-model",
        )
        openai_constructor = Mock()
        fake_openai_module = SimpleNamespace(OpenAI=openai_constructor)
        with patch.dict(sys.modules, {"openai": fake_openai_module}):
            analyser = object.__new__(TerraformAnalyser)
            analyser.config = config
            analyser._init_openai_client()
        self.assertEqual(openai_constructor.call_args.kwargs["max_retries"], 0)

    def test_load_config_reads_depth_and_foundry_values(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plan_path = os.path.join(tmp_dir, "plan.json")
            with open(plan_path, "w") as plan_file:
                json.dump({"format_version": "1.2"}, plan_file)
            with patch.dict(os.environ, {
                "AI_PROVIDER": "foundry-openai",
                "FOUNDRY_API_KEY": "key",
                "FOUNDRY_ENDPOINT": "https://example.services.ai.azure.com",
                "FOUNDRY_DEPLOYMENT": "review-model",
                "ANALYSIS_DEPTH": "quick",
                "TERRAFORM_PLAN_PATH": plan_path,
            }, clear=True):
                config = load_config_from_env()
        self.assertEqual(config.analysis_depth, "quick")
        self.assertEqual(config.foundry_deployment, "review-model")
        self.assertEqual(config.analysis_mode, "plan-only")
        self.assertEqual(config.target_prompt_chars, 100000)
        self.assertEqual(config.max_prompt_chars, 120000)

    def test_quick_depth_changes_foundry_request(self):
        config = AnalysisConfig(
            foundry_api_key="key",
            foundry_endpoint="https://example.services.ai.azure.com",
            foundry_deployment="review-model",
            analysis_depth="quick",
        )
        response = Mock()
        response.choices = [Mock(message=Mock(content="review"))]
        client = Mock()
        client.chat.completions.create.return_value = response
        with patch.object(TerraformAnalyser, '_validate_inputs', return_value=None), \
             patch.object(TerraformAnalyser, '_init_openai_client', return_value=client):
            analyser = TerraformAnalyser(config)
            self.assertEqual(analyser.analyse_with_ai("evidence"), "review")
        call = client.chat.completions.create.call_args.kwargs
        self.assertEqual(call["model"], "review-model")
        self.assertEqual(call["max_completion_tokens"], 4000)
        self.assertNotIn("max_tokens", call)
        self.assertNotIn("temperature", call)
        self.assertNotIn("presence_penalty", call)
        self.assertNotIn("frequency_penalty", call)

    def test_detailed_depth_limits_foundry_response_to_12000_tokens(self):
        config = AnalysisConfig(
            foundry_api_key="key",
            foundry_endpoint="https://example.services.ai.azure.com",
            foundry_deployment="review-model",
            analysis_depth="detailed",
        )
        response = Mock()
        response.choices = [Mock(message=Mock(content="review"))]
        client = Mock()
        client.chat.completions.create.return_value = response
        with patch.object(TerraformAnalyser, '_validate_inputs', return_value=None), \
             patch.object(TerraformAnalyser, '_init_openai_client', return_value=client):
            analyser = TerraformAnalyser(config)
            analyser.analyse_with_ai("evidence")
        self.assertEqual(client.chat.completions.create.call_args.kwargs["max_completion_tokens"], 12000)

    def test_foundry_failure_is_not_returned_as_successful_review(self):
        config = AnalysisConfig(
            foundry_api_key="key",
            foundry_endpoint="https://example.services.ai.azure.com",
            foundry_deployment="review-model",
        )
        client = Mock()
        client.chat.completions.create.side_effect = RuntimeError("provider unavailable")
        with patch.object(TerraformAnalyser, '_validate_inputs', return_value=None), \
             patch.object(TerraformAnalyser, '_init_openai_client', return_value=client), \
             patch.dict(os.environ, {"API_MAX_RETRIES": "1"}):
            analyser = TerraformAnalyser(config)
            with self.assertRaisesRegex(RuntimeError, "AI API failed"):
                analyser.analyse_with_ai("evidence")

    def test_empty_foundry_completion_is_not_returned_as_successful_review(self):
        config = AnalysisConfig(
            foundry_api_key="key",
            foundry_endpoint="https://example.services.ai.azure.com",
            foundry_deployment="review-model",
        )
        response = Mock()
        response.choices = [Mock(message=Mock(content=""), finish_reason="length")]
        client = Mock()
        client.chat.completions.create.return_value = response
        with patch.object(TerraformAnalyser, '_validate_inputs', return_value=None), \
             patch.object(TerraformAnalyser, '_init_openai_client', return_value=client), \
             patch.dict(os.environ, {"API_MAX_RETRIES": "1"}):
            analyser = TerraformAnalyser(config)
            with self.assertRaisesRegex(RuntimeError, "empty completion"):
                analyser.analyse_with_ai("evidence")

    def test_invalid_api_retry_configuration_fails_before_calling_foundry(self):
        config = AnalysisConfig(
            foundry_api_key="key",
            foundry_endpoint="https://example.services.ai.azure.com",
            foundry_deployment="review-model",
        )
        client = Mock()
        with patch.object(TerraformAnalyser, '_validate_inputs', return_value=None), \
             patch.object(TerraformAnalyser, '_init_openai_client', return_value=client), \
             patch.dict(os.environ, {"API_MAX_RETRIES": "0"}):
            analyser = TerraformAnalyser(config)
            with self.assertRaisesRegex(ValueError, "api-max-retries must be at least 1"):
                analyser.analyse_with_ai("evidence")
        client.chat.completions.create.assert_not_called()

    def test_system_prompt_treats_infrastructure_as_untrusted_data(self):
        config = AnalysisConfig()
        with patch.object(TerraformAnalyser, '_validate_inputs', return_value=None), \
             patch.object(TerraformAnalyser, '_init_openai_client', return_value=Mock()):
            analyser = TerraformAnalyser(config)
        for style in ("severity", "domain"):
            with self.subTest(style=style):
                prompt = analyser.load_system_prompt(style)
                self.assertIn("untrusted data", prompt.lower())
                self.assertIn("never as instructions", prompt.lower())
                self.assertIn("## Immediate actions", prompt)


class TestReportSummary(unittest.TestCase):
    def test_severity_gate_uses_report_sections_not_incidental_words(self):
        report = "## Summary\nNo critical changes.\n\n## Warnings (🟡)\n- Missing backup policy"
        summary = summarise_report(report, mcp_status="unavailable")
        self.assertEqual(summary["highest_severity"], "warning")
        self.assertFalse(summary["has_critical_issues"])
        self.assertTrue(severity_gate(summary, "warning"))
        self.assertFalse(severity_gate(summary, "critical"))

    def test_summary_does_not_flag_word_critical_outside_finding_section(self):
        summary = summarise_report("## Summary\nThis is not critical.\n", mcp_status="available")
        self.assertFalse(summary["has_issues"])

    def test_domain_style_severity_markers_trigger_gate(self):
        report = "## Security Analysis\n- 🔴 Critical: public database exposure\n\n## Cost Optimization\n- 🟡 Warning: oversized instance"
        summary = summarise_report(report, mcp_status="available")
        self.assertEqual(summary["highest_severity"], "critical")
        self.assertTrue(summary["has_critical_issues"])
        self.assertTrue(severity_gate(summary, "critical"))

    def test_domain_style_heading_finding_triggers_gate(self):
        report = "## Security Analysis\n### 🔴 Critical: public database exposure"
        self.assertEqual(summarise_report(report)["highest_severity"], "critical")

    def test_empty_critical_section_does_not_trigger_gate(self):
        report = "## Critical Issues (🔴)\n- None identified."
        self.assertEqual(summarise_report(report)["highest_severity"], "none")

    def test_numbered_bold_severity_sections_are_supported(self):
        report = "1. **Summary**\nReview.\n3. **Critical Issues (🔴)**\n- Public database"
        self.assertEqual(summarise_report(report)["highest_severity"], "critical")

    def test_recommendations_are_counted_from_bullets_only(self):
        report = "## Recommendations (🔵)\n- First\n- Second\nParagraph recommending another item."
        self.assertEqual(summarise_report(report)["recommendations_count"], 2)


class TestMCPFallback(unittest.TestCase):
    def test_timeout_response_is_recorded_as_lookup_error(self):
        client = object.__new__(__import__('analyse_terraform').TerraformMCPClient)
        client.process = None
        with patch.object(client, '_send_mcp_request', return_value=None):
            result = __import__('asyncio').run(client._get_resource_specific_docs({
                "resource_changes": [{"type": "aws_instance"}]
            }))
        self.assertEqual(result["aws_instance"]["status"], "error")

    def test_all_failed_document_lookups_mark_enrichment_unavailable(self):
        client = object.__new__(__import__('analyse_terraform').TerraformMCPClient)
        client.process = None
        with patch.object(client, '_initialize_mcp', return_value=True), \
             patch.object(client, '_get_resource_specific_docs', return_value={
                 "aws_instance": {"status": "error", "error": "registry timeout"}
             }), \
             patch.object(client, '_cleanup_mcp', return_value=None):
            result = __import__('asyncio').run(client._validate_plan_async({}))
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("registry timeout", result["errors"])

    def test_unavailable_mcp_adds_notice_without_stopping_analysis(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plan_path = os.path.join(tmp_dir, "plan.json")
            with open(plan_path, "w") as plan_file:
                json.dump({"format_version": "1.2", "resource_changes": []}, plan_file)
            config = AnalysisConfig(
                foundry_api_key="key",
                foundry_endpoint="https://example.services.ai.azure.com",
                foundry_deployment="review-model",
                terraform_plan_path=plan_path,
                terraform_directory=tmp_dir,
                analysis_mode="plan-only",
            )
            original_cwd = os.getcwd()
            try:
                os.chdir(tmp_dir)
                with patch.object(TerraformAnalyser, '_init_openai_client', return_value=Mock()), \
                     patch.object(TerraformAnalyser, 'analyse_with_ai', return_value="## Summary\nNo findings."):
                    analyser = TerraformAnalyser(config)
                    analyser.mcp_client = Mock()
                    analyser.mcp_client.validate_plan_with_mcp.return_value = {
                        "status": "unavailable", "documents": [], "errors": ["Docker unavailable"]
                    }
                    result = analyser.run_analysis()
            finally:
                os.chdir(original_cwd)
        self.assertNotIn("error", result)
        self.assertIn("Documentation enrichment unavailable", result["analysis"])


if __name__ == '__main__':
    unittest.main()
