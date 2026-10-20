"""
Small, dependency-free Unicode text helpers shared by question de-duplication and evidence checks.

A "word" is a run of letters/digits plus combining marks (so Indic scripts such as Telugu and
Devanagari are not split at vowel signs). Scripts written without spaces (CJK, Thai, ...) are
split into overlapping character bigrams so near-duplicates can still be compared.
"""
import unicodedata
from typing import List, Sequence

_SPACELESS_NAME_PREFIXES = ("CJK", "HIRAGANA", "KATAKANA", "THAI", "LAO", "KHMER", "MYANMAR", "TIBETAN")

QUESTION_MARKS = ("?", "？", "؟")  # Latin, fullwidth, Arabic


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or unicodedata.category(ch).startswith("M")


def _is_spaceless_script(ch: str) -> bool:
    try:
        return unicodedata.name(ch).startswith(_SPACELESS_NAME_PREFIXES)
    except ValueError:
        return False


def tokenize(text: str) -> List[str]:
    """Case-folded word tokens, in order. Spaceless scripts become overlapping bigrams."""
    text = unicodedata.normalize("NFC", text or "").casefold()
    words: List[str] = []
    buf: List[str] = []
    for ch in text:
        if _is_word_char(ch):
            buf.append(ch)
        elif buf:
            words.append("".join(buf))
            buf = []
    if buf:
        words.append("".join(buf))

    tokens: List[str] = []
    for word in words:
        if any(_is_spaceless_script(c) for c in word) and len(word) > 1:
            tokens.extend(word[i:i + 2] for i in range(len(word) - 1))
        else:
            tokens.append(word)
    return tokens


def jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def contains_sequence(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    """True if `needle` appears as a contiguous run of whole tokens inside `haystack`."""
    n = len(needle)
    if n == 0 or n > len(haystack):
        return False
    first = needle[0]
    for i in range(len(haystack) - n + 1):
        if haystack[i] == first and list(haystack[i:i + n]) == list(needle):
            return True
    return False
