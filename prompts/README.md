# OpenAI System Prompts

This directory contains customisable system prompts for the Terraform AI Review Action.

## Available Prompts

### `system_prompt_severity.md`
Used when `analysis-style: severity` (default)

Groups findings by severity level:
- 🔴 Critical Issues
- 🟡 Warnings
- 🔵 Recommendations
- ✅ Good Practices

### `system_prompt_domain.md`
Used when `analysis-style: domain`

Groups findings by technical domain:
- Security Analysis
- Cost Optimization
- Best Practices Review
- Deployment Readiness
- etc.

## Customizing Prompts

You can customize these prompts to fit your organisation's needs:

1. **Modify existing prompts** - Edit the markdown files directly
2. **Add specific requirements** - Include company-specific standards or policies
3. **Adjust output format** - Change how findings are structured
4. **Add custom focus areas** - Define new analysis categories

### Example Customizations

**Add compliance requirements:**
```markdown
ANALYSIS REQUIREMENTS:
- Check compliance with SOC 2 requirements
- Verify GDPR data handling practices
- Validate HIPAA encryption standards
```

**Add organisation-specific rules:**
```markdown
COMPANY POLICIES:
- All Azure Storage Accounts must have versioning enabled
- Virtual Machines must use approved marketplace images
- No public IP addresses allowed on VMs without approval
- All resources must include required tags (environment, owner, cost-center)
```

**Customize output format:**
```markdown
OUTPUT FORMAT:
1. **Executive Summary** - High-level overview for management
2. **Technical Details** - Detailed findings for engineers
3. **Action Items** - Prioritized list with owners and deadlines
```

## Testing Your Prompts

To test your custom prompts:

1. Make your changes to the prompt files
2. Commit and push them to your repository
3. Run the action in a workflow
4. Review the AI analysis output to verify it follows your custom requirements
5. Iterate on your prompts based on the AI responses

## Prompt Engineering Tips

- **Be specific** - Clear instructions produce better results
- **Use examples** - Show the format you want with examples
- **Set boundaries** - Define what to include and exclude
- **Prioritize** - Tell the AI what's most important
- **Structure matters** - Use markdown formatting for clarity

## Fallback Behavior

If the prompt files cannot be found, the action will use built-in fallback prompts to ensure the analysis continues without failure.
