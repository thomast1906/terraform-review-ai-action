# Troubleshooting

## The plan file is missing or rejected

Confirm that the configured path is relative to the workspace and contains `terraform show -json` output:

```bash
terraform plan -out=tfplan.binary
terraform show -json tfplan.binary > tfplan.json
```

Then set:

```yaml
terraform-plan-path: tfplan.json
```

## Foundry input validation fails

Check that:

- `foundry-api-key` is populated.
- `foundry-deployment` matches an existing deployment.
- `foundry-endpoint` uses HTTPS.
- The endpoint has no query string, fragment, or embedded credentials.
- The runner can reach the endpoint.

## No PR comment appears

Verify all of the following:

```yaml
permissions:
  contents: read
  pull-requests: write
```

- The event is `pull_request`.
- `disable-pr-comment` is not `true`.
- `github-token: ${{ github.token }}` is supplied.
- Repository or organisation policy allows GitHub Actions to write pull-request comments.

## MCP enrichment is unavailable

MCP is optional. It requires Docker plus registry and network access. If it cannot start or query documentation, the action continues with plan and source evidence.

## The job fails after creating a review

The severity gate intentionally runs after report creation. Inspect the managed PR comment, `ai_analysis.md`, or `analysis_summary.json` to identify the finding that triggered the gate.

## The job fails during evidence packing or review

The action fails rather than returning a partial report. A packing failure means one evidence item cannot fit within `max-prompt-chars`; either reduce the selected source evidence or increase both prompt budgets when the Foundry deployment has sufficient context capacity. The defaults are `target-prompt-chars: 100000` and `max-prompt-chars: 120000`; larger budgets increase latency and token cost. For an API failure, inspect the sanitized job log and confirm the Foundry deployment, endpoint reachability, timeout, and retry settings.

## Reviews take too long or use too many tokens

Try:

```yaml
analysis-mode: plan-only
analysis-preset: quick-check
analysis-depth: quick
```

For comprehensive mode, lower `max-files`, `max-file-size-mb`, or `max-total-size-mb`; this can exclude source files. For either mode, lower `max-resources-per-request` or `target-prompt-chars` to create smaller Foundry requests.

## Fork pull requests do not run

GitHub protects repository secrets from forked pull requests. This is expected. Do not expose Foundry credentials to untrusted code; use a trusted review path or manual approval process.

## The PR comment is too large

The complete Markdown is available through the `analysis-result` output and `ai_analysis.md`. Disable the managed comment and upload the report as an artifact if your workflow needs a different presentation strategy.

## Need more detail?

Review the [complete configuration reference](configuration.md) and the repository [FAQ](faq.md).
