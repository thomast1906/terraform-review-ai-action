# Configuration

## Required Foundry inputs

| Input | Description |
|---|---|
| `foundry-api-key` | Microsoft Foundry API key. Use a GitHub secret. |
| `foundry-endpoint` | HTTPS Foundry endpoint without query parameters, fragments, or embedded credentials. |
| `foundry-deployment` | Foundry model deployment name. |

## Terraform evidence

| Input | Default | Description |
|---|---:|---|
| `terraform-plan-path` | `tfplan.json` | Path to `terraform show -json` output. |
| `terraform-directory` | `.` | Source root read in comprehensive mode. |
| `max-file-size-mb` | `10` | Maximum individual source file size. |
| `max-total-size-mb` | `50` | Maximum combined source evidence size. |
| `max-files` | `100` | Maximum source files included. |
| `max-resources-per-request` | `100` | Maximum number of changed resources in one Foundry request. |
| `target-prompt-chars` | `100000` | Target character budget for evidence in each request. |
| `max-prompt-chars` | `120000` | Maximum character count for one Foundry request. |

!!! info
    `plan-only` is the default. It sends only the plan delta, so it is faster, costs less, and sends less data. `comprehensive` is optional. It reads eligible `.tf` files below `terraform-directory`. It does not limit source to files that the pull request changed.

    The default target and maximum prompt budgets are 100,000 and 120,000 characters. Make sure that the selected Foundry deployment has enough context capacity for the request and response. A larger budget can increase latency and token cost.     A request-size or API failure fails the action.

## Review controls

| Input | Default | Supported values |
|---|---:|---|
| `analysis-mode` | `plan-only` | `comprehensive`, `plan-only` |
| `analysis-preset` | `complete` | `security-audit`, `cost-optimisation`, `production-ready`, `quick-check`, `complete` |
| `analysis-depth` | `detailed` | `quick`, `standard`, `detailed` |
| `analysis-style` | `severity` | `severity`, `domain` |
| `fail-on-severity` | `none` | `none`, `warning`, `critical` |

### Modes

- **Plan-only** (default) reviews only plan evidence and usually uses fewer tokens.
- **Comprehensive** reviews plan evidence and bounded Terraform source. Use it only when the Foundry trust boundary and prompt budget suit the source tree.

### Presets

| Preset | Focus |
|---|---|
| `quick-check` | Security and best practices |
| `security-audit` | Security, compliance, and governance |
| `cost-optimisation` | Cost only |
| `production-ready` | Security, reliability, deployment, observability, and performance |
| `complete` | Every supported focus area |

### Styles

- **Severity** groups findings as critical issues, warnings, recommendations, and good practices.
- **Domain** groups findings by areas such as security, cost, reliability, and network design.

### Severity gates

| Value | Behaviour |
|---|---|
| `none` | The review never fails because of findings. |
| `warning` | Warning or critical findings fail the action. |
| `critical` | Only critical findings fail the action. |

The action writes the report before it enforces the gate. A failed job can still show its findings.

## Commenting and API behaviour

| Input | Default | Description |
|---|---:|---|
| `disable-pr-comment` | `false` | Skip the managed pull-request comment. |
| `github-token` | optional | Required when pull-request comments are enabled. |
| `api-timeout-seconds` | `120` | Foundry request timeout in seconds. |
| `api-max-retries` | `2` | Maximum Foundry request attempts, including the initial attempt. |
| `ai-provider` | `foundry-openai` | Compatibility input; no other provider is supported. |

## Outputs

| Output | Description |
|---|---|
| `analysis-result` | Complete Markdown review. |
| `has-issues` | `true` for warning or critical findings. |
| `recommendations-count` | Number of recommendation bullets. |
| `highest-severity` | `none`, `warning`, or `critical`. |

```yaml
- id: review
  uses: thomast1906/terraform-ai-review-action@<commit-sha>
  with:
    foundry-api-key: ${{ secrets.FOUNDRY_API_KEY }}
    foundry-endpoint: ${{ secrets.FOUNDRY_ENDPOINT }}
    foundry-deployment: terraform-review
    disable-pr-comment: true

- name: Read outputs
  run: |
    echo "Severity: ${{ steps.review.outputs.highest-severity }}"
    echo "Issues: ${{ steps.review.outputs.has-issues }}"
```
