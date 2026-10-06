# Frequently asked questions

## What does the action do?

The action analyzes bounded Terraform plan evidence and optional source files with a Microsoft Foundry model. It writes a detailed Markdown review and can maintain one stable pull-request comment.

## What is sent to Foundry?

Included changed plan values and, in comprehensive mode, bounded Terraform source files. Terraform-sensitive values become `<redacted-sensitive>` and unknown values become `<unknown-until-apply>` before the request. The action also checks the assembled prompt for patterns that match secrets. This step adds protection. Do not put secrets in source evidence.

## Does comprehensive mode review only changed files?

No. It reads eligible `.tf` files below `terraform-directory`, subject to source limits.

## Is Terraform MCP required?

No. MCP documentation enrichment is best effort. When available, it queries documentation for detected providers. The core Foundry review continues when Docker, registry, network, startup, or lookup access is unavailable.

## How does `fail-on-severity` work?

- `none`: findings do not fail the action.
- `warning`: warnings or critical findings fail the action.
- `critical`: only critical findings fail the action.

The gate runs after the report is written.

## Can I run without PR comments?

Yes. Set `disable-pr-comment: true`. You can then omit `github-token` and `pull-requests: write`.

## How do I reduce runtime and token usage?

Use `analysis-mode: plan-only`, `analysis-depth: quick`, and `analysis-preset: quick-check`. Reduce source limits if comprehensive mode includes more context than you need.
