# Skill Subsystem Documentation

## Overview

The **Skill Subsystem** in Dawei is a knowledge management and guidance system that provides domain-specific expertise to the AI agent. Skills are structured instruction sets stored as markdown files that guide agents on how to perform specialized tasks effectively.

## What is a Skill?

A **skill** is a specialized knowledge package consisting of:

1. **SKILL.md** - Main skill definition file containing:
   - **Frontmatter**: Metadata (name, description, version, etc.)
   - **Instructions**: Detailed workflow, best practices, code examples
   - **Guidance**: Step-by-step procedures for specific tasks

2. **Resources** (optional) - Supporting files in the same directory:
   - Templates
   - Code examples
   - Reference materials
   - Configuration files

### Skill File Format

```markdown
---
name: pdf
description: PDF processing and extraction workflows
version: 1.0.0
---

# PDF Processing Skill

## Overview
This skill provides comprehensive guidance for...

## Workflow
1. Step one...
2. Step two...

## Code Examples
\`\`\`python
# Example code
\`\`\`
```

## Architecture

### Storage Locations

Skills are stored in a hierarchical structure with priority-based resolution:

```
.dawei/
├── skills/                    # General skills
│   ├── pdf/
│   │   └── SKILL.md
│   ├── xlsx/
│   │   ├── SKILL.md
│   │   └── templates/
│   │       └── invoice.xlsx
│   └── frontend-design/
│       └── SKILL.md
├── skills-web/               # Mode-specific skills
│   └── responsive/
│       └── SKILL.md
```

### Priority Order (highest to lowest)

1. **Workspace General**: `{workspace}/.dawei/skills/`
2. **Workspace Mode-Specific**: `{workspace}/.dawei/skills-{mode}/`
3. **Global System**: `{DAWEI_HOME}/skills/`
4. **Global User**: `{DAWEI_HOME}/.dawei/skills/`
5. **Global Mode-Specific**: `{DAWEI_HOME}/skills-{mode}/`

Higher priority skills override lower priority skills with the same name.

## Core Components

### 1. SkillManager (`skill_manager.py`)

The central class that manages skill discovery, loading, and retrieval.

#### Key Methods

| Method | Description |
|--------|-------------|
| `discover_skills()` | Scans all root directories for skills |
| `get_all_skills()` | Returns all discovered skills sorted by priority |
| `find_matching_skills(query)` | Searches skills by keyword matching |
| `get_skill_content(skill_name)` | Loads complete skill content (lazy loading) |
| `get_skill_resources(skill_name)` | Returns resource files for a skill |

#### Skill Data Model

```python
@dataclass
class Skill:
    name: str                              # Unique identifier
    description: str                        # Brief description
    scope: Literal['workspace', 'system', 'user']  # Origin
    mode: str | None                        # Mode specificity
    directory: Path                         # Skill directory path
    content: str | None = None              # Lazy-loaded content
    resources: list[Path] | None = None     # Resource files
    priority: int = 0                       # Loading priority
```

### 2. Progressive Loading Strategy

The skill system uses a three-tier loading approach:

1. **Discovery Phase** (Fast)
   - Reads only frontmatter from SKILL.md
   - Minimal I/O for quick startup
   - Builds skill registry

2. **Content Loading** (On-Demand)
   - Loads full SKILL.md when agent requests it
   - Uses `get_skill_content()` method
   - Content cached after first load

3. **Resource Access** (As Needed)
   - Scans directory for additional files
   - Accessible via `read_skill_resource()` tool
   - Supports templates, examples, configs

### 3. Skill Tools (`skills_tool.py`)

Tools that agents use to interact with skills:

| Tool | Purpose |
|------|---------|
| `list_skills` | Display all available skills with metadata |
| `search_skills` | Find skills matching a query |
| `get_skill` | Load complete skill instructions |
| `list_skill_resources` | Show resource files for a skill |
| `read_skill_resource` | Read specific resource file content |

### 4. API Endpoints (`skills.py`)

REST API for skill management:

```
GET    /api/skills/list                    # List all skills
GET    /api/skills/search/{query}          # Search skills
GET    /api/skills/skill/{skill_name}      # Get skill metadata
GET    /api/skills/skill/{skill_name}/content    # Get skill content
POST   /api/skills/skill                   # Create new skill
PUT    /api/skills/skill/{skill_name}      # Update skill
DELETE /api/skills/skill/{skill_name}      # Delete skill
```

## Skill Usage Flow

### Agent Execution with Skills

