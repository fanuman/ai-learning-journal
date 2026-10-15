# Day 40 - Normalization: many spellings, one canonical code

Status: done. Concept + toy example (Part 1), then the repo changes in four files (Part 2) and the first real results.

## The problem this solves
Our generator makes each invoice use a different spelling than its quote on purpose: the quote says `Ocean Freight`, the invoice says `O/F`.
A person sees the same charge. Software comparing text sees two different charges and would report one "missing" and one "unquoted" charge, both false.
Normalization maps every spelling to one agreed code (`OCEAN_FREIGHT`) so Day 41's reconciliation compares codes, not spellings.

## Concepts

**Canonical code.** One agreed name for a thing (`OCEAN_FREIGHT`, `BAF`, `THC_ORIGIN`, ...). The raw label is always kept next to it, never thrown away (audit trail).

**Reference data.** The table saying which spellings mean which code. It is data, not logic: supporting a new carrier's wording means adding a line, not changing code.

**Alias.** One known spelling of a code. `o/f`, `sea freight` and `ocean freight` are all aliases of `OCEAN_FREIGHT`.

**Cleaning.** Removing differences that carry no meaning before looking anything up (capitals, extra spaces): `" ".join(text.lower().split())`.
`split()` with no argument splits on any run of whitespace; `join` glues the pieces back with single spaces.

**Exact lookup.** Flip the table once into `{spelling: code}` so a lookup is instant. A spelling is either known or not.

**Fuzzy matching.** Pick the most similar known spelling by a similarity score (`difflib`). Feels smarter because it handles spellings never seen before. It is the dangerous option for money (see experiments).

**Flagging.** An unknown label becomes `OTHER` and is marked for a human. It is never dropped and never guessed. The charge keeps its amount and raw label.

**Precision over recall.** For money lines, a wrong code is worse than an honest "I don't know". We accept a higher flagged rate to keep silent errors at zero.

## Failure modes compared
| | wrong and flagged | wrong and NOT flagged |
|---|---|---|
| meaning | a human looks at it | nobody ever looks |
| worst case | wasted review time | an overcharge filed under a quoted charge and lost |
| exact lookup | possible, safe | cannot happen for unseen spellings |
| fuzzy matching | rare | happens (see below) |

The metric that matters is **confident wrong**: wrong code AND not flagged. The target is 0.

## The experiments and what they showed
Toy test: 7 labels (messy known spellings, one genuinely new spelling, three charges with no canonical code).

| Method | confident wrong | note |
|---|---|---|
| exact lookup | 0 | flags `Terminal Handling Charge Origin` (new spelling) as OTHER: safe, a human adds the alias |
| fuzzy, cutoff 0.6 | 3 | Peak Season, Low Sulphur -> ISPS, Emergency Risk -> CAF (the word "Surcharge" looks similar) |
| fuzzy, cutoff 0.7 | 1 | Emergency Risk still -> CAF |
| fuzzy, cutoff 0.8 | 0 | looks perfect, but see the next paragraph |

Why "0 at 0.8" is not a win: we picked 0.8 by looking at the answers on 7 labels (the same trap as tuning a prompt on the same 90 documents).
Nothing in freight says 0.8 is right, and at 0.9 even the correct new spelling is flagged, so fuzzy becomes exactly what exact lookup already is.
Exact lookup fails safely (a flag today); fuzzy fails silently (a wrong code at some unpredictable point later).

Decision: exact lookup after cleaning, flag everything unknown. Fuzzy matching may come back later only as a *suggestion* a human approves, never as an automatic decision. An LLM guessing the code would repeat the fuzzy problem, with a model making a money decision.

## Reading the toy's counting line
`wrong["exact"] += ec != truth and not ef`
- `ec` = exact method's code, `ef` = its flag (True = flagged), `truth` = right answer.
- `ec != truth` is "the code is wrong"; `not ef` is "nobody was warned". `and` makes it True only when both hold.
- `True` counts as 1 and `False` as 0, so `+=` counts the case. Same as `if ec != truth and not ef: wrong["exact"] += 1`.
- Careful: the toy returns `(code, flagged)`; the repo's `normalize_charge` returns `(code, known)`. The boolean is inverted on purpose in each (toy: True = a human must look; repo: True = recognised).

