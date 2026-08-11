#!/usr/bin/env python3
"""
Unit tests for Terraform Analyser
"""

import json
import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyse_terraform import (
    AnalysisConfig,
    CloudProviderDetector,
    TerraformAnalyser,
    resolve_analysis_preset
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
        config = AnalysisConfig(ai_provider="azure", azure_openai_api_key="test-key")
        self.assertEqual(
            config.analysis_focus,
            ['security', 'cost', 'best-practices', 'deployment']
        )

    def test_custom_analysis_focus(self):
        """Test custom analysis focus areas"""
        config = AnalysisConfig(
            ai_provider="azure",
            azure_openai_api_key="test-key",
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
            ai_provider="azure",
            azure_openai_api_key="test-key",
            azure_openai_endpoint="https://test.openai.azure.com",
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
        
        with patch.object(TerraformAnalyser, '_init_ai_client', return_value=Mock()), \
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
        
        with patch.object(TerraformAnalyser, '_init_ai_client', return_value=Mock()), \
             patch.object(TerraformAnalyser, '_validate_inputs', return_value=None):
            analyser = TerraformAnalyser(self.config)
            changes, _, action_counts = analyser.format_plan_changes(plan_data)
            
            self.assertEqual(action_counts['replace'], 1)
            self.assertEqual(changes[0]['action'], 'replace')


if __name__ == '__main__':
    unittest.main()
