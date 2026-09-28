# Terraform AI Plan Review Action

[![Documentation](https://github.com/thomast1906/terraform-ai-review-action-privaterepo/actions/workflows/docs.yml/badge.svg)](https://github.com/thomast1906/terraform-ai-review-action-privaterepo/actions/workflows/docs.yml)
[![GitHub Pages](https://img.shields.io/badge/docs-GitHub%20Pages-0078D4?logo=github)](https://thomast1906.github.io/terraform-ai-review-action-privaterepo/)

Turn Terraform plans into actionable pull-request feedback. The action sends bounded plan evidence to Microsoft Foundry and returns findings for security, cost, reliability, and delivery risk—linked to resource addresses and changed values.

## What you get

- One managed PR comment that updates on every run
- Critical issues, warnings, recommendations, good practices, and immediate actions
- Resource addresses and before/after evidence where available
- Markdown and JSON outputs for workflow automation

## Quick start

Generate a Terraform JSON plan, then invoke the action:

```yaml
- uses: thomast1906/terraform-ai-review-action@<commit-sha>
  with:
    foundry-api-key: ${{ secrets.FOUNDRY_API_KEY }}
    foundry-endpoint: ${{ secrets.FOUNDRY_ENDPOINT }}
    foundry-deployment: terraform-review
    terraform-plan-path: tfplan.json
    github-token: ${{ github.token }}
```

Replace `<commit-sha>` with a revision you have reviewed. See the [getting-started guide](https://thomast1906.github.io/terraform-ai-review-action-privaterepo/getting-started/) for workflow setup and security guidance.

## Built for Terraform pull requests

- Plan-only feedback for speed, or comprehensive source-and-plan review for context
- Security, cost, production-readiness, quick-check, and complete presets
- Warning and critical severity gates for CI
- Terraform-sensitive and unknown-value masking before requests

## Documentation

The guide covers setup, configuration, safety, and examples:

**[Read the documentation website](https://thomast1906.github.io/terraform-ai-review-action-privaterepo/)**

- [Get started](https://thomast1906.github.io/terraform-ai-review-action-privaterepo/getting-started/)
- [Configuration reference](https://thomast1906.github.io/terraform-ai-review-action-privaterepo/configuration/)
- [Review modes and presets](https://thomast1906.github.io/terraform-ai-review-action-privaterepo/review-options/)
- [Workflow examples](https://thomast1906.github.io/terraform-ai-review-action-privaterepo/examples/)
- [Security and privacy](https://thomast1906.github.io/terraform-ai-review-action-privaterepo/security/)
- [Troubleshooting](https://thomast1906.github.io/terraform-ai-review-action-privaterepo/troubleshooting/)
