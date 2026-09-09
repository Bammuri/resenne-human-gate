"""Conservative detection of numbered answer menus in completed agent messages."""
import hashlib
import re


CHOICE = re.compile(r"^\s{0,3}(?:\*\*)?(\d{1,2})[.)](?:\*\*)?\s+(.+?)\s*$")
ANSWER_CUE = re.compile(
    r"선택\s*(?:해|하|할|해주|해주세요|하세요|해줘|하면)|골라|고르|어떻게\s*진행|"
    r"어느\s*(?:것|쪽|방식)|어떤\s*(?:방식|방법|선택)|번호.{0,24}(?:답|알려)|"
    r"\b(?:choose|select|pick)\b|\bwhich\b.{0,100}\?|\bhow\s+(?:would|should|shall)\b",
    re.IGNORECASE,
)


def parse_numbered_question(text, identity):
    """Return one complete, consecutive menu only when prose requests an answer.

    Fenced code and indented examples are ignored. Multiple menus are ambiguous
    and left to text input. Options are never truncated to the hardware count.
    """
    if not isinstance(text, str) or len(text) > 100000:
        return None
    text = re.sub(r"```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)", "", text)
    lines = text.splitlines()
    entries = [(i, CHOICE.match(line)) for i, line in enumerate(lines)]
    entries = [(i, match) for i, match in entries if match]
    if len(entries) < 2 or [int(m.group(1)) for _, m in entries] != list(range(1, len(entries) + 1)):
        return None
    first, last = entries[0][0], entries[-1][0]
    before = "\n".join(lines[max(0, first - 4):first]).strip()
    after = "\n".join(lines[last + 1:last + 5]).strip()
    if not ANSWER_CUE.search(before + "\n" + after):
        return None
    # An unrelated paragraph between list entries means these are not one menu.
    for (left, _), (right, _) in zip(entries, entries[1:]):
        if any(line.strip() and not line.startswith((" ", "\t")) for line in lines[left + 1:right]):
            return None
    prompt = before or after
    digest = hashlib.sha256((str(identity) + "\0" + text).encode()).hexdigest()[:24]
    return {"id": "prose-" + digest, "kind": "choice", "prompt": prompt,
            "options": [{"id": str(i + 1), "label": match.group(2).strip("*")}
                        for i, (_, match) in enumerate(entries)]}
