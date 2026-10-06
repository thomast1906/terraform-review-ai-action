# Fork pull requests

GitHub normally withholds repository secrets from workflows that fork pull requests trigger. This protects Foundry credentials from untrusted code.

## Expected behaviour

GitHub can skip a workflow or report an input error for a fork pull request. The workflow cannot access `FOUNDRY_API_KEY` or `FOUNDRY_ENDPOINT`.

## Safe approaches

Use a review process that fits your organization's threat model:

- Ask a maintainer to reproduce the change on a trusted branch.
- Run the AI review after a maintainer merges trusted code into an integration branch.
- Use a manually approved environment that contains the Foundry credentials.
- Run an unprivileged Terraform validation job first. Then review the trusted plan output.

## Avoid privileged execution of untrusted code

!!! danger
    Do not use `pull_request_target` to check out and execute an untrusted pull-request head while repository secrets or write permissions are available.

Treat pull-request content as executable and untrusted if a workflow runs `terraform init`, provider code, scripts, or repository-controlled commands.

## Permissions

For a normal trusted pull request with comments enabled:

```yaml
permissions:
  contents: read
  pull-requests: write
```

When comments are disabled:

```yaml
permissions:
  contents: read
```

Set `disable-pr-comment: true` and omit `github-token` if the workflow does not need a comment.
