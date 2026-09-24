"""A pasted transcript is context, not the task.

Measured before the fix: pasting a session excerpt and asking "is this the new agentic os?"
classified level 5 and inlined 27 skills / 10.8KB. The question is level 1.
"""
import json
import os
import subprocess
import sys

from helpers import PAYLOAD

HOOKS = os.path.join(PAYLOAD, "hooks")
ENV = dict(os.environ, AOS_HOME=PAYLOAD)

PASTE = """is this the new agentic os? I'll start by reading the current dashboard implementation.

  Searched for 3 patterns, read 7 files, ran 7 shell commands
Loaded .claude/rules/frontend.md
Loaded .claude/rules/error-handling.md

I've read the current implementation. The six-mode architecture is already built - modes,
sub-modes, role landing, exception-driven copy. So what you are reacting to is the visual
execution, not the architecture. My read of what is actually wrong:

- You are being greeted by the wrong name. roster.items[0] is the shop's oldest-created
  staff member, not you - and for non-owners it is blank.
- Tonal monotony. Every block is the same 12px grey label over the same hairline-divided
  list - six of them stacked. Nothing carries weight, so nothing is scannable.
- Filler labels: "Summary", "Additional actions", "Where this stands".
- The mode bar is a dropdown, so five of your six business areas are invisible. The
  cascade that is the whole point of the doc never appears on screen.

  User answered Claude's questions
  - The six modes are currently behind a dropdown. Reverse it? -> Visible bar, all six
  - How far should the visual redesign go? -> Visual + copy, same data

  $ sed -n 1,60p "app/(jeweler)/home/RecentDesigns.tsx"
"""

REAL_LONG_TASK = (
    "redesign the jeweler dashboard so the six modes are a visible bar instead of a "
    "dropdown, rework the visual hierarchy so the page stops reading as six identical "
    "grey lists, replace the filler section labels with specific ones, and fix the "
    "greeting so it uses the signed-in user and the actual hour. " * 4
)


def ctx(prompt):
    r = subprocess.run([sys.executable, os.path.join(HOOKS, "user_prompt_submit.py")],
                       input=json.dumps({"prompt": prompt}), capture_output=True,
                       text=True, env=ENV)
    assert r.returncode == 0, r.stderr
    if not r.stdout.strip():
        return None
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


def test_pasted_transcript_does_not_inflate_the_level():
    c = ctx(PASTE)
    assert c is not None
    assert "level 5/5" not in c, c[:200]
    assert c.count("<skill name=") <= 2, "a question about a paste must not load the library"
    assert len(c) < 6000, len(c)


def test_a_genuinely_long_task_still_classifies_high():
    c = ctx(REAL_LONG_TASK)
    assert "level 1/5" not in c, c[:200]
    assert "<skill name=" in c, "real work still gets its skills"


def test_short_prompts_are_unaffected():
    sys.path.insert(0, HOOKS)
    import user_prompt_submit as u  # noqa: E402
    short = "add a graduation-year filter to the alumni list page"
    assert u.task_text(short, {}) == short


def test_the_recorded_turn_uses_the_trimmed_subject():
    sys.path.insert(0, HOOKS)
    import user_prompt_submit as u  # noqa: E402
    subject = u.task_text(PASTE, {})
    assert len(subject) <= 600
    assert "is this the new agentic os" in subject.lower()
    assert "roster.items[0]" not in subject
