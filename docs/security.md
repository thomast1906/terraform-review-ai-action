# Security and privacy

The action sends infrastructure evidence to a Microsoft Foundry deployment. Review the trust boundary before you enable the action in a repository.

## Credential handling

- Store `foundry-api-key` and `foundry-endpoint` in GitHub Actions secrets.
- Never place credentials directly in workflow YAML.
- Grant only `contents: read` by default.
- Add `pull-requests: write` only when managed PR comments are enabled.
- Limit who can modify workflow files and environments that contain Foundry secrets.

## Evidence sent to Foundry

The request can contain:

- Changed Terraform plan evidence
- Resource addresses and changed before/after values
- In comprehensive mode, eligible `.tf` source files under `terraform-directory`
- Best-effort Terraform Registry documentation returned by MCP enrichment

Comprehensive mode scans the configured source tree, not only pull-request changes.

The action packs plan evidence into bounded Foundry requests and then consolidates it. Source limits can exclude files. Review the job logs before you rely on a report.

## Terraform plan value protection

Before the action calls Foundry, it protects plan values:

- The action changes Terraform-sensitive values to `<redacted-sensitive>`.
- The action changes unknown planned values to `<unknown-until-apply>`.
- The action limits source evidence by file size, total size, and file count.

!!! warning
    Terraform supplies the sensitive and unknown marks for plan protection. The action also checks the assembled prompt for patterns that match secrets. This adds protection, but it does not guarantee secret removal. Do not enable comprehensive mode for source files with secrets unless the Foundry trust boundary permits it.

## Untrusted pull requests

GitHub normally withholds repository secrets from fork pull requests. Do not expose credentials to workflows that run untrusted code. Use a trusted-branch or manually approved workflow that fits your organization's threat model.

Do not use an unsafe `pull_request_target` workflow. Do not check out or run code from an untrusted pull-request head while privileged secrets are available.

## MCP enrichment

The action attempts to run a HashiCorp Terraform MCP container that uses a fixed digest. It queries documentation for detected providers. Docker, registry, network, startup, or lookup errors do not stop the action. The report lists these errors.
