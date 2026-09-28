# Frequently asked questions

## What does the action do?

It analyses bounded Terraform plan and optional source evidence with a Microsoft Foundry model, writes a rich Markdown review, and can maintain one stable pull-request comment.

## What is sent to Foundry?

Included changed plan values and, in comprehensive mode, bounded Terraform source files. Terraform-sensitive values become `<redacted-sensitive>` and unknown values become `<unknown-until-apply>` before the request. The assembled prompt also receives pattern-based scrubbing; it is a safeguard, not a substitute for keeping secrets out of source evidence.

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

Use `analysis-mode: plan-only`, `analysis-depth: quick`, and `analysis-preset: quick-check`. Reduce source limits if comprehensive mode includes more context than required.
