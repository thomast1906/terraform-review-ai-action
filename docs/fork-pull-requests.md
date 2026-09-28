# Fork pull requests

GitHub normally withholds repository secrets from workflows triggered by pull requests from forks. This protects Foundry credentials from untrusted code.

## Expected behaviour

A workflow requiring `FOUNDRY_API_KEY` and `FOUNDRY_ENDPOINT` may be skipped or fail validation for a fork pull request because those secrets are unavailable.

## Safe approaches

Choose a review process that matches your organisation's threat model:

- Require a maintainer to reproduce the change on a trusted branch.
- Run the AI review after trusted code is merged to an integration branch.
- Use a manually approved environment containing the Foundry credentials.
- Perform an unprivileged Terraform validation job first, then separately review trusted plan output.

## Avoid privileged execution of untrusted code

!!! danger
    Do not use `pull_request_target` to check out and execute an untrusted pull-request head while repository secrets or write permissions are available.

Any workflow that runs `terraform init`, provider code, scripts, or repository-controlled commands should treat the pull-request contents as executable and untrusted.

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

Set `disable-pr-comment: true` and omit `github-token` when the workflow does not need to comment.
