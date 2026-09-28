# Security and privacy

The action sends infrastructure evidence to a Microsoft Foundry deployment. Review the trust boundary before enabling it in a repository.

## Credential handling

- Store `foundry-api-key` and `foundry-endpoint` in GitHub Actions secrets.
- Never place credentials directly in workflow YAML.
- Grant only `contents: read` by default.
- Add `pull-requests: write` only when managed PR comments are enabled.
- Review who can modify workflow files and environments containing Foundry secrets.

## Evidence sent to Foundry

The request can contain:

- Changed Terraform plan evidence
- Resource addresses and changed before/after values
- In comprehensive mode, eligible `.tf` source files under `terraform-directory`
- Best-effort Terraform Registry documentation returned by MCP enrichment

Comprehensive mode scans the configured source tree, not only pull-request changes.

Plan evidence is packed into bounded Foundry requests and then consolidated. Source limits can exclude files; review the job logs before relying on a report.

## Terraform plan value masking

Before analysis:

- Terraform-sensitive values become `<redacted-sensitive>`.
- Unknown planned values become `<unknown-until-apply>`.
- Source evidence is limited by file size, total size, and file count.

!!! warning
    Terraform supplies the sensitive/unknown marks used for plan masking. The action also applies pattern-based scrubbing to the assembled prompt, but this is a safeguard rather than a guarantee of secret removal. Do not enable comprehensive mode for source containing secrets unless your Foundry trust boundary permits it.

## Untrusted pull requests

GitHub normally withholds repository secrets from fork pull requests. Do not work around this by exposing credentials to workflows that execute untrusted code. Use a trusted-branch or manually approved workflow appropriate to your organisation's threat model.

Avoid unsafe `pull_request_target` designs that check out and execute code from an untrusted head revision while privileged secrets are available.

## MCP enrichment

The action attempts to run a digest-pinned HashiCorp Terraform MCP container and query documentation for detected providers. Docker, registry, network, startup, and lookup failures are non-blocking and are noted in the report.
