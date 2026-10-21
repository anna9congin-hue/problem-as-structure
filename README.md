# problem-as-structure

An [Agent Skill](https://agentskills.io) for solving hard, multi-constraint real-world problems *with* a user, and saving each solve as a reusable, inspectable case: the problem's approximate archetype, the solution-space graph, the full exploration trail (what was tried, pruned, parked, and the conflict cores), the verification done in the original problem, and the final plan.

一个 Agent Skill：和用户一起求解多约束的复杂现实问题，并把每次求解存成可复用、可检查的案例——问题的近似母题、解空间图、完整探索过程（已尝试、已淘汰、已搁置、冲突核）、在原问题里做的验证，以及最终方案。

## Idea

Most agent conversations throw away the structure behind a hard problem. You watch an assistant try option after option, hit walls, and sometimes give up — while the answer sat in an option it dropped 200 turns earlier for a weak reason. This skill makes the structure a first-class, persisted object:

1. **Collect constraints first.** Hard constraints and soft preferences are kept separate. A soft preference may only *park* a candidate, never *prune* it. An unverified fact may never prune.
2. **Pick an approximate archetype** (constraint satisfaction, bootstrapping, bottleneck/shadow-price, inference, search, …) and a good representation. No strict proof is required; correctness is checked by engineering means in the original problem.
3. **Expand, prune, and park** the solution space as a typed graph.
4. **On repeated failure, extract the conflict core and backjump** to a higher level instead of trying the next sibling.
5. **Verify in the original problem** — a real attempt, running code, checking source text, or user confirmation. Reasoning inside the archetype is not verification.
6. **Save everything** so similar problems can reuse the archetype, the reusable constraint knowledge, and the conflict cores.

The method and its rationale come from the "problem as structure, language as shell" line of work. See `references/`.

## Layout

```
SKILL.md                     # the protocol the agent follows
references/case_schema.md     # case.json field reference
references/archetypes.md      # starter library of 12 approximate archetypes
references/soft_constraints.md  # relative, dynamic soft constraints ("too expensive", "too slow", ...)
references/delegation.md      # handing tasks to other agents: delivery quality ≈ verifier quality
scripts/case_tool.py          # new / check / render / index  (Python 3 stdlib only)
```

## The tool

`case_tool.py` has no third-party dependencies.

```bash
python3 scripts/case_tool.py new --slug <short-name> --title "<title>" [--origin retro]
python3 scripts/case_tool.py render <case-dir>   # validate + write tree.md, graph.canvas and progress.html
python3 scripts/case_tool.py html   <case-dir>    # write progress.html only
python3 scripts/case_tool.py check  <case-dir>    # validate only
python3 scripts/case_tool.py index                # rebuild INDEX.md
```

`render` and `check` enforce the method as hard errors (pruning by a soft preference, by an unverified hard constraint, or by an unverified fact) and as rule reminders (unextracted conflict core after repeated failure; parked candidates not re-reviewed once all live candidates are out).

`progress.html` is an offline, single-file progress dashboard (stages, pending decisions, running tasks, the solution tree, claims) that auto-refreshes every 10 seconds.

Optional **claims ledger** (`claims[]`): outward-facing statements (paper claims, investment theses) with frozen wording, coverage, status, and typed dependencies (`conclusion`, `method`, `cites`). The verification level V0–V3 is computed from verification records, never hand-entered. When an upstream claim is withdrawn, `check` flags the downstream claims that depend on its conclusion or method (`规则·连带`) and only asks citing claims to update their reference.

The case library location is chosen by, in order: `--root`, the `PROBLEM_CASES_DIR` environment variable, or the default path baked into the script. Set `PROBLEM_CASES_DIR` to point the tool at your own case library.

Each case is one directory: `case.json` is the single source of truth; `tree.md`, `graph.canvas` (an Obsidian Canvas file) and `progress.html` are generated; `INDEX.md` is the library-wide table with per-case sample metrics.

## Install

Copy the `problem-as-structure/` directory into your agent's skills directory:

- Kiro: `~/.kiro/skills/`
- Codex: `~/.codex/skills/`
- Gemini CLI / Antigravity: `~/.gemini/config/skills/`
- Claude Code or any Agent Skills host: that host's skills directory, or point the agent at `SKILL.md` directly.

## License

MIT. See `LICENSE`.
