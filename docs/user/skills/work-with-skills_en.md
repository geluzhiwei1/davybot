# Working with Skills - User Guide

## Introduction

**Skills** are Dawei's way of sharing expertise and best practices. Think of them as "how-to guides" that help the AI assistant perform specialized tasks more effectively.

When you give Dawei a task, it can reference relevant skills to ensure it follows proven workflows and industry best practices.

### What Problems Do Skills Solve?

- **Inconsistency**: Different approaches to the same task each time
- **Re-explanation**: Repeatedly explaining how you like things done
- **Best Practices**: Ensuring the agent uses proven methods
- **Complex Workflows**: Multi-step processes that require specific expertise

## Understanding Skills

### Skill Structure

A skill consists of:

```
my-skill/
├── SKILL.md              # Main instructions (required)
├── template.py           # Example templates (optional)
├── config.json           # Reference configs (optional)
└── README.md             # Additional docs (optional)
```

### What's Inside a Skill?

Open any `SKILL.md` and you'll find:

```markdown
---
name: pdf
description: PDF processing, OCR, and extraction workflows
---

# PDF Processing Skill

This skill guides you through working with PDF files...

## Common Workflows

### Extract Text from PDF
1. Use the pdf_extractor tool...
2. For scanned PDFs, first apply OCR...

### Extract Tables
1. Convert PDF to images...
2. Use OCR with table detection...
```

## Discovering Available Skills

### Via CLI

List all available skills:

```bash
# See all skills
dawei skills list

# Search for specific skills
dawei skills search pdf
dawei skills search "table extraction"
dawei skills search web
```

### Via TUI

In the TUI (Text User Interface), use the `@skill:` syntax:

```
# While typing your request
User: @skill:pdf How do I extract tables from a scanned PDF?
```

The TUI will:
1. Show available skills that match your query
2. Auto-suggest skill names as you type `@skill:`
3. Display skill descriptions for preview

### Via Web UI

Access skills through the web interface:
- Navigate to **Skills** section
- Browse all available skills
- Search by keyword
- View skill details and resources

## Using Skills

### Implicit Usage (Recommended)

Just describe your task naturally - Dawei will automatically find relevant skills:

```
User: Extract tables from this scanned PDF document

# Dawei automatically:
# 1. Searches for relevant skills (finds "pdf" skill)
# 2. Loads the skill instructions
# 3. Follows the recommended workflow for table extraction
# 4. Uses appropriate tools (pdf2image, OCR, table extraction)
```

### Explicit Usage

Request a specific skill directly:

```
User: @skill:pdf Help me process this invoice PDF

# Dawei will:
# 1. Load the pdf skill
# 2. Apply pdf-specific workflows
# 3. Use recommended tools and settings
```

### Practical Examples

#### Example 1: PDF Processing

```
User: I have a scanned contract PDF. I need to extract all the text

# What Dawei does (using pdf skill):
# 1. Recognizes this is a PDF task
# 2. Loads the pdf skill
# 3. Follows the OCR workflow for scanned PDFs
# 4. Uses pdf2image + pytesseract
# 5. Returns extracted text with confidence scores
```

#### Example 2: Excel Processing

```
User: Summarize the sales data in this Excel file

# What Dawei does (using xlsx skill):
# 1. Loads the xlsx skill
# 2. Reads the Excel file structure
# 3. Identifies data patterns
# 4. Creates summary statistics
# 5. Generates insights following xlsx best practices
```

#### Example 3: Web Development

```
User: @skill:frontend-design Create a responsive dashboard layout

# What Dawei does (using frontend-design skill):
# 1. Loads frontend design skill
# 2. Follows responsive design principles
# 3. Uses recommended CSS frameworks
# 4. Implements accessibility best practices
# 5. Generates clean, maintainable code
```

## Creating Custom Skills

### When to Create a Custom Skill

Create a skill when you:
- Have specific preferences for how tasks should be done
- Work in a specialized domain often
- Want to document team best practices
- Have complex workflows you repeat frequently

### Step-by-Step: Create Your First Skill

#### Step 1: Create the Skill Directory

