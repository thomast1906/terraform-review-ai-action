# Terraform AI Plan Review

Turn Terraform plans into actionable pull-request feedback. Terraform AI Plan Review uses Microsoft Foundry to identify security, cost, reliability, and delivery risks, with resource addresses and changed-value evidence where available.

- One managed PR comment that updates on every run
- Plan-only or comprehensive source-and-plan review
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

Replace `<commit-sha>` with a revision you have reviewed. The runner needs Terraform and access to your Foundry deployment. Docker is needed only for optional MCP documentation enrichment.

## What is sent

- Plan-only mode sends changed plan evidence.
- Comprehensive mode also sends eligible `.tf` files under `terraform-directory`, subject to configured source limits.
- Terraform-marked sensitive and unknown values are masked. Pattern-based scrubbing is an extra safeguard, not a guarantee that source has no secrets.

## Next steps

- [First review](getting-started.md)
- [Configuration](configuration.md)
- [Workflow recipes](examples.md)
- [Security and privacy](security.md)
- [Fork pull requests](fork-pull-requests.md)
- [Outputs and severity policy](outputs.md)
- [Troubleshooting](troubleshooting.md)
