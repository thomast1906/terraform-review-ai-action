# Review modes and presets

Select the review scope, focus, depth, format, and severity policy.

## Analysis mode

=== "Comprehensive"

    This mode reviews the Terraform plan and eligible `.tf` files below `terraform-directory`.

    ```yaml
    analysis-mode: comprehensive
    terraform-directory: terraform/production
    ```

    Use this mode when source files help explain modules, variables, provider configuration, or controls that the plan does not fully show.

=== "Plan only"

    This mode reviews only the JSON plan evidence.

    ```yaml
    analysis-mode: plan-only
    ```

    Use this mode for faster feedback, lower token use, or workflows that must not send source files.

## Analysis preset

| Preset | Focus areas | Typical use |
|---|---|---|
| `quick-check` | Security, best practices | Fast review |
| `security-audit` | Security, compliance, governance | Security review and critical gates |
| `cost-optimisation` | Cost only | Cost review |
| `production-ready` | Security, reliability, deployment, observability, performance | Review before production |
| `complete` | All supported focus areas | Full review |

## Analysis depth

- **`quick`** produces short, general feedback.
- **`standard`** balances detail, runtime, and token use.
- **`detailed`** requests the most thorough review.

## Report style

=== "Severity"

    ```yaml
    analysis-style: severity
    ```

    This style groups findings into critical issues, warnings, recommendations, and good practices. It gives clear information for pull-request decisions.

=== "Domain"

    ```yaml
    analysis-style: domain
    ```

    This style groups findings by areas such as security, cost, reliability, network design, and governance.

## Recommended profiles

### Balanced pull-request review

```yaml
analysis-mode: comprehensive
analysis-preset: production-ready
analysis-depth: standard
analysis-style: severity
fail-on-severity: warning
```

### Fast review

```yaml
analysis-mode: plan-only
analysis-preset: quick-check
analysis-depth: quick
analysis-style: severity
fail-on-severity: none
```

### Detailed security gate

```yaml
analysis-mode: comprehensive
analysis-preset: security-audit
analysis-depth: detailed
analysis-style: severity
fail-on-severity: critical
```