Skills live in your workspace under `.dawei/skills/`:

```bash
# Navigate to your workspace
cd my-workspace

# Create a new skill directory
mkdir -p .dawei/skills/my-custom-skill
cd .dawei/skills/my-custom-skill
```

#### Step 2: Write SKILL.md

Create the main skill file:

```markdown
---
name: my-custom-skill
description: Custom workflows for my specific needs
version: 1.0.0
author: Your Name
---

# My Custom Skill

## Purpose
This skill helps with [specific task] by following [your approach].

## Prerequisites
- Tool A is installed
- Configuration B is set up

## Workflow

### Step 1: Preparation
Always start by...
- Check for X
- Verify Y

### Step 2: Execution
Follow these steps:
1. First, do this...
2. Then, do that...
3. Finally, validate Z

### Step 3: Verification
Ensure the result meets these criteria:
- Criteria 1
- Criteria 2

## Common Patterns

### Pattern 1: [Name]
When [situation], use this approach:
\`\`\`python
# Example code
result = do_something()
\`\`\`

### Pattern 2: [Name]
For [different situation], do:
\`\`\`python
# Alternative approach
result = do_something_else()
\`\`\`

## Troubleshooting

### Issue: [Problem]
**Solution**: [Fix]

### Issue: [Another Problem]
**Solution**: [Different fix]

## Resources
- Link to external documentation
- Reference materials
```

#### Step 3: Add Optional Resources

Include helpful files in the same directory:

```bash
# Add a template
cat > template.py << 'EOF'
def example_function():
    """Template function"""
    pass
EOF

# Add a configuration example
cat > config.example.json << 'EOF'
{
    "setting1": "value1",
    "setting2": "value2"
}
EOF
```

#### Step 4: Test Your Skill

```bash
# Verify Dawei can find it
dawei skills list | grep my-custom-skill

# Test using it
dawei agent run ./my-workspace "@skill:my-custom-skill Help me with..."
```

### Real-World Skill Examples

#### Example: Git Workflow Skill

```markdown
---
name: git-workflow
description: Git branching and commit conventions for our team
version: 1.0.0
---

# Team Git Workflow

## Branch Naming
- Feature branches: `feature/ISSUE-DESCRIPTION`
- Bugfix branches: `bugfix/ISSUE-DESCRIPTION`
- Hotfix branches: `hotfix/VERSION-DESCRIPTION`

## Commit Messages
Format: `ISSUE: Brief description`

Example: `DAWEI-123: Add user authentication`

## Workflow
1. Create feature branch from main
2. Make commits with proper messages
3. Push to remote
4. Create PR with template
5. Request review
6. Address feedback
7. Merge after approval

## PR Template
\`\`\`
## Summary
- [ ] Change 1
- [ ] Change 2

## Testing
- [ ] Unit tests pass
- [ ] Manual testing done
\`\`\`
```

#### Example: Code Review Skill

```markdown
---
name: code-review
description: Code review guidelines and checklist
version: 1.0.0
---

# Code Review Guidelines

## Checklist
- [ ] Code follows project style guide
- [ ] No hardcoded secrets
- [ ] Error handling implemented
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No obvious performance issues
- [ ] Security vulnerabilities checked

## What to Look For

### Security
- SQL injection vulnerabilities
- XSS vectors
- Auth/authorization issues
- Sensitive data in logs

### Performance
- N+1 query problems
- Missing indexes
- Unnecessary loops
- Memory leaks

### Maintainability
- Clear variable names
- Appropriate comments
- Function length < 50 lines
- DRY principle followed
```

## Skill Management

### Viewing Skills

```bash
# List all skills
dawei skills list

# View skill details
dawei skills get pdf

# View skill content
dawei skills content pdf
```

### Updating Skills

Edit the `SKILL.md` file directly:

```bash
# Workspace skill (editable)
vim .dawei/skills/my-skill/SKILL.md

# Changes take effect immediately
```

### Deleting Skills

```bash
# Remove workspace skill
rm -rf .dawei/skills/my-skill

# Note: System skills cannot be deleted
```

## Organizing Skills

### By Domain

