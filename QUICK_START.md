# 🚀 Quick Start Guide

Get started with Terraform AI Review Action in under 5 minutes!

## Prerequisites

- GitHub repository with Terraform code
- A [Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/) resource with a model deployed (GPT-5 family, or Claude)
- GitHub Actions enabled

## Step 1: Configure Secrets

Add your Foundry credentials to GitHub Secrets:

1. Go to your repository → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add these secrets:

```
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource.services.ai.azure.com
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
```

The same three secrets work for both provider options below - only `ai-provider` and the deployment name change. Use your Azure AI Foundry resource endpoint (`.services.ai.azure.com`) - a classic Azure OpenAI-only resource (`.openai.azure.com`) won't serve the Claude (`azure-anthropic`) deployment.

## Step 2: Create Workflow File

Create `.github/workflows/terraform-review.yml`:

### Using GPT-5 family models

```yaml
name: Terraform AI Review

on:
  pull_request:
    paths:
      - '**.tf'
      - '**.tfvars'

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      
      - uses: hashicorp/setup-terraform@v3
      
      - name: Generate Terraform Plan
        run: |
          terraform init
          terraform plan -out=tfplan.binary
          terraform show -json tfplan.binary > tfplan.json
      
      - name: AI Review
        uses: thomast1906/terraform-review-ai-action@v2
        with:
          ai-provider: 'azure'
          azure-openai-api-key: ${{ secrets.AZURE_OPENAI_API_KEY }}
          azure-openai-endpoint: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
          azure-openai-deployment: ${{ secrets.AZURE_OPENAI_DEPLOYMENT }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Using Claude models

Same secrets, same Foundry resource - just switch the provider and deployment:

```yaml
name: Terraform AI Review

on:
  pull_request:
    paths:
      - '**.tf'
      - '**.tfvars'

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      
      - uses: hashicorp/setup-terraform@v3
      
      - name: Generate Terraform Plan
        run: |
          terraform init
          terraform plan -out=tfplan.binary
          terraform show -json tfplan.binary > tfplan.json
      
      - name: AI Review
        uses: thomast1906/terraform-review-ai-action@v2
        with:
          ai-provider: 'azure-anthropic'
          azure-openai-api-key: ${{ secrets.AZURE_OPENAI_API_KEY }}
          azure-openai-endpoint: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
          azure-openai-deployment: ${{ secrets.AZURE_OPENAI_DEPLOYMENT }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Step 3: Test It!

1. Create a new branch
2. Make a change to your Terraform files
3. Create a pull request
4. Watch the AI review appear as a comment! 🎉

## Common Configurations

### Quick Security Check (Fast)
```yaml
- uses: thomast1906/terraform-review-ai-action@v2
  with:
    ai-provider: 'azure'
    azure-openai-api-key: ${{ secrets.AZURE_OPENAI_API_KEY }}
    azure-openai-endpoint: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
    azure-openai-deployment: ${{ secrets.AZURE_OPENAI_DEPLOYMENT }}
    github-token: ${{ secrets.GITHUB_TOKEN }}
    analysis-preset: 'quick-check'
    analysis-depth: 'quick'
    analysis-mode: 'plan-only'
```

### Production Deployment Review (Thorough)
```yaml
- uses: thomast1906/terraform-review-ai-action@v2
  with:
    ai-provider: 'azure'
    azure-openai-api-key: ${{ secrets.AZURE_OPENAI_API_KEY }}
    azure-openai-endpoint: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
    azure-openai-deployment: ${{ secrets.AZURE_OPENAI_DEPLOYMENT }}
    github-token: ${{ secrets.GITHUB_TOKEN }}
    analysis-preset: 'production-ready'
    analysis-depth: 'detailed'
```

### Cost Optimisation Focus
```yaml
- uses: thomast1906/terraform-review-ai-action@v2
  with:
    ai-provider: 'azure'
    azure-openai-api-key: ${{ secrets.AZURE_OPENAI_API_KEY }}
    azure-openai-endpoint: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
    azure-openai-deployment: ${{ secrets.AZURE_OPENAI_DEPLOYMENT }}
    github-token: ${{ secrets.GITHUB_TOKEN }}
    analysis-preset: 'cost-optimisation'
```

### Security Audit with Claude
```yaml
- uses: thomast1906/terraform-review-ai-action@v2
  with:
    ai-provider: 'azure-anthropic'
    azure-openai-api-key: ${{ secrets.AZURE_OPENAI_API_KEY }}
    azure-openai-endpoint: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
    azure-openai-deployment: 'claude-sonnet-5'
    github-token: ${{ secrets.GITHUB_TOKEN }}
    analysis-preset: 'security-audit'
    analysis-depth: 'detailed'
```

## Multi-Directory Setup

If you have multiple Terraform directories:

```yaml
jobs:
  review:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        directory: [terraform/dev, terraform/staging, terraform/prod]
    steps:
      - uses: actions/checkout@v7
      - uses: hashicorp/setup-terraform@v3
      
      - name: Terraform Plan
        working-directory: ${{ matrix.directory }}
        run: |
          terraform init
          terraform plan -out=tfplan.binary
          terraform show -json tfplan.binary > tfplan.json
      
      - uses: thomast1906/terraform-review-ai-action@v2
        with:
          ai-provider: 'azure'
          azure-openai-api-key: ${{ secrets.AZURE_OPENAI_API_KEY }}
          azure-openai-endpoint: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
          azure-openai-deployment: ${{ secrets.AZURE_OPENAI_DEPLOYMENT }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
          terraform-plan-path: '${{ matrix.directory }}/tfplan.json'
          terraform-directory: '${{ matrix.directory }}'
```

## Troubleshooting

### ❌ "Terraform plan not found"
**Solution**: Ensure you run `terraform plan` and convert to JSON before the action:
```yaml
- run: |
    terraform plan -out=tfplan.binary
    terraform show -json tfplan.binary > tfplan.json
```

### ❌ "AI API error" / 401 Unauthorized
**Solution**: Verify `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, and `AZURE_OPENAI_DEPLOYMENT` are correctly configured in GitHub Settings, and that the deployment name matches what's deployed on your Foundry resource for the selected `ai-provider`.

### ❌ "No PR comment created"
**Solution**: Add `pull-requests: write` permission to your workflow

### ⚠️ "MCP server failed"
**Solution**: This is non-critical. Add `skip-mcp-validation: true` if it's causing issues

## AI Provider Comparison

| Feature | `azure` (GPT-5 family) | `azure-anthropic` (Claude) |
|---------|-------------------------|------------------------------|
| **Setup** | Foundry resource + deployment | Same Foundry resource + a Claude deployment |
| **API shape** | OpenAI-compatible (`/openai/v1/`) | Anthropic Messages API (`/anthropic`) |
| **Credentials** | `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` | Same secrets, same resource |
| **Billing** | Azure OpenAI consumption | Claude Consumption Units (Azure Marketplace) |

## What's Next?

- 📖 Read the [full documentation](README.md)
- 🎯 Check out [example workflows](examples/workflows/)
- ❓ See the [FAQ](FAQ.md)
- 🔧 Learn about [customisation options](README.md#analysis-modes)

## Need Help?

- 💬 [Start a discussion](https://github.com/thomast1906/terraform-review-ai-action/discussions)
- 🐛 [Report an issue](https://github.com/thomast1906/terraform-review-ai-action/issues)

---

**Happy Infrastructure Coding! 🏗️✨**
