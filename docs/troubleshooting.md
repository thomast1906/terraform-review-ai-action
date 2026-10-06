# Troubleshooting

## The plan file is not present or is rejected

Make sure that the configured path is relative to the workspace. Make sure that the file contains `terraform show -json` output:

```bash
terraform plan -out=tfplan.binary
terraform show -json tfplan.binary > tfplan.json
```

Then set:

```yaml
terraform-plan-path: tfplan.json
```

## Foundry input validation fails

Make sure that each condition is true:

- `foundry-api-key` is populated.
- `foundry-deployment` names a deployment that exists.
- `foundry-endpoint` uses HTTPS.
- The endpoint has no query string, fragment, or embedded credentials.
- The runner can reach the endpoint.

## No PR comment appears

Make sure that each condition is true:

```yaml
permissions:
  contents: read
  pull-requests: write
```

- The event is `pull_request`.
- `disable-pr-comment` is not `true`.
- `github-token: ${{ github.token }}` is supplied.
- Repository or organization policy allows GitHub Actions to write pull-request comments.

## MCP enrichment is unavailable

MCP is optional. It requires Docker, registry access, and network access. If MCP cannot start or query documentation, the action continues with plan and source evidence.

## The job fails after creating a review

The action runs the severity gate after it creates the report. Examine the managed PR comment, `ai_analysis.md`, or `analysis_summary.json` to find the issue that triggered the gate.

## The job fails during evidence packing or review

The action fails if it cannot create a complete report. A request-size error means that one evidence item exceeds `max-prompt-chars`. Reduce the selected source evidence or increase both prompt budgets if the Foundry deployment has enough context capacity. The default values are `target-prompt-chars: 100000` and `max-prompt-chars: 120000`. Larger budgets increase latency and token cost.

For an API failure, examine the sanitized job log. Confirm the Foundry deployment, endpoint access, timeout, and retry settings.

## Reviews take too long or use too many tokens

Use these settings:

```yaml
analysis-mode: plan-only
analysis-preset: quick-check
analysis-depth: quick
```

For comprehensive mode, lower `max-files`, `max-file-size-mb`, or `max-total-size-mb`. These settings can exclude source files. For either mode, lower `max-resources-per-request` or `target-prompt-chars` to make smaller Foundry requests.

## Fork pull requests do not run

GitHub protects repository secrets from forked pull requests. This is expected. Do not expose Foundry credentials to untrusted code. Use a trusted review path or manual approval process.

## The PR comment is too large

The `analysis-result` output and `ai_analysis.md` contain the complete Markdown report. Disable the managed comment and upload the report as an artifact if your workflow needs another format.

## Need more detail?

Read the [configuration reference](configuration.md) and the [FAQ](faq.md).
