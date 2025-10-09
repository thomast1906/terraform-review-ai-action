# Frequently Asked Questions (FAQ)

## General Questions

### What is Terraform AI Review Action?

This is a GitHub Action that uses AI (Azure OpenAI or GitHub Models) to analyse Terraform infrastructure plans and provide intelligent recommendations on security, cost optimisation, best practices, and more.

### How much does it cost to use?

The action itself is free and open-source. You only pay for:
- **Azure OpenAI**: Based on tokens processed (typically $0.01-0.10 per plan review)
- **GitHub Models**: [Free tier available](https://docs.github.com/en/github-models), paid tiers for higher usage
- **GitHub Actions minutes**: Usually within free tier limits

### Which Terraform providers are supported?

All Terraform providers are supported! The action automatically detects and adapts to:
- AWS
- Azure (azurerm)
- Google Cloud Platform
- Kubernetes
- And any other Terraform provider

## Setup & Configuration

### How do I get started?

1. Set up Azure OpenAI or GitHub Models access
2. Add API credentials to GitHub Secrets  
3. Add the action to your workflow (see [README.md](README.md))
4. **For GitHub Models**: Add `models: read` permission to your workflow
5. Configure analysis focus areas and depth

### What secrets do I need to configure?

For Azure OpenAI:
```
AZURE_OPENAI_API_KEY
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_DEPLOYMENT
```

For GitHub Models:
```
GITHUB_TOKEN  # Built-in token or personal access token
```

Plus GitHub token for PR comments (automatically provided):
```
GITHUB_TOKEN
```

**Note:** GitHub Models is the easiest to set up - it uses your existing GitHub token with no additional credentials needed!

### Can I use this with self-hosted runners?

Yes! Make sure your self-hosted runner has:
- Python 3.11+
- Docker (if using MCP validation)
- Network access to OpenAI API endpoints

## Analysis Features

### What's the difference between analysis modes?

- **comprehensive**: Analyses both Terraform plan and source files (slower, more thorough)
- **plan-only**: Analyses only the JSON plan (faster, good for CI/CD)

### What are the analysis depth levels?

- **quick**: ~4K tokens, high-level issues only (~30 seconds)
- **standard**: ~8K tokens, balanced analysis (~45 seconds)
- **detailed**: ~12K tokens, exhaustive review (~60-90 seconds)

### What analysis presets are available?

- `security-audit`: Security, compliance, governance
- `cost-optimisation`: Cost, performance, data
- `production-ready`: Security, reliability, deployment, observability, performance
- `quick-check`: Security, best-practices (fast)
- `complete`: All 11 focus areas

### Can I customize the analysis?

Yes! You can:
- Choose specific focus areas manually
- Adjust analysis depth
- Switch between severity/domain output styles
- Customize prompts (see [PROMPT_CUSTOMIZATION.md](PROMPT_CUSTOMIZATION.md))

## Troubleshooting

### The action fails with "Terraform plan not found"

Make sure you:
1. Run `terraform plan -out=tfplan.binary` before the action
2. Convert to JSON: `terraform show -json tfplan.binary > tfplan.json`
3. Specify correct path in `terraform-plan-path` input

### I get AI API errors

**For Azure OpenAI:**
- API key is valid and not expired
- Endpoint URL is correct (include https://)
- Deployment name matches your Azure OpenAI deployment
- You have sufficient quota/credits

**For GitHub Models (401 Unauthorized error):**
- Add `models: read` permission to your workflow:
```yaml
permissions:
  contents: read
  pull-requests: write
  models: read  # Required for GitHub Models
```
- Ensure your repository has access to GitHub Models
- [Learn more about GitHub Models setup](https://thomasthornton.cloud/2025/08/19/using-github-models-with-your-github-workflows/)

### MCP server fails to start

This is non-critical - the action will continue without MCP validation. Common causes:
- Docker not available in runner
- Network restrictions
- Use `skip-mcp-validation: true` to bypass

### The analysis is too verbose/brief

Adjust the `analysis-depth`:
- Too verbose? Use `quick` or `standard`
- Too brief? Use `detailed`

### No PR comment is created

Check:
- Workflow has `pull-requests: write` permission
- Running on pull_request event
- `disable-pr-comment` is not set to `true`

## Security & Privacy

### Is my Terraform code sent to OpenAI?

Yes, the action sends your Terraform data to the configured AI provider:
- **GitHub Models**: Data sent to GitHub's AI infrastructure
- **Azure OpenAI**: Data sent to your Azure OpenAI instance

What is sent:
- Terraform plan JSON (always)
- Terraform source files (in comprehensive mode only)

**Privacy considerations:**
- GitHub Models: Review [GitHub's data handling policies](https://docs.github.com/en/github-models)
- Azure OpenAI: Data stays in your Azure tenant with your configured data residency

### How is sensitive data handled?

The action includes automatic data scrubbing (enabled by default):
- Passwords, API keys, secrets are detected and redacted
- Use `enable-data-scrubbing: true` (default) to ensure sensitive data is scrubbed
- Scrubbing happens before data is sent to AI providers

### How do I exclude sensitive resources?

Use `analysis-mode: plan-only` to avoid sending source files, or:
1. Filter sensitive data from plan before analysis
2. Use `.gitignore` to exclude sensitive files
3. Review outputs before they're posted to PRs

### Can I use this in air-gapped environments?

Partially - you'd need:
- Access to Azure OpenAI API (Azure OpenAI can be deployed in your environment)
- GitHub Models won't work in air-gapped environments
- Skip MCP validation: `skip-mcp-validation: true`
- Network access from your runners to the AI provider endpoint

## Performance

### How long does analysis take?

Typical timing:
- **Quick analysis**: 20-40 seconds
- **Standard analysis**: 40-60 seconds  
- **Detailed analysis**: 60-90 seconds

Factors: plan size, file count, API latency, MCP validation

### How can I speed up the action?

- Use `analysis-mode: plan-only`
- Use `analysis-depth: quick`
- Use `skip-mcp-validation: true`
- Use `analysis-preset: quick-check`

### Can I cache dependencies?

The action automatically creates a Python virtual environment and installs dependencies. The setup is fast (~10-15 seconds) and caching is handled internally by the composite action.

## Advanced Usage

### Can I run this on multiple directories?

Yes! Use a matrix strategy:

```yaml
strategy:
  matrix:
    directory: [terraform/dev, terraform/prod]
steps:
  - uses: thomast1906/terraform-review-ai-action@v1
    with:
      ai-provider: 'github-models'
      github-models-token: ${{ secrets.GITHUB_TOKEN }}
      github-token: ${{ secrets.GITHUB_TOKEN }}
      terraform-directory: ${{ matrix.directory }}
      terraform-plan-path: ${{ matrix.directory }}/tfplan.json
```

### How do I fail the workflow on critical issues?

Check the outputs:

```yaml
- id: review
  uses: thomast1906/terraform-review-ai-action@v1
  with:
    ai-provider: 'github-models'
    github-models-token: ${{ secrets.GITHUB_TOKEN }}
    github-token: ${{ secrets.GITHUB_TOKEN }}

- name: Check for critical issues
  if: steps.review.outputs.has-issues == 'true'
  run: |
    echo "Critical issues found!"
    exit 1
```

### Can I customize the AI prompts?

The action uses carefully crafted system prompts optimized for Terraform analysis. While direct prompt customization isn't exposed as an input, you can:
- Adjust analysis focus areas to target specific concerns
- Use different analysis presets for different prompt templates
- Modify analysis depth to control output verbosity

For advanced customization, you can fork the repository and modify the prompts in the `prompts/` directory.

### Can I use a different AI model?

Yes! Specify the model based on your AI provider:

**For Azure OpenAI:**
```yaml
with:
  ai-provider: 'azure'
  azure-openai-api-key: ${{ secrets.AZURE_OPENAI_API_KEY }}
  azure-openai-endpoint: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
  azure-openai-deployment: 'your-gpt-4-deployment'  # Name of your Azure deployment
  github-token: ${{ secrets.GITHUB_TOKEN }}
```

**For GitHub Models:**
```yaml
with:
  ai-provider: 'github-models'
  github-models-token: ${{ secrets.GITHUB_TOKEN }}
  github-models-model: 'gpt-4o'  # or 'gpt-4o-mini' for faster/cheaper analysis
  github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Integration

### Does this work with Terraform Cloud/Enterprise?

Yes! Generate the plan JSON from TFC/TFE and provide it to the action.

### Can I integrate with other tools?

Yes! The action outputs:
- `ai_analysis.md` - Markdown report
- `analysis_summary.json` - JSON summary

Use these in subsequent workflow steps.

### Can I send results to Slack/Teams?

Yes! Use the outputs with notification actions:

```yaml
- uses: 8398a7/action-slack@v3
  with:
    status: custom
    custom_payload: |
      {
        text: "Terraform Review Complete",
        attachments: [{
          text: "${{ steps.review.outputs.analysis-result }}"
        }]
      }
```

## Contributing

### How can I contribute?

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### I found a bug, how do I report it?

Create an issue using the bug report template.

### Can I request features?

Absolutely! Use the feature request template.

## Still Have Questions?

- 📖 Check the [README.md](README.md)
- 💬 Open a [Discussion](https://github.com/thomast1906/terraform-review-ai-action/discussions)
- 🐛 Report [Issues](https://github.com/thomast1906/terraform-review-ai-action/issues)
- 📧 Contact the maintainer
