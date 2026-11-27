"""Owner working rules that apply to every prompt: reply voice and discuss-before-build.

Discuss turn: the owner presents an idea, bug, problem or question. The agent researches,
proposes, weighs trade-offs and waits for "go". Discussion is the DEFAULT; keyword lists
for bug reports measured 28% misses. Classification, in order:
  1. A negated opening ("no", "not yet", "wait", "don't") stays in discussion.
  2. An approval ("go", "yes", "sounds good, proceed", "let's go with B") opens edits.
  3. A verb-first order ("fix the footer", "can you add a link") opens edits, unless it
     also carries an idea word (idea, what if, propose, research, trade-offs...).
  4. Everything else is discussion.
"""
import re

NEGATED = re.compile(r"^\W*(no|nope|not yet|not now|wait|hold on|hold off|stop|don'?t|do not)\b", re.I)
GO = re.compile(r"^\W*((ok(ay)?|yes|yep|yeah|alright|sure|great|cool|good|perfect)\W+)?"
                r"(go|go ahead|go for it|do it|proceed|ship it|implement it|build it|approved?|"
                r"lgtm|let'?s (go|do it|build)|start building|yes,? (do|build|implement))\b", re.I)
APPROVAL = re.compile(r"^\W*(yes|yep|yeah|y|sure|ok(ay)?|k|sounds good|looks good|perfect|great|"
                      r"agreed|approve[ds]?|lgtm|👍|✅)(\W+(please|thanks|thank you))?\W*$", re.I)
TRAILING_GO = re.compile(r"\b(proceed|go ahead|go for it|do it|ship it|build it)\W*$", re.I)
STRONG = re.compile(r"\b(ideas?|what if|should we|could we|how about|thoughts|propos(e|al)|"
                    r"trade-?offs?|alternatives?|research|i prefer|i think|maybe we|consider|"
                    r"brainstorm|opinions?|pros and cons)\b", re.I)
VERBS = (r"add|fix|rename|update|remove|delete|create|implement|build|change|make|write|run|"
         r"ensure|set|move|refactor|improve|replace|bump|merge|commit|push|install|deploy|"
         r"migrate|revert|test|document|wire|hook|port|convert|split|extract|start|stop|open|"
         r"close|publish|release|upgrade|enable|disable|apply|clean|restore|use")
ORDER = re.compile(r"^\W*((please|pls|can you|could you|now|also|then|and)\W+)*(%s)\b|"
                   r"\b(fix|do) it\b" % VERBS, re.I)

VOICE = ("Reply style (owner rule): brief. ASD-STE100: max 20 words per sentence, active voice, "
         "one term per thing, imperative for instructions. When a step needs the owner (a login, "
         "an approval, a value only they have), give numbered step-by-step instructions.")
DISCUSS_RULE = ("DISCUSS mode (owner rule): the owner presented an idea, bug, problem or question "
                "and has not said go. Do not edit files, commit or push. Research, propose, name the "
                "trade-offs, weigh options, find alternatives, refine the wording. End by asking "
                "if we are ready, then wait for the owner's go. File edits are blocked until then.")


def is_go(text):
    text = text or ""
    if NEGATED.match(text):
        return False
    return bool(GO.match(text) or APPROVAL.match(text) or TRAILING_GO.search(text))


def is_order(text):
    return bool(ORDER.search(text or "")) and not NEGATED.match(text or "")


def classify(text, previous=False):
    """True for a discuss turn. `previous` is kept for callers; discussion is the default."""
    text = text or ""
    if NEGATED.match(text):
        return True
    if is_go(text):
        return False
    if is_order(text):
        return bool(STRONG.search(text))
    return True


def is_discuss(text):
    return classify(text)


def rules(text, cfg, previous=False):
    """The rule lines for this prompt, and whether it is a discuss turn."""
    lines, discuss = [], False
    if not (text or "").strip():
        return "", False
    if cfg.get("voice", True):
        lines.append(VOICE)
    if cfg.get("discuss_gate", "block") != "off" and classify(text, previous):
        lines.append(DISCUSS_RULE)
        discuss = True
    return " ".join(lines), discuss