```
┌──────────────────────────────────────────────────────────────────┐
│                         User Request                              │
└──────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  Agent: search_skills(query="extract tables from PDF")           │
└──────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  SkillManager: find_matching_skills()                            │
│  → Returns: [pdf skill (description: "...table extraction...")]  │
└──────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  Agent: get_skill(skill_name="pdf")                              │
└──────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  SkillManager: get_skill_content("pdf")                          │
│  → Returns: Full SKILL.md content with workflows                 │
└──────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  Agent: Follows skill instructions                               │
│  1. Uses pdf2image tool for conversion                           │
│  2. Uses pytesseract tool for OCR                                │
│  3. Uses pandas tool for table extraction                        │
└──────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                         Result Delivery                           │
└──────────────────────────────────────────────────────────────────┘
```

## Skills vs Tools

### Key Differences

| Aspect | Tools | Skills |
|--------|-------|--------|
| **Nature** | Executable functions | Instruction sets |
| **Purpose** | Perform actions | Guide how to use tools |
| **Implementation** | Python functions | Markdown documents |
| **Execution** | Direct invocation | Agent follows instructions |
| **Example** | `extract_pdf()` | How to combine OCR + table extraction |

### Relationship

- **Tools** provide capabilities
- **Skills** provide expertise in using those capabilities
- Skills complement tools, not replace them
- Skills are "knowledge assets" that elevate agent performance

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DAWEI_HOME` | Base directory for global skills | `~/.dawei` |
| `DAWEI_WORKSPACE` | Current workspace path | `./` |

### Workspace Mode

Skills can be mode-specific to support different workflows:

- `web` - Web development skills
- `data` - Data analysis skills
- `dev` - General development skills

Mode-specific skills override general skills when that mode is active.

## Creating Custom Skills

### Directory Structure

```bash
mkdir -p .dawei/skills/my-skill
cat > .dawei/skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: My custom skill for specialized tasks
version: 1.0.0
---

# My Custom Skill

## Purpose
This skill helps with...

## Prerequisites
- Tool 1 installed
- Tool 2 configured

## Workflow
1. First step...
2. Second step...

## Example
\`\`\`python
# Code example
\`\`\`
EOF
```

### Best Practices

1. **Clear Descriptions**: Frontmatter description should be searchable
2. **Step-by-Step Workflows**: Break down complex tasks
3. **Code Examples**: Provide working examples
4. **Prerequisites**: List required tools/configurations
5. **Error Handling**: Include common issues and solutions
6. **Resources**: Add templates or reference files when helpful

## Security Considerations

### Path Validation

- All skill paths are validated to prevent directory traversal
- Workspace skills are isolated from system paths
- System-level skills are protected from modification

### Access Control

- Workspace skills: Can be created/modified/deleted by user
- System skills: Read-only (cannot be deleted via API)
- User-level skills: Can be managed by user

## Integration Points

### With Agent System

1. **Agent Context**: Skills loaded into agent context at initialization
2. **Tool Executor**: Skill tools available during agent execution
3. **Prompt Template**: `skills.j2` provides skill guidance in system prompt

### With Workspace

1. **UserWorkspace**: Integrates skill tools into workspace operations
2. **Workspace Structure**: `.dawei/skills/` part of workspace layout
3. **Mode Support**: Workspace mode affects skill resolution

### With TUI

1. **SkillAwareInput**: TUI widget supports `@skill:` syntax highlighting
2. **Quick Access**: TUI provides skill discovery and browsing

## Performance Characteristics

### Discovery Performance

- **Lazy Frontmatter**: Only reads YAML frontmatter during discovery
- **Selective Loading**: Full content loaded only when needed
- **Caching**: Discovered skills cached in SkillManager

### Search Performance

- **Keyword Matching**: Simple string matching for search
- **Priority Sorting**: Results sorted by priority first
- **No Indexing**: Direct file scanning (sufficient for typical skill counts)

## Troubleshooting

### Common Issues

**Issue**: Skill not appearing in list
- **Solution**: Check SKILL.md frontmatter format
- **Solution**: Verify directory name matches `name` in frontmatter

**Issue**: Low priority skill overriding high priority
- **Solution**: Check scope definitions (workspace > system > user)

**Issue**: Resources not accessible
- **Solution**: Verify files are in same directory as SKILL.md
- **Solution**: Check file permissions

## Future Enhancements

Potential improvements to the skill system:

1. **Skill Versioning**: Support multiple versions of same skill
2. **Skill Dependencies**: Skills that require other skills
3. **Skill Indexing**: Full-text search across skill content
4. **Skill Validation**: Automated validation of skill quality
5. **Skill Marketplace**: Share and discover skills from community
6. **Skill Composition**: Combine multiple skills into workflows

## References

- **Implementation**: `agent/dawei/tools/skill_manager.py`
- **Tools**: `agent/dawei/tools/custom_tools/skills_tool.py`
- **API**: `agent/dawei/api/skills.py`
- **Prompt Template**: `agent/dawei/prompts/skills.j2`
- **TUI Integration**: `agent/dawei/tui/widgets/skill_aware_input.py`
