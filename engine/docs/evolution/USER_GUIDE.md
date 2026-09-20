# Evolution Feature - User Guide

## What is Evolution?

**Evolution** is a continuous improvement system that automatically iterates on your workspace using the PDCA (Plan-Do-Check-Act) methodology. It helps your workspace evolve and improve over time through automated cycles.

### How It Works

```
┌──────────────────────────────────────────────────────────┐
│                    Evolution Cycle                        │
├──────────────────────────────────────────────────────────┤
│  1. PLAN    - Analyze workspace and create plan          │
│  2. DO      - Execute the plan and track progress        │
│  3. CHECK   - Verify results against criteria            │
│  4. ACT     - Create action items for next cycle        │
│                  ↓                                      │
│            [Repeat continuously]                         │
└──────────────────────────────────────────────────────────┘
```

## Quick Start

### Step 1: Define Workspace Goals

Create a `.dawei/dao.md` file in your workspace:

```markdown
# Workspace: My Project

## Goals
- Improve code quality
- Reduce technical debt
- Enhance test coverage
- Optimize performance

## Success Criteria
- Code coverage > 80%
- No critical bugs
- Response time < 200ms
- Test suite passes
```

### Step 2: Enable Evolution

1. Open your workspace in DavyBot
2. Click the **Evolution** button (cycle icon) in the left sidebar
3. Toggle **"Enable Evolution"** to ON
4. Configure settings:
   - **Schedule**: How often to run cycles (e.g., `0 * * * *` for hourly)
   - **Phase Duration**: Max time per phase (e.g., `15m`)
   - **Max Cycles**: Maximum number of cycles (e.g., `999`)
   - **Goals**: Specific improvement goals
5. Click **"Save"**

### Step 3: Trigger First Cycle

Click **"Trigger Now"** to start the first evolution cycle immediately.

### Step 4: Monitor Progress

Watch the cycle progress:
- **Phase Progress Bar**: Shows current phase (PLAN → DO → CHECK → ACT)
- **Status Indicators**: Shows if cycle is running, paused, or completed
- **Current Cycle Card**: Displays real-time status

### Step 5: Review Results

After cycle completes:
1. Click **"View Details"** on the cycle
2. Review each phase output:
   - **PLAN**: What was planned
   - **DO**: What was executed
   - **CHECK**: Verification results
   - **ACT**: Actions for next cycle

## Understanding Phases

### PLAN Phase

**Purpose**: Analyze workspace and create improvement plan

**Inputs**:
- `.dawei/dao.md` - Your goals and success criteria
- Previous cycle's `action.md` - Actions from last cycle

**Output**: `plan.md` containing:
- Priority tasks from previous actions
- New tasks based on workspace goals
- Implementation approach
- Success metrics

**Example Output**:
```markdown
# Plan for Cycle 001

## Priority Tasks from Previous Actions
(First cycle - no previous actions)

## New Tasks Based on Workspace Goals
1. Add unit tests for core modules
2. Refactor large functions (>100 lines)
3. Update documentation

## Implementation Approach
- **Task 1**: Add tests using pytest
  - Expected: 80% coverage
  - Effort: Medium
  - Risk: Low

## Success Metrics
- Test coverage > 80%
- All tests pass
- Documentation updated
```

### DO Phase

**Purpose**: Execute the plan and track progress

**Inputs**:
- Current cycle's `plan.md`

**Output**: `do.md` containing:
- Task execution summary
- Detailed progress for each task
- Overall progress metrics
- Deviations from plan

**Example Output**:
```markdown
# Progress for Cycle 001

## Task Execution Summary
### Task: Add unit tests for core modules
- **Status**: ✅ Complete
- **Started**: 2025-03-26 10:00
- **Completed**: 2025-03-26 11:30
- **Actions Taken**: Created 25 test files
- **Results**: Coverage now 82%

## Overall Progress
- Total Tasks: 3
- Completed: 3
- In Progress: 0
- Failed: 0
```

### CHECK Phase

**Purpose**: Verify results against success criteria

**Inputs**:
- `.dawei/dao.md`
- Previous cycle's `action.md` (if exists)
- Current cycle's `plan.md`
- Current cycle's `do.md`

**Output**: `check.md` containing:
- Task verification checklist
- Workspace success criteria check
- Gap analysis
- Metrics and measurements
- Recommendations for next cycle

