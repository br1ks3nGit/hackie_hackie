# AGENTS.md - Kimi Code CLI

Instruction file for Kimi Code CLI sessions in this repo. Local-only (listed in .gitignore), same
as CLAUDE.md.

CLAUDE.md is canonical for all project rules: layout, stack, tooling, hard limits, hard rules, git
rules, code rules, output rules. Read CLAUDE.md and docs/roadmap.md before planning any task. If
this file and CLAUDE.md disagree, CLAUDE.md wins; report the drift and fix this file. User
instructions override both.

## What differs from CLAUDE.md: orchestration only

Kimi is not Claude Code, so the Claude-native machinery does not load here:
- `.claude/agents/` and `.claude/skills/` are not registered as native subagents or skills.
- `.claude/settings.json` (permissions, hooks) does not apply; Kimi uses its own permission config.
- Haiku/Sonnet/Opus model assignments do not apply; all subagents run on the configured model.

The workflow itself is unchanged. The main session is the director: it plans, delegates, reviews,
and decides. Kimi subagent types (Agent tool):
- `explore`: read-only search, review, and web lookups.
- `plan`: read-only implementation planning.
- `coder`: edits files, runs commands, makes commits.
- `AgentSwarm`: fans one task template out over many files in parallel.

### Team mapping
Reuse the Claude agent briefs as delegation prompts; they are plain markdown.

| CLAUDE.md role | Kimi subagent | Brief file |
|---|---|---|
| web-researcher | explore | .claude/agents/web-researcher.md |
| designer | explore (spec/review), coder (assets) | .claude/agents/designer.md |
| coder | coder | .claude/agents/coder.md |
| linter | coder | .claude/agents/linter.md |
| reviewer | explore | .claude/agents/reviewer.md |
| database-reviewer | explore | .claude/agents/database-reviewer.md |
| committer | coder | .claude/agents/committer.md |
| pr-checker | explore | .claude/agents/pr-checker.md |

Review roles must stay read-only: always use `explore`, never `coder`, for reviewer,
database-reviewer, designer (review mode), and pr-checker.

### Skills
Read `.claude/skills/<name>/SKILL.md` on demand when a task matches; they are reference material,
not auto-loaded. Inventory and ownership (project vs ECC) are in .claude/README.md.

### Pipeline and escalation
Unchanged from CLAUDE.md: small incremental PRs; plan -> prepare -> build -> verify -> fix loop
(max 2 rounds) -> commit -> pr-check. Always ask the user before `git push` or `gh pr create`;
never merge, never force-push. Branch off an up-to-date main; per user direction, Kimi work uses
branches KA1, KA2, and so on, unless the user says otherwise. Nothing is coded without user
authorization.

### Delegation discipline
Same as CLAUDE.md token discipline: compact briefs (goal, file paths, acceptance criteria); point
to files, never paste contents; short structured reports back (verdict + file:line findings);
workers never delegate; reuse earlier results instead of re-reading unchanged files.
