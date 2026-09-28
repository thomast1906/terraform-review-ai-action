# Security policy

## Reporting a vulnerability

Do not open a public issue for a suspected security vulnerability. In particular, never include Foundry API keys, endpoints containing sensitive information, Terraform state, plan output containing sensitive values, or other credentials in an issue, pull request, log, or discussion.

Use this repository's **Report a vulnerability** option under the Security tab to submit a private report. Include a clear description, affected versions or commit SHA, reproduction steps, and the potential impact. Redact all secrets from the report.

If private vulnerability reporting is not enabled, contact [@thomast1906](https://github.com/thomast1906) through GitHub and ask for a private reporting channel. Do not disclose the vulnerability details publicly.

## Supported versions

Security fixes are applied to the latest released version and the default branch. Consumers should pin a reviewed release or commit SHA and update after a security fix is published.

## Scope notes

This action submits bounded Terraform plan evidence, and optionally Terraform source evidence, to a configured Microsoft Foundry deployment. The security of that deployment, its access controls, and the source selected for comprehensive review remain the responsibility of the repository using the action.