**Example Output**:
```markdown
# Verification for Cycle 001

## Task Verification Checklist
| Task | Status | Planned Outcome | Actual Result | Gap Analysis |
|------|--------|-----------------|---------------|-------------|
| Add tests | ✅ | 80% coverage | 82% | Exceeded |
| Refactor | ✅ | <100 lines | Done | Met |
| Update docs | ✅ | Updated | Updated | Met |

## Success Criteria Check
### Criteria Achieved ✅
- Code coverage > 80%: **82%** ✅
- No critical bugs: **0 bugs** ✅
```

### ACT Phase

**Purpose**: Create action items for next cycle

**Inputs**:
- `.dawei/dao.md`
- Current cycle's `plan.md`, `do.md`, `check.md`

**Output**: `action.md` containing:
- High priority actions for next cycle
- Medium priority actions
- Improvements identified
- Technical debt items
- Workspace goal updates (if needed)
- Lessons learned

**Example Output**:
```markdown
# Actions for Next Cycle

## High Priority Actions (Must Complete)
1. **Add integration tests**
   - Rationale: Current tests are unit-only
   - Success Criteria: 10 integration test scenarios
   - Estimated Effort: Medium

## Medium Priority Actions
1. **Set up CI/CD pipeline**
   - Rationale: Automate testing and deployment
   - Success Criteria: Pipeline runs on push
   - Estimated Effort: Large

## Lessons Learned
- Testing is easier with test utilities
- Documentation should be updated with code
```

## Controlling Cycles

### Pause a Cycle

Click the **Pause** button to pause at the next phase boundary.

**Use cases**:
- Need to intervene during execution
- Want to review progress before continuing
- System resource constraints

### Resume a Paused Cycle

Click the **Resume** button to continue execution.

### Abort a Cycle

Click the **Abort** button to stop the cycle.

**Result**:
- Current phase will complete
- Cycle marked as "aborted"
- New cycle can be started

**Use cases**:
- Cycle is going in wrong direction
- Emergency situation
- Need to start over with different configuration

## Viewing History

All completed cycles are stored in `.dawei/evolution-*/` directories.

### Access via UI

1. Scroll to **"Cycle History"** section
2. Click **"View"** on any cycle
3. Review all 4 phases

### Access via File System

```bash
# List all cycles
ls -la .dawei/evolution-*/

# View cycle 001 plan
cat .dawei/evolution-001/plan.md

# View cycle 001 action
cat .dawei/evolution-001/action.md

# View current cycle (symlink)
cat .dawei/evolution-current/plan.md
```

## Configuration Options

### Schedule (Cron Expression)

| Expression | Description |
|------------|-------------|
| `0 * * * *` | Every hour |
| `0 0 * * *` | Every day at midnight |
| `0 0 * * 0` | Every Sunday at midnight |
| `0 0 1 * *` | First day of every month |
| `*/30 * * * *` | Every 30 minutes |

**Format**: `minute hour day month weekday`

### Phase Duration

Maximum time for each phase:
- `5m` - 5 minutes
- `15m` - 15 minutes (default)
- `1h` - 1 hour

**Note**: This is a soft limit. Actual execution may vary.

### Max Cycles

Maximum number of cycles to run:
- `10` - Stop after 10 cycles
- `999` - Essentially unlimited (default)

**Behavior**: Evolution stops automatically when limit reached.

### Goals

Specific improvement goals (one per line):
```
improve code quality
reduce technical debt
enhance test coverage
optimize performance
```

## Best Practices

### 1. Start Simple

Begin with clear, achievable goals:
- ✅ Good: "Add tests for core modules"
- ❌ Bad: "Fix everything"

### 2. Define Success Criteria

Make goals measurable:
- ✅ Good: "Test coverage > 80%"
- ❌ Bad: "Improve quality"

### 3. Review Regularly

Check cycle history weekly:
- What worked well?
- What didn't work?
- What should change?

### 4. Iterate Gradually

Let cycles build on each other:
- Cycle 1: Add tests
- Cycle 2: Improve test quality
- Cycle 3: Add integration tests

### 5. Use Pause/Resume

Don't be afraid to intervene:
- Pause if something looks wrong
- Review and adjust
- Resume when ready

## Troubleshooting

### Cycle Not Starting

**Check**:
1. Is evolution enabled?
2. Is dao.md present?
3. Is another cycle already running?
4. Check server logs

**Solution**:
```bash
# View logs
tail -f dawei.log | grep EVOLUTION
```

### Phase Failing

**Check**:
1. LLM provider connectivity
2. Workspace has sufficient tokens
3. Agent execution permissions