```
.dawei/skills/
├── development/
│   ├── python/
│   ├── javascript/
│   └── testing/
├── data/
│   ├── analysis/
│   └── visualization/
└── ops/
    ├── deployment/
    └── monitoring/
```

### By Workflow

```
.dawei/skills/
├── data-processing/
├── report-generation/
├── code-review/
└── deployment/
```

### By Project

```
.dawei/skills/
├── project-alpha/
├── project-beta/
└── common/
```

## Skill Modes

Skills can be mode-specific to adapt to different contexts:

```bash
# General skills (always available)
.dawei/skills/
└── common/

# Web development mode
.dawei/skills-web/
└── frontend/

# Data analysis mode
.dawei/skills-data/
└── visualization/
```

When you set a workspace mode, Dawei prioritizes mode-specific skills:

```bash
# Set workspace mode
dawei workspace set-mode web

# Now web-specific skills are prioritized
```

## Best Practices

### Writing Good Skills

1. **Be Specific**: Clear, actionable instructions
2. **Provide Examples**: Show, don't just tell
3. **Include Edge Cases**: What to do when things go wrong
4. **Keep Updated**: Review and revise regularly
5. **Version Control**: Track changes to skills

### Skill Design Principles

1. **Single Purpose**: Each skill should focus on one domain
2. **Progressive**: Start simple, add detail gradually
3. **Testable**: Skills should produce consistent results
4. **Maintainable**: Easy to update and improve

### Common Mistakes to Avoid

- ❌ Skills that are too generic
- ❌ Missing edge cases
- ❌ Outdated information
- ❌ Unclear workflows
- ❌ Missing examples

## Advanced Usage

### Skill Composition

Skills can reference other skills:

```markdown
## Workflow
1. First, apply @skill:setup-environment
2. Then, use @skill:build-process
3. Finally, run @skill:deploy-checklist
```

### Conditional Logic

Guide the agent with conditionals:

```markdown
## Approach Selection

If the file is larger than 100MB:
- Use streaming approach
- Process in chunks

If the file is smaller:
- Load entirely into memory
- Process all at once
```

### Resource Files

Include templates for the agent to use:

```markdown
## Template

Use the template from template.py as a starting point.

The agent can access it with:
```
read_skill_resource(skill_name="my-skill", resource="template.py")
```
```

## Troubleshooting

### Skill Not Found

**Problem**: Dawei doesn't see your skill

**Solutions**:
1. Check directory structure: `.dawei/skills/your-skill/SKILL.md`
2. Verify frontmatter has `name` field
3. Ensure `name` matches directory name
4. Run `dawei skills list` to verify

### Wrong Skill Loaded

**Problem**: Lower priority skill overriding higher priority

**Solutions**:
1. Check skill locations (workspace > system > user)
2. Verify mode-specific vs general skills
3. Remove duplicate skill names

### Skill Not Applied

**Problem**: Dawei not following your skill

**Solutions**:
1. Make task description more explicit
2. Use `@skill:name` to force specific skill
3. Check that skill instructions are clear
4. Verify skill is relevant to the task

## Tips & Tricks

### Quick Skill Discovery

```bash
# Find skills related to a topic
dawei skills search "data"

# See what resources a skill has
dawei skills resources pdf

# Preview skill content
dawei skills content pdf | head -50
```

### Skill Versioning

Track versions in frontmatter:

```markdown
---
version: 2.1.0
changelog:
  - 2.1.0: Added OCR workflow
  - 2.0.0: Major restructure
  - 1.0.0: Initial release
---
```

### Team Collaboration

Share skills through version control:

```bash
# Commit skills to git
git add .dawei/skills/
git commit -m "Add data processing skill"

# Team members can pull updates
git pull
```

## Summary

- **Skills** are expert knowledge that guides Dawei's behavior
- **Discover** skills with `@skill:` syntax or natural language
- **Create** custom skills for your specific workflows
- **Organize** skills by domain, project, or workflow
- **Maintain** skills as living documents that evolve with your needs

Skills are a powerful way to make Dawei more effective for your specific use cases. Start with the built-in skills, then create your own as you discover patterns in your work.
