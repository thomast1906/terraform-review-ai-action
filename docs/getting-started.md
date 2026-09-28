# Get started

This guide takes you from a Terraform configuration to an AI-assisted pull-request review.

## 1. Create a Foundry deployment

You need a Microsoft Foundry model deployment compatible with OpenAI chat completions. Record:

- The HTTPS Foundry endpoint
- The API key
- The deployment name

!!! warning "Protect your credentials"
    Never commit Foundry credentials. Store them as GitHub Actions secrets.

## 2. Add repository secrets

In the repository that will use the action, open **Settings → Secrets and variables → Actions** and create:

| Secret | Value |
|---|---|
| `FOUNDRY_API_KEY` | Your Foundry API key |
| `FOUNDRY_ENDPOINT` | Your HTTPS Foundry endpoint |

The deployment name can be written in the workflow when it is not sensitive, or stored as another secret.

## 3. Add the workflow

Create `.github/workflows/terraform-review.yml`:

```yaml
name: Terraform AI review

on:
  pull_request:
    paths:
      - '**/*.tf'
      - '**/*.tfvars'

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: hashicorp/setup-terraform@v3

      - name: Create Terraform plan
        run: |
          terraform init -input=false
          terraform plan -input=false -out=tfplan.binary
          terraform show -json tfplan.binary > tfplan.json

      - name: Review Terraform plan
        uses: thomast1906/terraform-ai-review-action@<commit-sha>
        with:
          foundry-api-key: ${{ secrets.FOUNDRY_API_KEY }}
          foundry-endpoint: ${{ secrets.FOUNDRY_ENDPOINT }}
          foundry-deployment: terraform-review
          terraform-plan-path: tfplan.json
          analysis-preset: production-ready
          fail-on-severity: warning
          github-token: ${{ github.token }}
```

Replace `<commit-sha>` with a revision you have reviewed.

## 4. Open a pull request

When Terraform files change, the workflow:

1. Generates a JSON plan.
2. Masks Terraform-marked sensitive and unknown plan values.
3. Sends bounded evidence to Foundry.
4. Creates or updates one managed review comment.
5. Applies the configured severity gate.

## 5. Tune the review

Start with one of these profiles:

=== "Default PR review"

    ```yaml
    analysis-mode: plan-only
    analysis-preset: production-ready
    analysis-depth: standard
    analysis-style: severity
    fail-on-severity: warning
    ```

=== "Fast"

    ```yaml
    analysis-mode: plan-only
    analysis-preset: quick-check
    analysis-depth: quick
    fail-on-severity: none
    ```

=== "Security"

    ```yaml
    analysis-mode: comprehensive
    analysis-preset: security-audit
    analysis-depth: detailed
    fail-on-severity: critical
    ```

=== "Larger comprehensive review"

    ```yaml
    analysis-mode: comprehensive
    terraform-directory: terraform/production
    target-prompt-chars: 100000
    max-prompt-chars: 120000
    ```

    Use comprehensive mode only for source you are comfortable sending to Foundry. Confirm the selected deployment has sufficient context capacity after allowing for the model response; larger budgets can increase review time and cost.

## Fork pull requests

GitHub normally withholds repository secrets from workflows triggered by forks. Do not expose Foundry credentials to untrusted pull-request code. Use a trusted-branch review process appropriate to your security model.

## Next steps

- Explore every [configuration option](configuration.md).
- Copy a complete [workflow recipe](examples.md).
- Review the [security and privacy boundaries](security.md).