## Ports and container types
Same pattern: clean, exact lookup, unknown is flagged. `Jebel Ali`, `Jebel Ali (AEJEA)` and `AEJEA` all -> `AEJEA` (UN/LOCODE); `40' High Cube`, `40HQ`, `1 x 40HC` -> `40HC`. A charge needs an `OTHER` bucket because the line still carries money; an unrecognised port has no useful bucket, so we return `None` and flag it.

## Self-check (answer key)
1. **Why compare canonical codes instead of raw labels?** Different documents spell the same charge differently; comparing text would invent "missing" and "unquoted" charges that do not exist.
2. **Why `OTHER` + flag instead of a best guess?** A wrong code on a money line is filed silently under a different charge. A flag costs a human a few seconds; a silent wrong code can hide an overcharge.
3. **Wrong-and-flagged vs wrong-and-not-flagged?** The first gets looked at; the second never does. The second is worse, and it is the one we count as "confident wrong".
4. **Why does `build_lookup` raise an error when a spelling is listed under two codes?** Otherwise the last entry would silently win: another wrong-and-not-flagged failure.
5. **Why does the eval only check the code on charges the model read correctly?** So extraction errors and normalization errors stay separate; a misread charge is already penalised by charge F1.

## The toy example (standalone, not part of the repo)
Run it with `python normalize_demo.py`. Try: cutoff 0.8 / 0.9; add `"terminal handling charge origin"` to the THC_ORIGIN aliases (exact lookup then handles it: this is how the system improves); remove `.lower()` from `clean` and see which messy labels break.

```python
"""Day 40 toy: turning many spellings of a charge into one canonical code.
Standalone (standard library only). NOT part of the repo; run it from anywhere.
"""
import difflib

# 1. Reference data: canonical code -> the spellings we have actually seen in documents.
ALIASES = {
    "OCEAN_FREIGHT": ["ocean freight", "basic ocean freight", "o/f", "sea freight"],
    "BAF": ["baf", "bunker adjustment factor", "fuel surcharge", "bunker surcharge"],
    "THC_ORIGIN": ["thc origin", "origin terminal handling", "othc", "terminal handling - origin"],
    "THC_DEST": ["thc destination", "destination terminal handling", "dthc", "terminal handling - dest"],
    "DOC_FEE": ["documentation fee", "b/l fee", "bill of lading fee", "document charge"],
    "ISPS": ["isps", "port security surcharge", "isps security fee", "security surcharge"],
    "CAF": ["caf", "currency adjustment factor", "currency surcharge", "fx adjustment"],
    "INLAND": ["inland haulage", "trucking", "inland transport", "haulage"],
    "DETENTION": ["container detention"],
    "DEMURRAGE": ["demurrage charges"],
}
# Flip it once into a dictionary that answers "which code is this spelling?" instantly.
LOOKUP = {alias: code for code, aliases in ALIASES.items() for alias in aliases}


def clean(label: str) -> str:
    """Remove differences that do not matter: capital letters and extra spaces."""
    return " ".join(label.lower().split())


# 2. Method A: exact lookup. A spelling is known or it is not.
def normalize_exact(label: str) -> tuple[str, bool]:
    code = LOOKUP.get(clean(label))
    return (code, False) if code else ("OTHER", True)  # True = flag for a human


# 3. Method B: fuzzy matching. Pick the most similar known spelling.
def normalize_fuzzy(label: str, cutoff: float = 0.6) -> tuple[str, bool]:
    best_alias = max(LOOKUP, key=lambda a: difflib.SequenceMatcher(None, clean(label), a).ratio())
    score = difflib.SequenceMatcher(None, clean(label), best_alias).ratio()
    return (LOOKUP[best_alias], False) if score >= cutoff else ("OTHER", True)


# 4. Test labels with the right answer. Some are messy versions of known spellings,
#    some are genuinely new (never seen), some are charges that have NO canonical code.
TESTS = [
    ("OCEAN FREIGHT ", "OCEAN_FREIGHT"),            # messy: capitals and trailing space
    ("Terminal  Handling - Origin", "THC_ORIGIN"),   # messy: double space
    ("Fuel Surcharge", "BAF"),                       # known synonym
    ("Terminal Handling Charge Origin", "THC_ORIGIN"),  # NEW spelling, same meaning
    ("Peak Season Surcharge", "OTHER"),              # a real charge with no canonical code
    ("Low Sulphur Surcharge", "OTHER"),
    ("Emergency Risk Surcharge", "OTHER"),
]

if __name__ == "__main__":
    print(f"{'label':<34}{'right answer':<15}{'exact lookup':<22}{'fuzzy matching'}")
    wrong = {"exact": 0, "fuzzy": 0}
    for label, truth in TESTS:
        (ec, ef), (fc, ff) = normalize_exact(label), normalize_fuzzy(label)
        e_txt = f"{ec}{' (flagged)' if ef else ''}"
        f_txt = f"{fc}{' (flagged)' if ff else ''}"
        wrong["exact"] += ec != truth and not ef  # a wrong answer that nobody is warned about
        wrong["fuzzy"] += fc != truth and not ff
        print(f"{label!r:<34}{truth:<15}{e_txt:<22}{f_txt}" + ("   <-- WRONG, not flagged" if fc != truth and not ff else ""))
    print(f"\nconfident wrong answers: exact = {wrong['exact']}, fuzzy = {wrong['fuzzy']}")
```

