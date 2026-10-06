# Get started

Use this guide to configure an AI-assisted pull-request review for Terraform.

## 1. Create a Foundry deployment

Create a Microsoft Foundry model deployment that supports OpenAI chat completions. Record these values:

- The HTTPS Foundry endpoint
- The API key
- The deployment name

!!! warning "Protect your credentials"
    Do not commit Foundry credentials. Store them as GitHub Actions secrets.

## 2. Add repository secrets

In the repository that uses the action, open **Settings → Secrets and variables → Actions**. Create these secrets:

| Secret | Value |
|---|---|
| `FOUNDRY_API_KEY` | Your Foundry API key |
| `FOUNDRY_ENDPOINT` | Your HTTPS Foundry endpoint |

Write the deployment name in the workflow if it is not sensitive. Otherwise, store it as another secret.

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

Replace `<commit-sha>` with a revision that you reviewed.

## 4. Open a pull request

When Terraform files change, the workflow does these steps:

1. Generate a JSON plan.
2. Mask sensitive and unknown plan values that Terraform marks.
3. Send bounded evidence to Foundry.
4. Create or update one managed review comment.
5. Apply the configured severity gate.

## 5. Tune the review

Use one of these profiles:

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

    Use comprehensive mode only for source that you can send to Foundry. Make sure that the selected deployment has enough context capacity for the request and response. A larger budget can increase review time and cost.

## Fork pull requests

GitHub normally withholds repository secrets from workflows that forks trigger. Do not expose Foundry credentials to untrusted pull-request code. Use a trusted-branch review process that fits your security model.

## Next steps

- Read the [configuration options](configuration.md).
- Copy a complete [workflow recipe](examples.md).
- Review the [security and privacy boundaries](security.md).
