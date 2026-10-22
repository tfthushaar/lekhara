"""Looking for a few words in a text, the ways a person writing a rule means them.

Filing rules look in a document's text, bank rules in a statement line's narration. Of
Paperless-ngx's ways to match, four are kept:

- any:    any one of the words appears;
- all:    every word appears, in any order;
- phrase: the words appear together, in that order;
- fuzzy:  every word appears, allowing a letter or two wrong (useful for scanned text).

Patterns (regular expressions) are left out on purpose: one written carelessly can take a
server minutes to run over a long text.
"""

import difflib
import re

HOW = {
    "any": "Any of the words",
    "all": "All of the words",
    "phrase": "The exact phrase",
    "fuzzy": "All of the words, allowing small spelling differences",
}


def normal(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.casefold())).strip()


def position(how: str, words: str, text: str) -> int | None:
    """Where in the text (already normalised) the words are found the given way, or None."""
    wanted = normal(words).split()
    if not wanted:
        return None
    padded = f" {text} "

    def at(word: str) -> int:
        return padded.find(f" {word} ")

    if how == "phrase":
        found = at(" ".join(wanted))
        return found if found >= 0 else None
    places = [at(w) for w in wanted]
    if how == "any":
        hits = [p for p in places if p >= 0]
        return min(hits) if hits else None
    if how == "all":
        return min(places) if all(p >= 0 for p in places) else None
    if how == "fuzzy":
        tokens = text.split()
        starts, found = [], []
        offset = 0
        for token in tokens:
            starts.append(offset)
            offset += len(token) + 1
        for w in wanted:
            close = difflib.get_close_matches(w, set(tokens), n=1, cutoff=0.8)
            if not close:
                return None
            found.append(starts[tokens.index(close[0])])
        return min(found)
    return None


def matches(how: str, words: str, text: str) -> bool:
    return position(how, words, text) is not None
