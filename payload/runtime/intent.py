"""Owner working rules that apply to every prompt: reply voice and discuss-before-build.

Discuss turn: the owner presents an idea, bug or problem. The agent researches, proposes,
weighs trade-offs and waits for "go". Classification, in order:
  1. An opening go ("go", "ok, go ahead", "go on the proposal") ends discussion.
  2. A strong marker (idea, what if, should we, trade-offs...) is always discussion.
  3. An order (starts with a build verb, or says "fix it") is work, not discussion.
  4. A weak marker (bug, broken, fails...) without an order is discussion.
  5. Anything else keeps the previous turn's state, so "no" or "wait" never opens edits.
"""
import re

GO = re.compile(r"^\W*((ok(ay)?|yes|yep|alright|sure|great|cool|good)\W+)?"
                r"(go|go ahead|do it|proceed|ship it|implement it|build it|approved|lgtm|"
                r"let'?s do it|start building|yes,? (do|build|implement))\b", re.I)
STRONG = re.compile(r"\b(ideas?|what if|should we|could we|how about|thoughts|propos(e|al)|"
                    r"trade-?offs?|alternatives?|research|i prefer|i think|maybe we|consider|"
                    r"brainstorm|opinions?|pros and cons)\b", re.I)
WEAK = re.compile(r"\b(bugs?|issues?|problems?|broken|fail(s|ing|ed)?|crash(es|ing)?|errors?|"
                  r"wrong|doesn'?t work|not working|improve)\b", re.I)
VERBS = (r"add|fix|rename|update|remove|delete|create|implement|build|change|make|write|run|"
         r"ensure|set|move|refactor|improve|replace|bump|merge|commit|push|install|deploy|"
         r"migrate|revert|test|document|wire|hook|port|convert|split|extract|delete")
ORDER = re.compile(r"^\W*((please|pls|can you|could you|now)\W+)*(%s)\b|\b(fix|do) it\b" % VERBS, re.I)

VOICE = ("Reply style (owner rule): brief. ASD-STE100: max 20 words per sentence, active voice, "
         "one term per thing, imperative for instructions. When a step needs the owner (a login, "
         "an approval, a value only they have), give numbered step-by-step instructions.")
DISCUSS_RULE = ("DISCUSS mode (owner rule): the owner presented an idea, bug or problem and has "
                "not said go. Do not edit files, commit or push. Research, propose, name the "
                "trade-offs, weigh options, find alternatives, refine the wording. End by asking "
                "if we are ready, then wait for the owner's go. File edits are blocked until then.")


def is_go(text):
    return bool(GO.match(text or ""))


def is_order(text):
    return bool(ORDER.search(text or ""))


def classify(text, previous=False):
    """True for a discuss turn. `previous` is the last turn's state, kept on a neutral reply."""
    text = text or ""
    if is_go(text):
        return False
    if STRONG.search(text):
        return True
    if is_order(text):
        return False
    if WEAK.search(text):
        return True
    return bool(previous)


def is_discuss(text):
    return classify(text)


def rules(text, cfg, previous=False):
    """The rule lines for this prompt, and whether it is a discuss turn."""
    lines, discuss = [], False
    if cfg.get("voice", True):
        lines.append(VOICE)
    if cfg.get("discuss_gate", "block") != "off" and classify(text, previous):
        lines.append(DISCUSS_RULE)
        discuss = True
    return " ".join(lines), discuss
