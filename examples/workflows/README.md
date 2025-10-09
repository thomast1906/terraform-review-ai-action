# Usage Examples

This directory contains example workflows demonstrating different use cases for the Terraform AI Review Action.

## Available Examples

### Azure OpenAI Examples
1. **[basic-usage.yml](basic-usage.yml)** - Simple single-job workflow with Azure OpenAI
2. **[multi-environment.yml](multi-environment.yml)** - Review multiple environments (dev/prod)
3. **[security-focused.yml](security-focused.yml)** - Security audit with automated issue creation

### GitHub Models Examples
4. **[github-models.yml](github-models.yml)** - Basic workflow using GitHub Models
5. **[github-models-multi-env.yml](github-models-multi-env.yml)** - Multi-environment review with GitHub Models

## How to Use

Copy any example to your `.github/workflows/` directory and customize as needed.

### Required Secrets

For Azure OpenAI (recommended):
- `AZURE_OPENAI_API_KEY` - Your Azure OpenAI API key
- `AZURE_OPENAI_ENDPOINT` - Your Azure OpenAI endpoint URL
- `AZURE_OPENAI_DEPLOYMENT` - Your Azure OpenAI deployment name

For GitHub Models (alternative):
- `GH_MODELS_TOKEN` - GitHub token with models access (can use `secrets.GITHUB_TOKEN`)

### Required Permissions

All workflows need these permissions:
```yaml
permissions:
  contents: read
  pull-requests: write
  models: read  # Required for GitHub Models
```
