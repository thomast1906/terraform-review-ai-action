# Terraform AI Plan Review Action

[![GitHub release](https://img.shields.io/github/release/thomast1906/terraform-review-ai-action.svg)](https://github.com/thomast1906/terraform-review-ai-action/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/thomast1906/terraform-review-ai-action/workflows/Build%20and%20Test/badge.svg)](https://github.com/thomast1906/terraform-review-ai-action/actions)

**Transform your Terraform workflows with Terraform AI analysis.** This GitHub Action delivers expert-level code reviews powered by [Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/) (GPT-5 family or Claude models, on the same Azure resource), integrated with HashiCorp's official MCP Server for real-time provider documentation and module registry access. 

**Analyse across 11 specialized domains** (security, cost, performance, reliability, compliance, observability, networking, data protection, governance, deployment safety, best practices) with **Customisable analysis presets** (security audit, cost optimisation, production-ready checks, quick scans), **flexible depth levels** (quick/standard/detailed), and **dual output styles** (severity-based or domain-grouped). 

**Every finding is automatically posted to your PRs** as intelligent comments with severity ratings, provider-specific recommendations, mitigation strategies, and compliance mappings. Works with **ANY Terraform provider**—from AWS, Azure, GCP, and Kubernetes to 1000+ community providers like Auth0, Datadog, MongoDB, Vault, and beyond. 

## Features

- 💬 **Automated PR Comments** - AI analysis posted directly to pull requests for team visibility
- 🤖 **Microsoft Foundry** - GPT-5 family or Claude models, on your own Azure resource
- 🏗️ **HashiCorp MCP** - Official Terraform MCP Server for enhanced validation
- 🌐 **Universal Support** - Works with any Terraform provider (AWS, Azure, GCP, Kubernetes, etc.)
- 🔒 **11 Focus Areas** - Security, cost, performance, reliability, compliance, and more
- ⚡ **Flexible Depth** - Quick, standard, or detailed analysis modes
- 📝 **Structured Output** - Severity-coded findings with actionable recommendations

## Example Outputs

See real-world analysis examples:

- [AWS Infrastructure](examples/outputs/aws-comprehensive.md) - Security, cost, compliance review
- [Azure Deployment](examples/outputs/azure-comprehensive.md) - Key Vault, networking analysis
- [GCP Multi-Cloud](examples/outputs/gcp-comprehensive.md) - Multi-provider infrastructure
- [Advanced Providers](examples/outputs/other-providers.md) - Auth0, Datadog, MongoDB, Vault, etc.

## Quick Start

### Basic Usage

```yaml
name: Terraform AI Review
on:
  pull_request:
    paths: ['**.tf', '**.tfvars']

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      
      - uses: hashicorp/setup-terraform@v3
      
      - name: Terraform Plan
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
          analysis-preset: 'production-ready'
          analysis-depth: 'detailed'
```

### Claude on Microsoft Foundry

Both providers run on the same Foundry resource (same endpoint and API key) - just switch `ai-provider` and point `azure-openai-deployment` at your Claude deployment:

```yaml
- uses: thomast1906/terraform-review-ai-action@v2
  with:
    ai-provider: 'azure-anthropic'
    azure-openai-api-key: ${{ secrets.AZURE_OPENAI_API_KEY }}
    azure-openai-endpoint: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
    azure-openai-deployment: 'claude-sonnet-5'
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Configuration

### Inputs

#### AI Provider
| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `ai-provider` | AI provider on Microsoft Foundry: `azure` (OpenAI-compatible models, e.g. GPT-5) or `azure-anthropic` (Claude models) | ❌ | `azure` |

#### Microsoft Foundry / Azure OpenAI
| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `azure-openai-api-key` | Foundry / Azure OpenAI API key | ✅ | - |
| `azure-openai-endpoint` | Foundry resource endpoint URL (e.g. `https://<resource>.services.ai.azure.com`) - must be an Azure AI Foundry resource, not a classic Azure OpenAI-only resource, since `azure-anthropic` requires the Foundry `/anthropic` path | ✅ | - |
| `azure-openai-deployment` | Model deployment name on your Foundry resource | ❌ | `gpt-5-mini` |

Both providers use the same three inputs above - they share one Foundry resource, differentiated only by `ai-provider` and which deployment name you point at.

#### Terraform Configuration
| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `terraform-plan-path` | Path to Terraform plan JSON file | ❌ | `tfplan.json` |
| `terraform-directory` | Directory containing Terraform files for enhanced analysis | ❌ | `.` |

#### GitHub Configuration
| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `github-token` | GitHub token for PR comments | ✅ | - |
| `disable-pr-comment` | Disable automatic PR commenting | ❌ | `false` |

#### Analysis Configuration
| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `analysis-preset` | Analysis preset: `security-audit`, `cost-optimisation`, `production-ready`, `quick-check`, or `complete` | ❌ | `complete` |
| `analysis-focus` | Focus areas (comma-separated) - overridden by `analysis-preset` | ❌ | `security,cost,best-practices,deployment` |
| `analysis-mode` | Analysis mode: `plan-only` or `comprehensive` | ❌ | `comprehensive` |
| `analysis-depth` | Analysis depth: `quick`, `standard`, or `detailed` | ❌ | `detailed` |
| `analysis-style` | Output organisation: `severity` or `domain` | ❌ | `severity` |

<details>
<summary>MCP Server Configuration</summary>

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `skip-mcp-validation` | Skip MCP server validation | ❌ | `false` |
| `show-mcp-details` | Show detailed MCP server analysis for troubleshooting | ❌ | `false` |
| `mcp-server-timeout` | MCP server startup timeout (seconds) | ❌ | `60` |

</details>

<details>
<summary>Security & Performance</summary>

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `enable-data-scrubbing` | Auto-scrub sensitive data (passwords, keys, secrets) before sending to AI | ❌ | `true` |
| `max-file-size-mb` | Maximum size per file in MB (prevents processing oversized files) | ❌ | `1` |
| `max-total-size-mb` | Maximum total size of all files in MB (prevents excessive API costs) | ❌ | `10` |
| `max-files` | Maximum number of files to process (prevents resource exhaustion) | ❌ | `100` |
| `api-timeout-seconds` | Timeout for AI API calls in seconds (prevents hanging requests) | ❌ | `120` |
| `api-max-retries` | Maximum API retry attempts with exponential backoff | ❌ | `3` |

</details>

### Outputs

<details>
<summary>View Outputs</summary>

| Output | Description |
|--------|-------------|
| `analysis-result` | The complete AI analysis result |
| `has-issues` | Whether critical issues were found |
| `recommendations-count` | Number of recommendations provided |

</details>

## Analysis Modes

<details>
<summary>📋 Analysis Output Styles</summary>

Choose how findings are organised in the analysis output:

### Severity-Based Organisation (Default)
- Summary with key findings overview
- **Critical Issues (🔴)** - Security vulnerabilities, breaking changes
- **Warnings (🟡)** - Suboptimal configurations, potential issues
- **Recommendations (🔵)** - Best practice improvements, optimisations
- **Good Practices (✅)** - Well-configured items to acknowledge

**Use Case:** Management reporting, security audits, prioritised action items

### Domain-Based Organisation
- **Security Analysis** - All security-related findings together
- **Cost Optimisation** - Cost-related recommendations and issues
- **Best Practices Review** - Infrastructure best practice violations
- **Deployment Readiness** - Deployment safety and operational concerns

**Use Case:** Technical reviews, domain-specific analysis, learning

```yaml
# Severity-based grouping (default)
analysis-style: 'severity'

# Technical domain grouping  
analysis-style: 'domain'
```

</details>

<details>
<summary>🎯 Analysis Focus Areas</summary>

You can customise the analysis by specifying focus areas:

### Configuration Presets

Use analysis presets for quick, standardised configurations:

#### Security Audit
```yaml
analysis-preset: 'security-audit'
analysis-depth: 'detailed'
```
**Includes:** security, compliance, governance

#### Cost Optimisation Review
```yaml
analysis-preset: 'cost-optimisation'
analysis-depth: 'standard'
```
**Includes:** cost, performance, data

#### Production Readiness
```yaml
analysis-preset: 'production-ready'
analysis-depth: 'detailed'
```
**Includes:** security, reliability, deployment, observability

#### Quick CI/CD Check
```yaml
analysis-preset: 'quick-check'
analysis-depth: 'quick'
analysis-mode: 'plan-only'
```
**Includes:** security, best-practices

#### Complete Infrastructure Review
```yaml
analysis-preset: 'complete'
analysis-depth: 'detailed'
```
**Includes:** All 11 focus areas (security, cost, best-practices, deployment, compliance, performance, reliability, observability, networking, data, governance)

### Core Analysis Areas
- **security:** Security vulnerabilities, exposed resources, compliance issues
- **cost:** Cost implications and optimisation opportunities
- **best-practices:** Infrastructure and provider-specific best practices
- **deployment:** Deployment safety and potential risks
- **compliance:** Regulatory and organisational compliance requirements

### Extended Analysis Areas
- **performance:** Resource sizing, scaling policies, and performance optimisation
- **reliability:** High availability, disaster recovery, and fault tolerance
- **observability:** Logging, monitoring, alerting, and tracing configurations
- **networking:** Network security, connectivity, routing, and firewall rules
- **data:** Data protection, encryption, backup strategies, and storage optimisation
- **governance:** Resource tagging, naming conventions, and organisational policies

### Usage Examples

```yaml
# Use preset (recommended)
analysis-preset: 'production-ready'
analysis-depth: 'detailed'

# Manual focus areas (if you need custom combination)
analysis-focus: 'security,cost,best-practices,deployment'
analysis-depth: 'standard'

# Complete review with preset
analysis-preset: 'complete'
analysis-depth: 'detailed'
analysis-style: 'severity'
```

</details>

### Analysis Depth

- **`quick`** - ~4K tokens, high-level critical findings
- **`standard`** - ~8K tokens, balanced comprehensive analysis
- **`detailed`** - ~12K tokens, exhaustive examination (default)

## Example Workflows

### Production Deployment

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
    enable-data-scrubbing: 'true'
```

### Quick CI/CD Check

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

### Multi-Environment Strategy

```yaml
jobs:
  terraform-review:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        environment: [dev, staging, prod]
    steps:
      - uses: actions/checkout@v7
      - uses: hashicorp/setup-terraform@v3
      
      - name: Terraform Plan
        working-directory: ./environments/${{ matrix.environment }}
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
          terraform-plan-path: ./environments/${{ matrix.environment }}/tfplan.json
          terraform-directory: ./environments/${{ matrix.environment }}
          analysis-preset: 'production-ready'
```

## HashiCorp MCP Integration

Integrates with HashiCorp's Terraform Model Context Protocol Server for enhanced validation:

- ✅ **Provider Documentation** - Real-time access to official docs
- 📦 **Module Registry** - Terraform module recommendations
- 🔍 **Resource Validation** - Validates against HashiCorp standards
- 📊 **Connection Status** - Real-time MCP server diagnostics

```yaml
# Enable detailed MCP diagnostics
skip-mcp-validation: false
show-mcp-details: true
mcp-server-timeout: 60
```

## Provider Support

**Automatically detects and analyses ANY Terraform provider:**

- Dynamic provider detection from resource types
- No hardcoded provider lists
- Works with AWS, Azure, GCP, Kubernetes, and 1000+ community providers
- Enhanced analysis in comprehensive mode

## Required Secrets

### Microsoft Foundry (both `azure` and `azure-anthropic`)
```bash
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_ENDPOINT=https://<resource>.services.ai.azure.com
AZURE_OPENAI_DEPLOYMENT=<deployment-name>
```
Use your Azure AI Foundry resource endpoint (`.services.ai.azure.com`), not a classic Azure OpenAI-only resource (`.openai.azure.com`) - Claude deployments (`azure-anthropic`) are only reachable through the Foundry endpoint.

`GITHUB_TOKEN` for PR comments is provided automatically by GitHub Actions - no secret to configure.

## Development

### Local Setup

```bash
git clone https://github.com/thomast1906/terraform-review-ai-action.git
cd terraform-ai-review-action
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
```

### Testing Locally

```bash
export AI_PROVIDER="azure"
export AZURE_OPENAI_API_KEY="<key>"
export AZURE_OPENAI_ENDPOINT="<endpoint>"
export AZURE_OPENAI_DEPLOYMENT="<deployment>"
export TERRAFORM_PLAN_PATH="tfplan.json"
python analyse_terraform.py
```

## Support

- 📖 [Documentation](https://github.com/thomast1906/terraform-review-ai-action)
- 🐛 [Report Issues](https://github.com/thomast1906/terraform-review-ai-action/issues)
- 💡 [Request Features](https://github.com/thomast1906/terraform-review-ai-action/issues)
- 💬 [Discussions](https://github.com/thomast1906/terraform-review-ai-action/discussions)

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

⭐ **Star this repo if it helped you!**

Built by [Thomas Thornton](https://github.com/thomast1906)