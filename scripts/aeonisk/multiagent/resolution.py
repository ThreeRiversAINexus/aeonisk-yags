"""One resolver for "the model named something — which thing did it mean?" (#134).

Nine independently-written matchers grew across this codebase, with at least
four different policies, three of them bidirectional substring containment. That
last shape is how a player asking for a stun weapon receives a lethal one:
`'the stun pistol'` contains `'pistol'`, so a Pistol (WOUND) answers a
non-lethal request, and the matcher reports success.

The policy here, in order:

  1. **exact**, casefolded
  2. **normalized** — articles, punctuation and trailing annotations removed.
     `"Stun Baton (STUN)"` is what a model actually writes, and `(STUN)` is an
     annotation this codebase itself prints (`player.py:_format_weapon_inventory`),
     not part of any name.
  3. **token subset, directional** — every declared token must match a token of
     the candidate, never the reverse. `{tranquilizer} ⊆ {tranquilizer, gun}` is
     the paraphrase models actually write; `{the, stun, pistol} ⊄ {pistol}` is
     the lethality upgrade, and refusing it is the whole point.
  4. **invariant** — a domain property the match must preserve however it was
     reached. For weapons that is `damage_type`: a match may never cross
     lethality class.
  5. **ambiguity → refuse** — exactly one surviving candidate, or nothing. This
     is `name_matching.py`'s rule, the only one of the nine that had it.

Generous on the name, absolute on the invariant. The old matcher had it
backwards on both axes: it accepted `'the stun pistol'` while refusing `'the
tranquilizer'`, the example in its own docstring.

Edit-distance fuzzing (`Tranquiliser`/`Tranquilizer`) is deliberately absent. It
is the one step that cannot be made conservative, and a reprompt handles it
better than a guess. Prefix matching covers the common abbreviation (`tranq
gun`) without that risk, because a prefix is directional too.

`Resolution.path` is returned rather than logged here so callers can record it.
That field is what makes close-enough matching auditable: any analysis can
restrict to `path == "exact"` and check whether a finding survives without the
inferred ones. Fuzzy resolution does not have to be trusted; it has to be
subtractable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence

# Articles and possessives a model writes around a name but never inside one.
_ARTICLES = frozenset({
    "the", "a", "an", "my", "our", "your", "their", "his", "her", "its",
})

# A trailing "(STUN)" / "(WOUND damage)" annotation, which this codebase prints
# into the prompt itself, so models echo it back.
_PARENTHETICAL = re.compile(r"\([^)]*\)")
_PUNCTUATION = re.compile(r"[^\w\s]")

#: Shortest declared token allowed to match by prefix. "tranq" -> "tranquilizer"
#: is worth having; three characters would let "gun" reach anything gun-shaped.
MIN_PREFIX = 4

EXACT = "exact"
NORMALIZED = "normalized"
TOKEN_SUBSET = "token_subset"
REFUSED = "refused"


@dataclass(frozen=True)
class Resolution:
    """What the resolver decided, and how it got there."""
    value: Optional[Any]
    path: str
    reason: Optional[str] = None
    considered: int = 0

    @property
    def matched(self) -> bool:
        return self.value is not None

    @property
    def is_exact(self) -> bool:
        return self.path == EXACT


@dataclass(frozen=True)
class Policy:
    """How one domain resolves names.

    `name_of` extracts the comparable string from a candidate. `invariant`, when
    given, receives `(declared, candidate)` and returns False to refuse a match
    that would cross a property the domain considers load-bearing.
    """
    name_of: Callable[[Any], Optional[str]]
    invariant: Optional[Callable[[str, Any], bool]] = None
    min_prefix: int = MIN_PREFIX


def normalize(text: str) -> str:
    """Casefold, drop annotations and punctuation, drop articles."""
    text = _PARENTHETICAL.sub(" ", text or "")
    text = _PUNCTUATION.sub(" ", text).lower()
    return " ".join(w for w in text.split() if w not in _ARTICLES)


def _tokens(text: str) -> List[str]:
    return normalize(text).split()


def _token_matches(declared: str, candidate: str, min_prefix: int) -> bool:
    """One declared token against one candidate token, directionally.

    Equality, or the declared token being a prefix of the candidate's — never
    the reverse, which is what lets a shorter, different name answer a longer,
    more specific request.
    """
    if declared == candidate:
        return True
    return (len(declared) >= min_prefix
            and len(declared) < len(candidate)
            and candidate.startswith(declared))


def _is_subset(declared: Sequence[str], candidate: Sequence[str],
               min_prefix: int) -> bool:
    return all(
        any(_token_matches(d, c, min_prefix) for c in candidate)
        for d in declared
    )


def resolve(declared: str, candidates: Sequence[Any], policy: Policy) -> Resolution:
    """Resolve a declared name against the candidates the actor actually has.

    Candidates are the *owned* set, never a library: naming a thing must not
    confer its properties.
    """
    considered = len(candidates or ())
    if not declared or not declared.strip():
        return Resolution(None, REFUSED, "empty declaration", considered)
    if not candidates:
        return Resolution(None, REFUSED, "no candidates", considered)

    named = [(c, policy.name_of(c)) for c in candidates]
    named = [(c, n) for c, n in named if n]

    def _guarded(candidate: Any, path: str) -> Resolution:
        if policy.invariant and not policy.invariant(declared, candidate):
            return Resolution(
                None, REFUSED,
                f"match {policy.name_of(candidate)!r} violates the domain "
                f"invariant for {declared!r}", considered)
        return Resolution(candidate, path, None, considered)

    needle = declared.strip().lower()
    for candidate, name in named:
        if name.lower() == needle:
            return _guarded(candidate, EXACT)

    norm = normalize(declared)
    for candidate, name in named:
        if normalize(name) == norm and norm:
            return _guarded(candidate, NORMALIZED)

    declared_tokens = _tokens(declared)
    if not declared_tokens:
        return Resolution(None, REFUSED, "declaration normalized to nothing",
                          considered)

    hits = [c for c, name in named
            if _is_subset(declared_tokens, _tokens(name), policy.min_prefix)]

    if len(hits) == 1:
        return _guarded(hits[0], TOKEN_SUBSET)
    if len(hits) > 1:
        names = ", ".join(sorted(repr(policy.name_of(h)) for h in hits))
        return Resolution(None, REFUSED,
                          f"{declared!r} is ambiguous between {names}",
                          considered)
    return Resolution(None, REFUSED,
                      f"{declared!r} matches nothing held", considered)


# ---------------------------------------------------------------------------
# Weapons — the first domain migrated (#131, #133)
# ---------------------------------------------------------------------------
def declared_damage_class(declared: str) -> Optional[str]:
    """The lethality class a declaration commits to, or None if it states none.

    Two sources, both structured rather than inferred from prose:

      * the declaration names a library weapon, whose `damage_type` is known;
      * it carries the `(STUN)` / `(WOUND)` annotation that
        `_format_weapon_inventory` prints into the prompt, so models echo it.

    Deliberately not a keyword scan of free text — bare-word matching over
    narration is exactly what this codebase forbids.
    """
    from .weapons import WEAPON_LIBRARY

    if not declared:
        return None

    norm = normalize(declared)
    for weapon in WEAPON_LIBRARY.values():
        name = getattr(weapon, "name", "")
        if name and normalize(name) == norm:
            return getattr(weapon, "damage_type", None)

    for annotation in _PARENTHETICAL.findall(declared):
        token = annotation.strip("()").strip().lower().split()
        if token and token[0] in ("stun", "wound", "mixed"):
            return token[0]
    return None


def _weapon_invariant(declared: str, candidate: Any) -> bool:
    """A match may never change the lethality class that was asked for."""
    wanted = declared_damage_class(declared)
    if wanted is None:
        return True
    return getattr(candidate, "damage_type", None) == wanted


WEAPON_POLICY = Policy(
    name_of=lambda w: getattr(w, "name", None),
    invariant=_weapon_invariant,
)
