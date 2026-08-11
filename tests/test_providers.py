#!/usr/bin/env python3
"""
Unit tests for AI provider dispatch: client construction, config validation,
and model-name / token-parameter resolution per provider.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyse_terraform import (
    AnalysisConfig,
    AzureOpenAIProvider,
    AzureAnthropicProvider,
    PROVIDERS,
    load_config_from_env,
)


class TestProviderRegistry(unittest.TestCase):
    """Provider registry only exposes the supported providers"""

    def test_registered_providers(self):
        self.assertEqual(set(PROVIDERS.keys()), {"azure", "azure-anthropic"})

    def test_github_models_not_registered(self):
        self.assertNotIn("github-models", PROVIDERS)


class TestAzureOpenAIProviderClient(unittest.TestCase):
    """Client construction for the OpenAI-compatible Foundry v1 endpoint"""

    def setUp(self):
        self.config = AnalysisConfig(
            ai_provider="azure",
            azure_openai_api_key="test-key",
            azure_openai_endpoint="https://my-resource.openai.azure.com",
        )

    def test_base_url_and_api_key(self):
        with patch("openai.OpenAI") as mock_openai:
            AzureOpenAIProvider().init_client(self.config)
            mock_openai.assert_called_once_with(
                api_key="test-key",
                base_url="https://my-resource.openai.azure.com/openai/v1/"
            )

    def test_trailing_slash_on_endpoint_is_normalised(self):
        self.config.azure_openai_endpoint = "https://my-resource.openai.azure.com/"
        with patch("openai.OpenAI") as mock_openai:
            AzureOpenAIProvider().init_client(self.config)
            mock_openai.assert_called_once_with(
                api_key="test-key",
                base_url="https://my-resource.openai.azure.com/openai/v1/"
            )

    def test_model_name_is_deployment(self):
        self.config.azure_openai_deployment = "gpt-5-mini"
        self.assertEqual(AzureOpenAIProvider().model_name(self.config), "gpt-5-mini")


class TestAzureAnthropicProviderClient(unittest.TestCase):
    """Client construction for Claude models on Foundry (Anthropic Messages API)"""

    def setUp(self):
        self.config = AnalysisConfig(
            ai_provider="azure-anthropic",
            azure_openai_api_key="test-key",
            azure_openai_endpoint="https://my-resource.services.ai.azure.com",
            azure_openai_deployment="claude-sonnet-5",
        )

    def test_base_url_and_api_key(self):
        with patch("anthropic.AnthropicFoundry") as mock_foundry:
            AzureAnthropicProvider().init_client(self.config)
            mock_foundry.assert_called_once_with(
                api_key="test-key",
                base_url="https://my-resource.services.ai.azure.com/anthropic"
            )

    def test_trailing_slash_on_endpoint_is_normalised(self):
        self.config.azure_openai_endpoint = "https://my-resource.services.ai.azure.com/"
        with patch("anthropic.AnthropicFoundry") as mock_foundry:
            AzureAnthropicProvider().init_client(self.config)
            mock_foundry.assert_called_once_with(
                api_key="test-key",
                base_url="https://my-resource.services.ai.azure.com/anthropic"
            )


class TestAzureOpenAITokenParamResolution(unittest.TestCase):
    """GPT-5 family models require max_completion_tokens instead of max_tokens"""

    def _completion_response(self, text="analysis result"):
        response = Mock()
        response.choices = [Mock(message=Mock(content=text))]
        return response

    def test_gpt5_uses_max_completion_tokens(self):
        client = Mock()
        client.chat.completions.create.return_value = self._completion_response()

        AzureOpenAIProvider().complete(
            client, "gpt-5-mini", "system", "user", 0.1, 8000, 120
        )

        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertIn("max_completion_tokens", kwargs)
        self.assertNotIn("max_tokens", kwargs)
        self.assertEqual(kwargs["max_completion_tokens"], 8000)

    def test_non_gpt5_uses_max_tokens(self):
        client = Mock()
        client.chat.completions.create.return_value = self._completion_response()

        AzureOpenAIProvider().complete(
            client, "gpt-4.1", "system", "user", 0.1, 8000, 120
        )

        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertIn("max_tokens", kwargs)
        self.assertNotIn("max_completion_tokens", kwargs)
        self.assertEqual(kwargs["max_tokens"], 8000)

    def test_returns_response_content(self):
        client = Mock()
        client.chat.completions.create.return_value = self._completion_response("hello world")

        result = AzureOpenAIProvider().complete(
            client, "gpt-5-mini", "system", "user", 0.1, 8000, 120
        )
        self.assertEqual(result, "hello world")

    def test_system_prompt_sent_as_message(self):
        client = Mock()
        client.chat.completions.create.return_value = self._completion_response()

        AzureOpenAIProvider().complete(
            client, "gpt-5-mini", "system content", "user content", 0.1, 8000, 120
        )

        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["messages"][0], {"role": "system", "content": "system content"})
        self.assertEqual(kwargs["messages"][1], {"role": "user", "content": "user content"})


class TestAzureAnthropicRequestShape(unittest.TestCase):
    """Claude uses a top-level system param and returns content blocks, not choices"""

    def test_system_prompt_is_top_level_not_a_message(self):
        client = Mock()
        text_block = Mock(type="text", text="analysis result")
        client.messages.create.return_value = Mock(content=[text_block])

        AzureAnthropicProvider().complete(
            client, "claude-sonnet-5", "system content", "user content", 0.1, 8000, 120
        )

        kwargs = client.messages.create.call_args.kwargs
        self.assertEqual(kwargs["system"], "system content")
        self.assertEqual(kwargs["messages"], [{"role": "user", "content": "user content"}])
        self.assertNotIn("max_completion_tokens", kwargs)
        self.assertEqual(kwargs["max_tokens"], 8000)

    def test_extracts_text_from_content_blocks(self):
        client = Mock()
        text_block = Mock(type="text", text="hello world")
        client.messages.create.return_value = Mock(content=[text_block])

        result = AzureAnthropicProvider().complete(
            client, "claude-sonnet-5", "system", "user", 0.1, 8000, 120
        )
        self.assertEqual(result, "hello world")

    def test_ignores_non_text_content_blocks(self):
        client = Mock()
        thinking_block = Mock(type="thinking", text="reasoning...")
        text_block = Mock(type="text", text="final answer")
        client.messages.create.return_value = Mock(content=[thinking_block, text_block])

        result = AzureAnthropicProvider().complete(
            client, "claude-sonnet-5", "system", "user", 0.1, 8000, 120
        )
        self.assertEqual(result, "final answer")


class TestLoadConfigFromEnv(unittest.TestCase):
    """Env-based config loading validates provider and required credentials"""

    def setUp(self):
        self.plan_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        )
        json.dump({"format_version": "1.0", "resource_changes": []}, self.plan_file)
        self.plan_file.close()

        self.base_env = {
            "AZURE_OPENAI_API_KEY": "test-key",
            "AZURE_OPENAI_ENDPOINT": "https://my-resource.openai.azure.com",
            "TERRAFORM_PLAN_PATH": self.plan_file.name,
        }

    def tearDown(self):
        os.unlink(self.plan_file.name)

    def test_defaults_to_azure_provider(self):
        with patch.dict(os.environ, self.base_env, clear=True):
            config = load_config_from_env()
        self.assertEqual(config.ai_provider, "azure")

    def test_accepts_azure_anthropic_provider(self):
        env = {**self.base_env, "AI_PROVIDER": "azure-anthropic"}
        with patch.dict(os.environ, env, clear=True):
            config = load_config_from_env()
        self.assertEqual(config.ai_provider, "azure-anthropic")

    def test_rejects_github_models_provider(self):
        env = {**self.base_env, "AI_PROVIDER": "github-models"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(SystemExit):
                load_config_from_env()

    def test_rejects_unknown_provider(self):
        env = {**self.base_env, "AI_PROVIDER": "openai-direct"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(SystemExit):
                load_config_from_env()

    def test_requires_api_key(self):
        env = {k: v for k, v in self.base_env.items() if k != "AZURE_OPENAI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(SystemExit):
                load_config_from_env()

    def test_requires_endpoint(self):
        env = {k: v for k, v in self.base_env.items() if k != "AZURE_OPENAI_ENDPOINT"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(SystemExit):
                load_config_from_env()

    def test_default_deployment_is_gpt5_mini(self):
        with patch.dict(os.environ, self.base_env, clear=True):
            config = load_config_from_env()
        self.assertEqual(config.azure_openai_deployment, "gpt-5-mini")

    def test_no_azure_openai_api_version_field(self):
        # v1 Foundry API removes the need for a dated api-version - confirm
        # the field doesn't linger as dead config.
        self.assertFalse(hasattr(AnalysisConfig(), "azure_openai_api_version"))


if __name__ == '__main__':
    unittest.main()
