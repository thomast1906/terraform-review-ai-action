const test = require('node:test');
const assert = require('node:assert/strict');
const { findReviewComment, upsertReviewComment, renderFixtureReview } = require('../scripts/comment.js');

test('updates only the comment carrying the stable marker', () => {
  const comments = [{ id: 1, user: { type: 'User' }, body: 'old' }, { id: 2, user: { type: 'Bot', login: 'github-actions[bot]' }, body: '<!-- terraform-ai-plan-review -->\nold review' }];
  assert.equal(findReviewComment(comments).id, 2);
});

test('ignores a user comment that spoofs the review marker', () => {
  const comments = [{ id: 1, user: { type: 'User' }, body: '<!-- terraform-ai-plan-review -->' }];
  assert.equal(findReviewComment(comments), undefined);
});

test('ignores an unrelated bot that spoofs the review marker', () => {
  const comments = [{ id: 1, user: { type: 'Bot', login: 'other-app[bot]' }, body: '<!-- terraform-ai-plan-review -->' }];
  assert.equal(findReviewComment(comments), undefined);
});

test('finds a comment using a custom marker', () => {
  const marker = '<!-- terraform-ai-multicloud-review -->';
  const comments = [{ id: 7, user: { type: 'Bot', login: 'github-actions[bot]' }, body: `${marker}\nold` }];
  assert.equal(findReviewComment(comments, marker).id, 7);
});

test('paginates comments before creating a new review comment', async () => {
  const updated = [];
  const github = {
    paginate: async () => [
      { id: 1, user: { type: 'User' }, body: 'unrelated' },
      { id: 2, user: { type: 'Bot', login: 'github-actions[bot]' }, body: '<!-- terraform-ai-plan-review -->\nold review' },
    ],
    rest: { issues: {
      listComments() {},
      updateComment: async args => updated.push(args),
      createComment: async () => { throw new Error('must not create'); },
    } },
  };
  await upsertReviewComment({
    github,
    context: { issue: { number: 3 }, repo: { owner: 'o', repo: 'r' } },
    body: 'new review',
  });
  assert.equal(updated[0].comment_id, 2);
});

test('renders a capability fixture with its effective settings and coverage', () => {
  const section = renderFixtureReview({
    label: 'Security audit',
    report: '## Summary\nEvidence-backed security findings.',
    summary: {
      review_status: 'complete', resource_changes: 25, reviewed_resource_changes: 25,
      review_batches: 1, source_files_included: 0, source_files_omitted: 0,
      providers_detected: ['aws'], mcp_status: 'available',
      action_counts: { create: 25, update: 0, delete: 0, replace: 0 },
      review_configuration: {
        analysis_preset: 'security-audit', analysis_focus: ['security', 'compliance', 'governance'],
        analysis_mode: 'plan-only', analysis_depth: 'detailed', analysis_style: 'severity',
        fail_on_severity: 'none', request_strategy: 'single-request',
      },
    },
  });

  assert.match(section, /Security audit/);
  assert.match(section, /security-audit/);
  assert.match(section, /security, compliance, governance/);
  assert.match(section, /single-request/);
  assert.match(section, /25 \/ 25/);
  assert.match(section, /MCP enrichment.*available/);
  assert.match(section, /Evidence-backed security findings/);
});
