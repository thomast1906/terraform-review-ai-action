# Terraform AI Plan Review

Terraform AI Plan Review uses Microsoft Foundry to find security, cost, reliability, and delivery risks in Terraform plans. The review includes resource addresses and changed-value evidence when available.

- One managed PR comment that updates after each run
- Plan-only review or comprehensive source-and-plan review
- Presets for security, cost, production readiness, quick checks, and complete reviews
- Markdown, JSON, and severity-gate outputs for CI

## Quick start

```yaml
name: Terraform AI review

on:
  pull_request:
    paths: ['**/*.tf', '**/*.tfvars']

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: hashicorp/setup-terraform@v3
      - run: |
          terraform init -input=false
          terraform plan -input=false -out=tfplan.binary
          terraform show -json tfplan.binary > tfplan.json
      - uses: thomast1906/terraform-ai-review-action@<commit-sha>
        with:
          foundry-api-key: ${{ secrets.FOUNDRY_API_KEY }}
          foundry-endpoint: ${{ secrets.FOUNDRY_ENDPOINT }}
          foundry-deployment: terraform-review
          github-token: ${{ github.token }}
```

Replace `<commit-sha>` with a revision that you reviewed. The runner needs Terraform and access to your Foundry deployment. Docker is necessary only for optional MCP documentation enrichment.

## What is sent

- Plan-only mode sends evidence from changed plan values.
- Comprehensive mode also sends eligible `.tf` files under `terraform-directory`, within the configured source limits.
- The action masks Terraform-marked sensitive and unknown values. The action also checks for secret patterns, but this does not guarantee that source files contain no secrets.

## Next steps

- [First review](getting-started.md)
- [Configuration](configuration.md)
- [Workflow recipes](examples.md)
- [Security and privacy](security.md)
- [Fork pull requests](fork-pull-requests.md)
- [Outputs and severity policy](outputs.md)
- [Troubleshoot problems](troubleshooting.md)