## Part 2 - The real thing in the repo

### What changed and why
| File | Change | Why |
|---|---|---|
| `pipeline/normalize.py` (new) | alias tables for charges / ports / container types, `clean`, `build_lookup`, `normalize_charge/port/equipment` | the canonical-code logic in one place, as data + a tiny lookup |
| `pipeline/validation.py` | `TypedCharge` gets `code` and `known`; `TypedDocument` gets `origin`, `destination`, `equipment`; new warnings `UNKNOWN_CHARGE`, `UNKNOWN_PORT`, `UNKNOWN_EQUIPMENT` | turning a label into a code is the same kind of conversion `validate()` already does (text -> typed values); no new graph node needed |
| `evaluation/metrics.py`, `runner.py` | origin/destination/equipment join field accuracy; new `normalization` block: code accuracy, confident wrong, flagged, alias gaps | measure normalization separately from extraction |
| tests | `test_validation.py` updated (+1 test), `test_eval.py` updated (+1 test) | prove unknown labels are flagged not guessed, and that the metric catches "confident wrong" |

Design decisions:
- **Warnings, not errors.** An unknown label is a flag for a person, not proof the document is wrong. An unquoted surcharge is a business finding that Day 41 reconciliation will turn into a discrepancy; changing what "needs_review" means belongs to Day 42.
- **Safe defaults.** `TypedCharge(code="OTHER", known=False)`: a charge nobody normalised counts as unknown.
- **Ambiguity guard.** A spelling claimed by two codes stops the program at start-up with a clear error instead of letting the last entry win.
- **No fuzzy, no LLM** in the mapping.

