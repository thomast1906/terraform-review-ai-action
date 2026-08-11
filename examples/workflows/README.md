# Usage Examples

This directory contains example workflows demonstrating different use cases for the Terraform AI Review Action.

## Available Examples

1. **[basic-usage.yml](basic-usage.yml)** - Simple single-job workflow
2. **[multi-environment.yml](multi-environment.yml)** - Review multiple environments (dev/prod)
3. **[security-focused.yml](security-focused.yml)** - Security audit with automated issue creation

## How to Use

Copy any example to your `.github/workflows/` directory and customize as needed.

### Required Secrets

The action runs on [Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/), using either OpenAI-compatible models (e.g. GPT-5) or Claude models on the same Foundry resource:

- `AZURE_OPENAI_API_KEY` - Your Microsoft Foundry / Azure OpenAI API key
- `AZURE_OPENAI_ENDPOINT` - Your Foundry resource endpoint URL
- `AZURE_OPENAI_DEPLOYMENT` - Your model deployment name

Set `ai-provider: 'azure'` for OpenAI-compatible deployments (GPT-5 family), or `ai-provider: 'azure-anthropic'` for a Claude deployment on the same resource - see the [README](../../README.md#ai-provider) for details.

### Required Permissions

All workflows need these permissions:
```yaml
permissions:
  contents: read
  pull-requests: write
```
