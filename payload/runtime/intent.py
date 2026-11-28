"""Owner working rules that apply to every prompt: reply voice and discuss-before-build.

The owner presents an idea, bug, problem or question: the agent researches, proposes,
weighs trade-offs and waits for "go". A regex cannot read intent reliably (three review
rounds measured 22-47% errors with a hard gate on every guess), so the verdict has three
values and only the confident one is enforced:
  discuss  clear idea/bug/question, or a refusal -> rule injected AND file edits blocked
  work     an approval or a clear order           -> no rule, no block
  unsure   anything else                          -> rule injected as a reminder, no block;
           the model applies the owner rule with its own judgement
"""
import re

NEGATED = re.compile(r"^\W*(not yet|not now|wait|hold on|hold off|nope|don'?t|do not|no\W*$|no,? not)", re.I)
BUT = re.compile(r"^\W*(yes|yep|yeah|ok(ay)?|sure|sounds good)\W+but\b", re.I)
GO = re.compile(r"^\W*((ok(ay)?|yes|yep|yeah|alright|sure|great|cool|good|perfect)\W+)?"
                r"(go(?!\s+(through|over|back|to|into|and|check|see|look)\b)|go ahead|go for it|"
                r"go with|do it|do that|proceed|ship it|implement it|build it|approved?|lgtm|"
                r"let'?s (go|do|build)|start building|yes,? (do|build|implement)|option \w+\W*(please)?\W*$)",
                re.I)
APPROVAL = re.compile(r"^\W*(yes|yep|yeah|y|sure|ok(ay)?|k|sounds good|looks good|perfect|great|"
                      r"agreed|approve[ds]?|lgtm|👍|✅)(\W+(please|thanks|thank you))?\W*$", re.I)
TRAILING_GO = re.compile(r"\b(proceed|go ahead|go for it|do it|ship it|build it)\W*$", re.I)
STRONG = re.compile(r"\b(ideas?|what if|should we|could we|how about|thoughts|propose|"
                    r"trade-?offs?|alternatives?|research|i prefer|i think|maybe we|consider|"
                    r"brainstorm|opinions?|pros and cons|what do you think|i don'?t like|compare)\b", re.I)
REPORT = re.compile(r"\b(is|are|was|were|shows|throws|crash(es|ing)?|fails?|failing|failed|"
                    r"broken|misaligned|overlaps?|not (working|arriving|loading|showing|saving)|"
                    r"does nothing|doesn'?t|off by|slow|twice|wrong|bugs?|errors?|cramped|too (big|small))\b", re.I)
VERBS = (r"add|fix|rename|update|remove|delete|create|implement|build|change|make|write|run|"
         r"ensure|set|move|refactor|improve|replace|bump|merge|commit|push|install|deploy|"
         r"migrate|revert|test|document|wire|hook|port|convert|split|extract|start|stop|open|"
         r"close|publish|release|upgrade|enable|disable|apply|clean|restore|use|redesign|polish|keep|"
         r"align|reduce|increase|center|resize|hide|show|tighten|simplify")
ORDER = re.compile(r"^\W*((please|pls|can you|could you|now|also|then|and)\W+)*(%s)\b" % VERBS, re.I)
ASKED = re.compile(r"\b(you have to|you need to|i want you to|we need to|please)\s+(\w+\s+)?(%s)\b|"
                   r"\b(fix|do) it\b" % VERBS, re.I)
# Verbs that also read as nouns ("Test failing on CI", "Close button is misaligned"):
# only these yield to a report. "Fix the footer, it overlaps" stays an order.
AMBIGUOUS = re.compile(r"^\W*(test|update|push|open|close|use|start|stop|show|set|run|release|"
                       r"add|delete|remove|save|search|share|"
                       r"hook|port|split|clean|build|merge|install|wire|move|change)\b", re.I)
DIRECT = re.compile(r"^\W*(implement|build|apply|ship)\b", re.I)   # "implement the proposal" is a go

VOICE = ("Reply style (owner rule): brief. ASD-STE100: max 20 words per sentence, active voice, "
         "one term per thing, imperative for instructions. When a step needs the owner (a login, "
         "an approval, a value only they have), give numbered step-by-step instructions.")
DISCUSS_RULE = ("DISCUSS mode (owner rule): the owner presented an idea, bug, problem or question "
                "and has not said go. Do not edit files, commit or push. Research, propose, name the "
                "trade-offs, weigh options, find alternatives, refine the wording. End by asking "
                "if we are ready, then wait for the owner's go. File edits are blocked until then.")


def is_go(text):
    text = text or ""
    if NEGATED.match(text) or BUT.match(text):
        return False
    return bool(GO.match(text) or APPROVAL.match(text) or TRAILING_GO.search(text))


def mode(text):
    """"discuss", "work" or "unsure" for one prompt (see the module docstring)."""
    text = (text or "").strip()
    if not text:
        return "work"
    if NEGATED.match(text) or BUT.match(text):
        return "discuss"
    if is_go(text) or DIRECT.match(text):
        return "work"
    if ORDER.match(text):
        if STRONG.search(text):
            return "discuss"
        # "Close button is misaligned": a noun that looks like a verb, then a report
        report = AMBIGUOUS.match(text) and REPORT.search(text) and not ASKED.search(text)
        return "discuss" if report else "work"
    if ASKED.search(text):
        return "discuss" if STRONG.search(text) else "work"
    if STRONG.search(text) or text.endswith("?") or REPORT.search(text):
        return "discuss"
    return "unsure"


def classify(text, previous=False):
    """True when edits must be blocked (a confident discuss turn)."""
    return mode(text) == "discuss"


def is_discuss(text):
    return classify(text)


UNSURE_RULE = ("Owner rule: if this prompt presents an idea, bug, problem or question rather than "
               "an order, discuss first: research, propose, name trade-offs, then ask if we are "
               "ready and wait for go. Build only on a clear order or a go.")


def rules(text, cfg, previous=False):
    """The rule lines for this prompt, and whether file edits are blocked."""
    lines, discuss = [], False
    if not (text or "").strip():
        return "", False
    if cfg.get("voice", True):
        lines.append(VOICE)
    if cfg.get("discuss_gate", "block") != "off":
        m = mode(text)
        if m == "discuss":
            lines.append(DISCUSS_RULE)
            discuss = True
        elif m == "unsure":
            lines.append(UNSURE_RULE)
    return " ".join(lines), discuss
