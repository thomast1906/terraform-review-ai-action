# Review modes and presets

Choose the review scope, focus, depth, organisation, and enforcement policy independently.

## Analysis mode

=== "Comprehensive"

    Reviews the Terraform plan and eligible `.tf` files below `terraform-directory`.

    ```yaml
    analysis-mode: comprehensive
    terraform-directory: terraform/production
    ```

    Use this when source context is important to understanding modules, variables, provider configuration, or controls not fully represented in the plan.

=== "Plan only"

    Reviews only the JSON plan evidence.

    ```yaml
    analysis-mode: plan-only
    ```

    Use this for faster feedback, lower token usage, or workflows where source should not be sent.

## Analysis preset

| Preset | Focus areas | Typical use |
|---|---|---|
| `quick-check` | Security, best practices | Fast feedback |
| `security-audit` | Security, compliance, governance | Security review and critical gates |
| `cost-optimisation` | Cost, performance, data | Cost-control reviews |
| `production-ready` | Security, reliability, deployment, observability, performance | Pre-production review |
| `complete` | All supported focus areas | Broad, detailed assessment |

## Analysis depth

- **`quick`** produces concise, high-level feedback.
- **`standard`** balances detail, runtime, and token use.
- **`detailed`** requests the most thorough review.

## Report style

=== "Severity"

    ```yaml
    analysis-style: severity
    ```

    Organises findings into critical issues, warnings, recommendations, and good practices. This is usually the clearest format for pull-request decisions.

=== "Domain"

    ```yaml
    analysis-style: domain
    ```

    Organises findings by areas such as security, cost, reliability, networking, and governance.

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
