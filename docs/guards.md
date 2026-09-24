# Guards and tool policy

(For the automatic prompt-time planning hook, see `docs/automatic-mode.md`.)

## Autonomy

`config/tools.json` lists the tools and command families that are auto-approved for ordinary
engineering: read, search, edit, write, test, lint, format, typecheck, build, git inspection,
staging and committing. Agents should not ask permission for these.

## Guards

Every Bash command and every file write passes `runtime/guards.py` through the PreToolUse
hook. Verdicts:

| Verdict | Effect |
|---|---|
| `ALLOW` | proceeds silently |
| `CONFIRM` | the user is asked, with the reason |
| `REVIEW_REQUIRED` | the user is asked; intended for irreversible or outward-facing actions |
| `BLOCK` | denied |

Covered classes: destructive filesystem operations, device writes, permission widening,
force push and history rewriting, hard reset and clean, remote branch deletion, `DROP` /
`TRUNCATE` / unqualified `DELETE`, database CLIs pointed at production, deployments, cloud
resource deletion, credential reading and exfiltration, piping the network into a shell,
`sudo` and system configuration, package publishing, and anti-forensic history destruction.

## Bypass resistance

Commands are normalised (in-word quotes, backslash escapes, `${IFS}`), split across
`;` `|` `&&` `||` and newlines, recursed into `$(...)` and backticks, and base64 blobs are
decoded and re-inspected. The strictest verdict across all fragments wins. The test suite
exercises eleven evasion techniques — quote splitting, chaining, subshells, pipelines,
nested shells, IFS substitution, encoding — and requires each to be blocked.

Agents are instructed never to route around a guard, and the learning system cannot weaken
one: the safety floor rejects any candidate policy touching guards, approvals, tests,
privacy, or destructive capability, both at proposal time and again at promotion time.

## Checking a command yourself

```bash
aos guard 'git push --force origin main'    # -> REVIEW_REQUIRED, with the reason
aos guard-path .env                         # -> CONFIRM, protected path
```

## Editing the rules

`config/guards.json`. Each rule is `{id, action, why, regex}`. Add rules freely; the
`immutable_keys` field marks what learning may never rewrite.
