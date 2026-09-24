# Limitations

Stated plainly, because claiming capabilities that do not exist is the failure mode this
system is built to prevent.

1. **No background execution.** Claude Code has no persistent worker process, so the Agentic
   OS does not run tasks on its own. The queue is durable state that makes work resumable;
   an agent in a session does the work. `aos queue ready` is how the next session finds it.

2. **The runtime plans and records; the model reasons.** `workflow.plan`, the classifiers and
   the router produce decisions and context. They do not execute agents — Claude Code's Task
   tool does, following the agent definitions.

3. **Classification is heuristic.** Difficulty and risk come from configurable phrase signals,
   not from understanding. They are deliberately conservative (risk floors only escalate), and
   the router agent is instructed to report disagreement so the config can improve.

4. **The completion audit's criterion matching is a word-overlap heuristic.** It flags missing
   evidence for a human or the reviewer agent; it does not judge semantic satisfaction.

5. **Guards are pattern-based.** They cover the known dangerous classes and eleven tested
   evasion techniques, and the strictest verdict across every command fragment wins. A
   determined adversary with shell access can still construct something novel; guards are a
   safety net for an agent's mistakes, not a sandbox.

6. **Model availability detection is best-effort.** If the environment does not expose a model
   list, `aos models` reports the tier's model as an unverified assumption rather than
   claiming it is confirmed.

7. **Learning needs volume.** Promotion requires three challenger runs against a champion
   baseline. On a project with few recorded runs, nothing will be promoted — correctly.

8. **Hooks fail open.** If the runtime cannot be imported, the PreToolUse hook exits without a
   verdict rather than breaking every tool call. A broken installation therefore removes
   protection silently; `agentic-os doctor` is the check for that.

9. **Skills are read, not enforced.** A skill changes behaviour by being loaded into context.
   The two executable skill checkers (`anti-ai-slop`, `design-taste`) are the exception.
