# Outputs and severity policy

## Action outputs

Assign an `id` to the action step to consume its outputs:

```yaml
- id: terraform-review
  uses: thomast1906/terraform-ai-review-action@<commit-sha>
  with:
    foundry-api-key: ${{ secrets.FOUNDRY_API_KEY }}
    foundry-endpoint: ${{ secrets.FOUNDRY_ENDPOINT }}
    foundry-deployment: terraform-review
    disable-pr-comment: true
```

| Output | Description |
|---|---|
| `analysis-result` | Complete Markdown review. |
| `has-issues` | `true` when warning or critical findings exist. |
| `recommendations-count` | Number of recommendation bullets. |
| `highest-severity` | `none`, `warning`, or `critical`. |

```yaml
- name: Show review result
  run: |
    echo "Highest severity: ${{ steps.terraform-review.outputs.highest-severity }}"
    echo "Issues found: ${{ steps.terraform-review.outputs.has-issues }}"
    echo "Recommendations: ${{ steps.terraform-review.outputs.recommendations-count }}"
```

## Generated files

The action writes two files in the job workspace:

- `ai_analysis.md` — complete Markdown review
- `analysis_summary.json` — compact machine-readable summary

For a successful review, the summary includes plan-change counts, review-batch counts, source files included, action counts, MCP status, and the effective configuration. `review_batches` excludes a final consolidation request.

`ai_analysis.md` and `analysis_summary.json` are created only after a successful review. Use `if: always()` for artifact upload so any files produced before a later severity gate failure are retained.

Upload them when you want reports to remain available after a workflow run:

```yaml
- name: Upload Terraform AI review
  if: always()
  uses: actions/upload-artifact@v7
  with:
    name: terraform-ai-review
    path: |
      ai_analysis.md
      analysis_summary.json
```

## Severity policy

| `fail-on-severity` | Result |
|---|---|
| `none` | Findings never fail the action. |
| `warning` | Warning or critical findings fail the action. |
| `critical` | Only critical findings fail the action. |

The report and summary are written before the gate runs. Use `if: always()` on artifact-upload steps so reports are retained when a gate fails.