**Solution**:
- Retry is automatic (3 attempts)
- Check agent mode configuration
- Verify LLM API key

### Schedule Not Triggering

**Check**:
1. Cron expression is valid
2. Previous cycle completed
3. Evolution is still enabled

**Solution**:
- Use cron validator: https://crontab.guru/
- Check previous cycle status
- Manually trigger to test

## Tips and Tricks

### 1. Manual Trigger for Testing

Use manual trigger to test before enabling schedule:
1. Configure with short schedule (e.g., `0 * * * *`)
2. Click "Trigger Now"
3. Review results
4. Adjust configuration if needed
5. Enable automatic scheduling

### 2. Delete Failed Cycles

Keep history clean by deleting failed cycles:
1. Click "Delete" on cycle
2. Confirm deletion
3. Directory removed from filesystem

### 3. Compare Cycles

Track progress over time:
1. View cycle 001 action.md
2. View cycle 002 plan.md
3. See if actions were addressed

### 4. Export Cycle Outputs

Archive important cycles:
```bash
# Export cycle 001
cp -r .dawei/evolution-001 ~/backups/
```

### 5. Customize Prompts

Evolution uses built-in prompts, but you can influence:
- Add context to dao.md
- Be specific in action.md
- Provide examples in goals

## Advanced Usage

### Custom Workspace Template

Create `.dawei/dao.md` template:

```markdown
# Workspace: {name}

## Context
{project description}

## Goals
{specific goals}

## Success Criteria
{measurable criteria}

## Constraints
{limitations and boundaries}

## Notes
{additional context}
```

### Integration with CI/CD

Add evolution cycle to your pipeline:

```yaml
# .github/workflows/evolution.yml
name: Evolution Cycle
on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly
jobs:
  evolution:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Evolution
        run: |
          curl -X POST $DAWIBOT_API/evolution/trigger
```

### Monitoring with Alerts

Set up alerts for cycle completion:

```python
# Custom monitoring script
import requests

def check_evolution_status():
    response = requests.get(
        f"{API_BASE}/evolution/status"
    )
    status = response.json()

    if status['current_cycle']:
        cycle_id = status['current_cycle']['cycle_id']
        state = status['current_cycle']['status']

        if state == 'completed':
            print(f"Cycle {cycle_id} completed!")
            # Send notification
            send_notification(f"Evolution Cycle {cycle_id} completed")
```

## Examples

### Example 1: Code Quality Evolution

**Goal**: Improve code quality over time

**Configuration**:
- Schedule: `0 0 * * 0` (weekly)
- Phase Duration: `30m`
- Max Cycles: `52` (one year)
- Goals:
  ```
  reduce code complexity
  improve test coverage
  fix linting issues
  update documentation
  ```

**Expected Progress**:
- Week 1-4: Add tests
- Week 5-8: Improve coverage
- Week 9-12: Reduce complexity
- Week 13-52: Iterative improvements

### Example 2: Performance Optimization

**Goal**: Optimize application performance

**Configuration**:
- Schedule: `0 * * * *` (hourly during work day)
- Phase Duration: `15m`
- Max Cycles: `100`
- Goals:
  ```
  reduce response time
  optimize database queries
  cache frequently accessed data
  profile bottlenecks
  ```

**Expected Progress**:
- Each cycle targets specific optimization
- Continuous monitoring and adjustment
- Gradual performance improvement

### Example 3: Documentation Updates

**Goal**: Keep documentation up to date

**Configuration**:
- Schedule: `0 0 * * *` (daily)
- Phase Duration: `10m`
- Max Cycles: `30`
- Goals:
  ```
  update API docs
  add code examples
  improve tutorials
  fix broken links
  ```

**Expected Progress**:
- Daily documentation updates
- Improved user onboarding
- Better developer experience

## Resources

- **Design Document**: `/docs/design.md`
- **Testing Guide**: `/docs/evolution/TESTING.md`
- **API Documentation**: `/docs/api/evolution.md`
- **GitHub Issues**: Report bugs and feature requests

## Support

For issues or questions:
1. Check troubleshooting section
2. Review test documentation
3. Check server logs: `tail -f dawei.log | grep EVOLUTION`
4. Open GitHub issue with details

## Changelog

### Version 1.0.0 (2025-03-26)
- Initial release
- PDCA cycle implementation
- Pause/resume/abort support
- Manual and scheduled triggers
- Full UI integration
- Multi-workspace support
