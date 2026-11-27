"""Owner working rules that apply to every prompt: reply voice and discuss-before-build."""
import re

# An explicit go: the owner approves building. Checked first, so "go ahead, fix the bug" builds.
GO = re.compile(r"\b(go|go ahead|do it|proceed|ship it|implement it|build it|approved|lgtm|"
                r"let'?s do it|yes,? (do|build|implement)|start building)\b", re.I)
# The owner is presenting something to think about, not ordering a change.
DISCUSS = re.compile(r"(\b(idea|ideas|bug|bugs|issue|issues|problem|problems|broken|what if|"
                     r"should we|could we|how about|maybe|i think|i prefer|improve|propose|"
                     r"proposal|research|consider|thoughts|trade-?offs?|alternatives?)\b|\?)", re.I)

VOICE = ("Reply style (owner rule): brief. ASD-STE100: max 20 words per sentence, active voice, "
         "one term per thing, imperative for instructions. When a step needs the owner (a login, "
         "an approval, a value only they have), give numbered step-by-step instructions.")
DISCUSS_RULE = ("DISCUSS mode (owner rule): this prompt presents an idea, bug or problem and gives "
                "no go signal. Do not edit files, commit or push. Research, propose, name the "
                "trade-offs, weigh options, find alternatives, refine the wording. End by asking "
                "if we are ready, then wait for the owner's go. File edits are blocked until then.")


def is_go(text):
    return bool(GO.search(text or ""))


def is_discuss(text):
    """True when the prompt presents something to discuss and carries no go signal."""
    text = text or ""
    return bool(DISCUSS.search(text)) and not is_go(text)


def rules(text, cfg):
    """The rule lines for this prompt, and whether it is a discuss turn."""
    lines, discuss = [], False
    if cfg.get("voice", True):
        lines.append(VOICE)
    if cfg.get("discuss_gate", "block") != "off" and is_discuss(text):
        lines.append(DISCUSS_RULE)
        discuss = True
    return " ".join(lines), discuss