### The repo's normalize.py
```python
"""Turn the many spellings found in documents into one canonical code each.

Charges, ports and container types all work the same way:
  1. clean the text (lowercase, collapse spaces) so trivial differences vanish
  2. look it up EXACTLY in a table of known spellings
  3. if the spelling is unknown, say so (never guess): the caller flags it for a human

No fuzzy matching and no LLM on purpose: a wrong code on a money line is worse
than an honest "I don't know this one".
"""

# --- reference data: canonical code -> spellings we have seen --------------------
# This is data, not logic. Supporting a new carrier's wording means adding a line here.

CHARGE_ALIASES: dict[str, tuple[str, ...]] = {
    "OCEAN_FREIGHT": ("Ocean Freight", "Basic Ocean Freight", "O/F", "Sea Freight"),
    "BAF": ("BAF", "Bunker Adjustment Factor", "Fuel Surcharge", "Bunker Surcharge"),
    "THC_ORIGIN": ("THC Origin", "Origin Terminal Handling", "OTHC", "Terminal Handling - Origin"),
    "THC_DEST": ("THC Destination", "Destination Terminal Handling", "DTHC", "Terminal Handling - Dest"),
    "DOC_FEE": ("Documentation Fee", "B/L Fee", "Bill of Lading Fee", "Document Charge"),
    "ISPS": ("ISPS", "Port Security Surcharge", "ISPS Security Fee", "Security Surcharge"),
    "CAF": ("CAF", "Currency Adjustment Factor", "Currency Surcharge", "FX Adjustment"),
    "INLAND": ("Inland Haulage", "Trucking", "Inland Transport", "Haulage"),
    "DETENTION": ("Container Detention", "Detention"),
    "DEMURRAGE": ("Demurrage Charges", "Demurrage"),
}

# UN/LOCODE -> the name people print. A real system would load the full UN/LOCODE list.
PORT_NAMES: dict[str, str] = {
    "PKKHI": "Karachi", "CNSHA": "Shanghai", "AEJEA": "Jebel Ali", "DEHAM": "Hamburg",
    "NLRTM": "Rotterdam", "USNYC": "New York", "SGSIN": "Singapore", "GBFXT": "Felixstowe",
}
PORT_ALIASES: dict[str, tuple[str, ...]] = {
    code: (name, f"{name} ({code})") for code, name in PORT_NAMES.items()
}

EQUIPMENT_ALIASES: dict[str, tuple[str, ...]] = {
    "20GP": ("20GP", "20' Dry", "20DC", "1 x 20GP"),
    "40GP": ("40GP", "40' Dry", "40DC", "1 x 40GP"),
    "40HC": ("40HC", "40' High Cube", "40HQ", "1 x 40HC"),
}


# --- machinery -------------------------------------------------------------------

def clean(text: str) -> str:
    """'  Terminal  Handling - ORIGIN ' -> 'terminal handling - origin'."""
    return " ".join(text.lower().split())


def build_lookup(aliases: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """Flip {code: spellings} into {cleaned spelling: code} for instant exact lookup.

    The code itself counts as a spelling. If one spelling is claimed by two
    different codes the table is ambiguous, so we refuse to start (loudly, once)
    rather than silently let the last entry win.
    """
    lookup: dict[str, str] = {}
    for code, spellings in aliases.items():
        for spelling in (code, *spellings):
            key = clean(spelling)
            if lookup.get(key, code) != code:
                raise ValueError(f"{spelling!r} is listed under both {lookup[key]} and {code}")
            lookup[key] = code
    return lookup


_CHARGES = build_lookup(CHARGE_ALIASES)
_PORTS = build_lookup(PORT_ALIASES)
_EQUIPMENT = build_lookup(EQUIPMENT_ALIASES)


def normalize_charge(label: str) -> tuple[str, bool]:
    """Return (code, known). An unknown label becomes ('OTHER', False): the charge
    keeps its amount and raw label, but a human must look at it."""
    code = _CHARGES.get(clean(label))
    return (code, True) if code else ("OTHER", False)


def normalize_port(text: str | None) -> str | None:
    """Port text -> UN/LOCODE, or None if missing or not in our table."""
    return _PORTS.get(clean(text)) if text else None


def normalize_equipment(text: str | None) -> str | None:
    """Container text -> '20GP' / '40GP' / '40HC', or None if missing or unknown."""
    return _EQUIPMENT.get(clean(text)) if text else None
```

### Results
Oracle (perfect pretend model) and real gpt-4o-mini, 90 documents:

| Metric | Result |
|---|---|
| Charge-code accuracy | 100.0% |
| Confident wrong | 0 |
| Flagged | 3 / 564 (the three real surcharges with no taxonomy entry) |
| Alias gaps | 0 |
| Field accuracy (now incl. origin, destination, equipment) | 100.0% |
| Charge F1 | 100.0% |
| Cost | about $0.033, 190 calls |

Checked offline too: all 564 charge lines, and every port and container spelling the generator prints, map correctly.

### Honest caveats
- The alias table was written knowing the generator's spellings, so "100%" mostly shows the wiring is correct. It does NOT show the table covers real carriers' wording.
- The number to watch on real documents is **alias gaps** (and the flagged rate): each gap is a spelling a human adds to `normalize.py`. Confident wrong must stay 0.
- gpt-4o-mini copies labels faithfully; a model that "tidies" labels would show up as extraction errors (charge F1), not here.
- Synthetic data, one run, output not perfectly repeatable.

### Lessons
- Exact + flag beats fuzzy for money: the failure that matters is the silent one.
- Reference data grows by human-approved additions, which makes "unknown" a feature, not a bug.
- Pick thresholds on held-out data, never by looking at the answers you are scoring.
- File writes from the sandbox to the Mac can lag by a few seconds; verify a file landed (size) before running tests.

### Next (Day 41)
Persist documents to Postgres under row-level security, then reconcile quote vs invoice by canonical code: discrepancy types (missing charge, unquoted charge, amount changed, currency mismatch, expired quote) computed by deterministic code; the LLM only explains the computed result.