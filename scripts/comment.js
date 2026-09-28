const MARKER = '<!-- terraform-ai-plan-review -->';

function findReviewComment(comments, marker = MARKER) {
  return comments.find(comment =>
    comment.user?.type === 'Bot' &&
    comment.user?.login === 'github-actions[bot]' &&
    typeof comment.body === 'string' &&
    comment.body.includes(marker)
  );
}

async function upsertReviewComment({ github, context, body, marker = MARKER }) {
  const comments = await github.paginate(github.rest.issues.listComments, {
    issue_number: context.issue.number,
    owner: context.repo.owner,
    repo: context.repo.repo,
    per_page: 100,
  });
  const commentBody = `${marker}\n${body || ''}`;
  const existing = findReviewComment(comments, marker);
  if (existing) {
    await github.rest.issues.updateComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      comment_id: existing.id,
      body: commentBody,
    });
    return existing.id;
  }
  const created = await github.rest.issues.createComment({
    issue_number: context.issue.number,
    owner: context.repo.owner,
    repo: context.repo.repo,
    body: commentBody,
  });
  return created.data.id;
}

function renderFixtureReview({ label, report, summary }) {
  const configuration = summary.review_configuration || {};
  const actionCounts = summary.action_counts || {};
  const focus = Array.isArray(configuration.analysis_focus)
    ? configuration.analysis_focus.join(', ')
    : 'not recorded';
  const providerList = Array.isArray(summary.providers_detected)
    ? summary.providers_detected.join(', ')
    : 'not recorded';
  const reviewed = `${summary.reviewed_resource_changes ?? 0} / ${summary.resource_changes ?? 0}`;
  const actions = [
    `Create: ${actionCounts.create ?? 0}`,
    `Update: ${actionCounts.update ?? 0}`,
    `Delete: ${actionCounts.delete ?? 0}`,
    `Replace: ${actionCounts.replace ?? 0}`,
  ].join(' · ');

  return `<details>
<summary><strong>${label}</strong></summary>

### Review configuration and coverage

| Setting | Effective value |
|---|---|
| Preset | \`${configuration.analysis_preset || 'custom'}\` |
| Focus | ${focus} |
| Mode / depth / style | \`${configuration.analysis_mode || 'not recorded'}\` / \`${configuration.analysis_depth || 'not recorded'}\` / \`${configuration.analysis_style || 'not recorded'}\` |
| Severity gate | \`${configuration.fail_on_severity || 'not recorded'}\` |
| Request strategy | \`${configuration.request_strategy || 'not recorded'}\` |
| Providers | ${providerList} |
| Plan evidence reviewed | ${reviewed} resources in ${summary.review_batches ?? 0} batch(es) |
| Planned actions | ${actions} |
| Source evidence | ${summary.source_files_included ?? 0} included, ${summary.source_files_omitted ?? 0} omitted |
| MCP enrichment | ${summary.mcp_status || 'not recorded'} |
| Review status | ${summary.review_status || 'not recorded'} |

${report}

</details>`;
}

module.exports = { MARKER, findReviewComment, upsertReviewComment, renderFixtureReview };
