"""Incremental redaction for streamed model text.

No filter recognizes every possible secret. Known saved gateway keys and the
common sk-/Bearer patterns are treated as secrets, including across chunks.
"""
import re

PATTERN = re.compile(r'(?i)\b(sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._-]{12,})')
# Any suffix that could grow into a token is held until its delimiter arrives.
POSSIBLE_TOKEN = re.compile(
    r'(?i)(?<![A-Za-z0-9_])(?:s(?:k(?:-[A-Za-z0-9_-]*)?)?|'
    r'b(?:e(?:a(?:r(?:e(?:r(?:\s+[A-Za-z0-9._-]*)?)?)?)?)?)?)$'
)


def redact_text(text: str, secrets: list[str]) -> str:
    # Merge overlapping matches before replacing, so replacing one secret
    # cannot expose part of a second secret that overlaps it.
    spans = [(m.start(), m.end()) for m in PATTERN.finditer(text)]
    for secret in set(filter(None, secrets)):
        start = text.find(secret)
        while start != -1:
            spans.append((start, start + len(secret)))
            start = text.find(secret, start + 1)
    if not spans:
        return text
    spans.sort()
    merged = [spans[0]]
    for start, end in spans[1:]:
        old_start, old_end = merged[-1]
        if start <= old_end:
            merged[-1] = (old_start, max(end, old_end))
        else:
            merged.append((start, end))
    result = []
    previous = 0
    for start, end in merged:
        result.extend((text[previous:start], '[redacted]'))
        previous = end
    result.append(text[previous:])
    return ''.join(result)


class SlidingRedactor:
    def __init__(self, secrets: list[str]):
        self.secrets = sorted(set(filter(None, secrets)), key=len, reverse=True)
        self.pending = ''
        # Hold enough raw characters to catch a known key that crosses chunks.
        self.lookbehind = max([12, *(len(s) - 1 for s in self.secrets)])

    def feed(self, chunk: str) -> str:
        self.pending += chunk
        # Refuse unbounded ambiguous input rather than leaking it or exhausting memory.
        if len(self.pending) > 131072:
            raise ValueError('Response contains an excessively long ambiguous token')
        cut = max(0, len(self.pending) - self.lookbehind)
        token = POSSIBLE_TOKEN.search(self.pending)
        if token:
            cut = min(cut, token.start())
        # Cuts can overlap multiple secrets. Recheck until the cut no longer
        # moves, or moving it for one match could split an earlier match.
        while True:
            previous = cut
            for match in PATTERN.finditer(self.pending):
                if match.start() < cut < match.end():
                    cut = match.start()
            for secret in self.secrets:
                start = self.pending.find(secret)
                while start != -1:
                    if start < cut < start + len(secret):
                        cut = start
                    start = self.pending.find(secret, start + 1)
            if cut == previous:
                break
        safe, self.pending = self.pending[:cut], self.pending[cut:]
        return redact_text(safe, self.secrets)

    def finish(self) -> str:
        result = redact_text(self.pending, self.secrets)
        self.pending = ''
        return result
