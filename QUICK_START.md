# 🚀 Quick Start Guide

Get started with Terraform AI Review Action in under 5 minutes!

## Prerequisites

- GitHub repository with Terraform code
- Azure OpenAI access OR GitHub account (for GitHub Models)
- GitHub Actions enabled

## Step 1: Configure Secrets

### Option 1: GitHub Models (Recommended - No Setup Required!)

GitHub Models uses your existing GitHub token - no additional setup needed!

Just ensure your workflow has the `models: read` permission.

### Option 2: Azure OpenAI

Add your Azure OpenAI credentials to GitHub Secrets:

1. Go to your repository → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add these secrets:

```
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
```

## Step 2: Create Workflow File

Create `.github/workflows/terraform-review.yml`:

### Using GitHub Models (Simplest)

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
  models: read  # Required for GitHub Models

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      
      - uses: hashicorp/setup-terraform@v3
      
      - name: Generate Terraform Plan
        run: |
          terraform init
          terraform plan -out=tfplan.binary
          terraform show -json tfplan.binary > tfplan.json
      
      - name: AI Review
        uses: thomast1906/terraform-ai-review-action@v1
        with:
          ai-provider: 'github-models'
          github-models-token: ${{ secrets.GITHUB_TOKEN }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Using Azure OpenAI

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
      - uses: actions/checkout@v5
      
      - uses: hashicorp/setup-terraform@v3
      
      - name: Generate Terraform Plan
        run: |
          terraform init
          terraform plan -out=tfplan.binary
          terraform show -json tfplan.binary > tfplan.json
      
      - name: AI Review
        uses: thomast1906/terraform-ai-review-action@v1
        with:
          ai-provider: 'azure'
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
- uses: thomast1906/terraform-ai-review-action@v1
  with:
    ai-provider: 'github-models'
    github-models-token: ${{ secrets.GITHUB_TOKEN }}
    github-token: ${{ secrets.GITHUB_TOKEN }}
    analysis-preset: 'quick-check'
    analysis-depth: 'quick'
    analysis-mode: 'plan-only'
```

### Production Deployment Review (Thorough)
```yaml
- uses: thomast1906/terraform-ai-review-action@v1
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
- uses: thomast1906/terraform-ai-review-action@v1
  with:
    ai-provider: 'azure'
    azure-openai-api-key: ${{ secrets.AZURE_OPENAI_API_KEY }}
    azure-openai-endpoint: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
    azure-openai-deployment: ${{ secrets.AZURE_OPENAI_DEPLOYMENT }}
    github-token: ${{ secrets.GITHUB_TOKEN }}
    analysis-preset: 'cost-optimisation'
```

### Security Audit with GitHub Models
```yaml
- uses: thomast1906/terraform-ai-review-action@v1
  with:
    ai-provider: 'github-models'
    github-models-token: ${{ secrets.GITHUB_TOKEN }}
    github-models-model: 'gpt-4o'  # Or gpt-4o-mini for faster analysis
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
      - uses: actions/checkout@v5
      - uses: hashicorp/setup-terraform@v3
      
      - name: Terraform Plan
        working-directory: ${{ matrix.directory }}
        run: |
          terraform init
          terraform plan -out=tfplan.binary
          terraform show -json tfplan.binary > tfplan.json
      
      - uses: thomast1906/terraform-ai-review-action@v1
        with:
          ai-provider: 'github-models'
          github-models-token: ${{ secrets.GITHUB_TOKEN }}
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

### ❌ "GitHub Models 401 Unauthorized"
**Solution**: Add `models: read` permission to your workflow:
```yaml
permissions:
  contents: read
  pull-requests: write
  models: read  # Required for GitHub Models
```

### ❌ "Azure OpenAI API error"
**Solution**: Verify your secrets are correctly configured in GitHub Settings

### ❌ "No PR comment created"
**Solution**: Add `pull-requests: write` permission to your workflow

### ⚠️ "MCP server failed"
**Solution**: This is non-critical. Add `skip-mcp-validation: true` if it's causing issues

## AI Provider Comparison

| Feature | GitHub Models | Azure OpenAI |
|---------|--------------|--------------|
| **Setup** | ✅ No setup needed | ⚠️ Requires Azure account |
| **Cost** | ✅ Free (with limits) | 💰 Pay per token |
| **Models** | gpt-4o, gpt-4o-mini | Custom deployments |
| **Authentication** | GitHub token | API key |
| **Rate Limits** | GitHub tier-based | Your quota |

## What's Next?

- 📖 Read the [full documentation](README.md)
- 🎯 Check out [example workflows](examples/workflows/)
- ❓ See the [FAQ](FAQ.md)
- 🔧 Learn about [customisation options](README.md#analysis-modes)

## Need Help?

- 💬 [Start a discussion](https://github.com/thomast1906/terraform-ai-review-action/discussions)
- 🐛 [Report an issue](https://github.com/thomast1906/terraform-ai-review-action/issues)

---

**Happy Infrastructure Coding! 🏗️✨**
