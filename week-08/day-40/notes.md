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

# Day 41 - Reconciliation and persistence: compare quote vs invoice, then store it safely

Status: done. Part 1 = reconciliation logic (pure functions). Part 2 = persistence (tables, migration, repositories, service, DB tests). All tests pass.

## The problem this solves
Day 40 gave every charge a canonical code. Day 41 answers the business question: **did the carrier invoice what it quoted?**
The rule stays "the LLM reads, software decides": the model copied fields off the documents, and now plain deterministic code finds the discrepancies. No model call is involved on Day 41. Then we store the results so they survive a restart, can be queried, and can be audited.

# Part 1 - Reconciliation logic (`pipeline/reconcile.py`)

## Concepts

**Reconciliation.** Comparing two records that should agree (here: a quote and the invoice for it) and listing every difference.

**Matching (which quote does this invoice belong to?).** Done before comparing. Order of trust:
1. The invoice cites a quote reference -> use exactly that quote. If the cited quote is not in the system, the answer is `reference_not_found`. We never fall back to a guess, because a citation that points nowhere is itself a finding.
2. No reference -> same route and equipment, quote issued on or before the invoice date. Exactly one candidate -> use it. Zero -> `no_candidate`. Several -> `ambiguous` and a human decides. Quote validity is not a matching condition: an expired quote is still the quote the invoice belongs to, and "expired" is reported as a finding instead.

**Tolerance.** Amounts rarely match to the cent after currency rounding, so a small difference is forgiven: `max(1 cent, 0.5% of the quoted amount)`. 0.5% is written as 50 *basis points* (1 bp = 0.01%) so the maths stays in integers: `quoted * 50 // 10_000`. Money is never a float.

**Minor units.** Money is an integer count of cents (`300_000` = 3,000.00). Integers add and compare exactly; floats do not (`0.1 + 0.2 != 0.3`).

**Comparing by canonical code.** Charges are matched by code, not by label (that is what Day 40 was for). The code `OTHER` is a bucket, not an identity: two different unknown surcharges must not merge into one, so for `OTHER` the cleaned raw label is the key.

## The discrepancy types
| Type | Meaning |
|---|---|
| `OVERCHARGE` | invoiced more than quoted, beyond tolerance |
| `UNDERCHARGE` | invoiced less than quoted, beyond tolerance (my addition: reported, but it is the customer's favour, not a loss) |
| `UNQUOTED_CHARGE` | charge on the invoice that the quote does not have |
| `MISSING_CHARGE` | quoted charge absent from the invoice |
| `CURRENCY_MISMATCH` | different currencies. One finding, and line comparison is skipped (USD and EUR amounts cannot be subtracted) |
| `EXPIRED_QUOTE` | invoice dated after the quote's `valid_until` |
| `ARITHMETIC_ERROR` | printed invoice total differs from the sum of its own lines (beyond 1 cent) |

`total_variance_minor` = how far the invoice is from the quote overall. A charge with no readable amount raises `ValueError` (fail loudly; a silent 0 would hide an error).

## Reading the toy's central lines
- `allowed = max(ROUNDING_MINOR, quoted * TOLERANCE_BPS // 10_000)`: `//` is integer division, so no float ever appears.
- `charge_key`: `" ".join(c.label.lower().split()) if c.code == "OTHER" else c.code` - the identity of a charge is its code, except for the catch-all bucket.
- `q.keys() | i.keys()`: set union of both dictionaries' keys, so every charge on either side is looked at once.

## Real data check
Run against the generator's 45 cases with a perfect extraction: every case produced exactly the expected findings. Quote matching: 32 by reference, 11 by route, 2 `ambiguous` (the extraction schema has no carrier field, so two quotes on the same route look identical). Ambiguity goes to a human; it is not guessed.

## Self-check (Part 1)
1. Why does a cited-but-missing quote return `reference_not_found` instead of trying route matching? *A citation that points nowhere is information (wrong or forged reference); falling back could attach the invoice to a different quote and approve it.*
2. Why integer basis points instead of `0.005`? *Floats cannot represent most decimals exactly; integers make the tolerance check exact and repeatable.*
3. Why is `OTHER` keyed by its label? *Otherwise "Peak Season" and "Low Sulphur" would add up into one OTHER and a real overcharge could be netted against an unrelated charge.*
4. Why do we skip line comparison on a currency mismatch? *The amounts are in different units; every difference would be meaningless noise on top of the one real finding.*
5. Why is an expired quote not a reason to refuse matching? *The invoice still belongs to that quote; "expired" is a finding about it, and refusing would hide the invoice entirely.*

## The toy example (standalone, not part of the repo)
Run it with `python reconcile_demo.py`. Try: change `TOLERANCE_BPS` to 0 or 200 and see which invoices change; add a second quote on the same route and watch matching turn `ambiguous`; change the "overcharge" amount to be just inside, then just outside, tolerance.

```python
"""Day 41 toy: compare a quote with an invoice by canonical code and list the discrepancies.
Standalone (standard library only). NOT part of the repo; run it from anywhere.
All money is an integer number of minor units (cents). No floats, no LLM.
"""
from dataclasses import dataclass, field
from datetime import date

TOLERANCE_BPS = 50  # 0.5% written as basis points (1 bp = 0.01%), so we can stay in integers
ROUNDING_MINOR = 1  # always forgive one cent of rounding


@dataclass
class Charge:
    code: str  # canonical code from normalization ("OTHER" if unknown)
    label: str  # the raw label as printed
    amount: int


@dataclass
class Doc:
    ref: str
    carrier: str
    route: str  # origin-destination, e.g. "CNSHA-PKKHI"
    equipment: str
    currency: str
    day: date  # quote: issued; invoice: invoice date
    charges: list[Charge]
    valid_until: date | None = None  # quotes only
    quote_ref: str | None = None  # invoices only: the quote they cite (may be missing)
    stated_total: int | None = None  # invoices only: the total as PRINTED


@dataclass
class Discrepancy:
    type: str
    key: str | None = None
    quoted: int | None = None
    invoiced: int | None = None
    note: str = ""


# --- step 1: which quote does this invoice belong to? ---------------------------------

def match_quote(invoice: Doc, quotes: list[Doc]) -> tuple[Doc | None, str]:
    if invoice.quote_ref:  # explicit reference: trust it
        found = [q for q in quotes if q.ref == invoice.quote_ref]
        return (found[0], "by reference") if found else (None, "cited quote not found")
    # no reference: same carrier, route and equipment, issued on or before the invoice date.
    # (We do NOT require the quote to still be valid: judging validity is a separate check.)
    candidates = [q for q in quotes if (q.carrier, q.route, q.equipment) == (invoice.carrier, invoice.route, invoice.equipment)
                  and q.day <= invoice.day]
    if len(candidates) == 1:
        return candidates[0], "by route and date"
    return None, "ambiguous: send to a human" if candidates else "no candidate quote"


# --- step 2: compare the charges ------------------------------------------------------

def charge_key(c: Charge) -> str:
    """Charges are compared by canonical code. 'OTHER' is a bucket for unrelated things,
    so for OTHER the cleaned label is the identity (otherwise two different surcharges would be merged)."""
    return " ".join(c.label.lower().split()) if c.code == "OTHER" else c.code


def totals_by_key(charges: list[Charge]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in charges:
        out[charge_key(c)] = out.get(charge_key(c), 0) + c.amount
    return out


def within_tolerance(quoted: int, invoiced: int) -> bool:
    allowed = max(ROUNDING_MINOR, quoted * TOLERANCE_BPS // 10_000)
    return abs(invoiced - quoted) <= allowed


def reconcile(quote: Doc, invoice: Doc) -> list[Discrepancy]:
    found: list[Discrepancy] = []
    if quote.valid_until and invoice.day > quote.valid_until:
        found.append(Discrepancy("EXPIRED_QUOTE", note=f"invoice {invoice.day}, quote valid until {quote.valid_until}"))

    if quote.currency != invoice.currency:
        # EUR amounts cannot be compared with USD amounts. One finding, and stop comparing amounts.
        found.append(Discrepancy("CURRENCY_MISMATCH", note=f"quoted in {quote.currency}, invoiced in {invoice.currency}"))
    else:
        q, i = totals_by_key(quote.charges), totals_by_key(invoice.charges)
        for key in sorted(q.keys() | i.keys()):
            if key not in i:
                found.append(Discrepancy("MISSING_CHARGE", key, quoted=q[key]))
            elif key not in q:
                found.append(Discrepancy("UNQUOTED_CHARGE", key, invoiced=i[key]))
            elif not within_tolerance(q[key], i[key]):
                found.append(Discrepancy("OVERCHARGE" if i[key] > q[key] else "UNDERCHARGE", key, q[key], i[key]))

    line_sum = sum(c.amount for c in invoice.charges)
    if invoice.stated_total is not None and abs(invoice.stated_total - line_sum) > ROUNDING_MINOR:
        found.append(Discrepancy("ARITHMETIC_ERROR", invoiced=invoice.stated_total, quoted=line_sum,
                                 note="printed total differs from the sum of the lines"))
    return found


# --- demo data: one quote, and seven invoices each damaged in a different way ------------

QUOTE = Doc("Q-1", "meridian", "CNSHA-PKKHI", "40GP", "USD", date(2026, 8, 3), valid_until=date(2026, 8, 17), charges=[
    Charge("OCEAN_FREIGHT", "Ocean Freight", 300_000), Charge("BAF", "BAF", 27_000),
    Charge("THC_ORIGIN", "THC Origin", 14_000), Charge("DOC_FEE", "Documentation Fee", 7_500)])


def invoice(name: str, charges: list[Charge], *, currency="USD", day=date(2026, 8, 10), total_delta=0) -> tuple[str, Doc]:
    total = sum(c.amount for c in charges) + total_delta
    return name, Doc("INV-" + name, "meridian", "CNSHA-PKKHI", "40GP", currency, day, charges, quote_ref="Q-1", stated_total=total)


def base(**changes: int) -> list[Charge]:  # the quote's charges, with new spellings and optional amount changes
    spell = {"OCEAN_FREIGHT": "Basic Ocean Freight", "BAF": "Bunker Adjustment Factor", "THC_ORIGIN": "Origin Terminal Handling", "DOC_FEE": "B/L Fee"}
    return [Charge(c.code, spell[c.code], changes.get(c.code, c.amount)) for c in QUOTE.charges]


CASES = [
    invoice("clean", base()),
    invoice("rounding", base(BAF=27_001)),
    invoice("overcharge", base(THC_ORIGIN=17_000)),
    invoice("unquoted", base() + [Charge("OTHER", "Peak Season Surcharge", 15_000)]),
    invoice("two-unquoted", base() + [Charge("OTHER", "Peak Season Surcharge", 15_000), Charge("OTHER", "Low Sulphur Surcharge", 9_000)]),
    invoice("missing", base()[:-1]),
    invoice("currency", base(), currency="EUR"),
    invoice("expired", base(), day=date(2026, 9, 1)),
    invoice("arithmetic", base(), total_delta=5_000),
]

if __name__ == "__main__":
    for name, inv in CASES:
        print(f"\n{name}:")
        found = reconcile(QUOTE, inv)
        for d in found:
            print(f"   {d.type:<17}{(d.key or ''):<26}quoted={d.quoted}  invoiced={d.invoiced}  {d.note}")
        if not found:
            print("   no discrepancies")

    print("\n--- matching without a quote reference ---")
    q2 = Doc("Q-2", "meridian", "CNSHA-PKKHI", "40GP", "USD", date(2026, 8, 5), valid_until=date(2026, 8, 19), charges=[])
    other_route = Doc("Q-3", "meridian", "DEHAM-PKKHI", "40GP", "USD", date(2026, 8, 3), charges=[])
    for label, quotes in (("one candidate", [QUOTE, other_route]), ("two candidates", [QUOTE, q2, other_route]), ("none", [other_route])):
        inv = Doc("INV-X", "meridian", "CNSHA-PKKHI", "40GP", "USD", date(2026, 8, 10), [])
        match, why = match_quote(inv, quotes)
        print(f"   {label:<15} -> {match.ref if match else None}  ({why})")
```

# Part 2 - Persistence

## Concepts

**Persistence.** Writing results to the database so they outlive the process. Until now results lived in a Python dictionary and in eval reports.

**Raw JSONB plus typed columns.** Each extraction keeps the raw model output (`data`, JSONB) for audit - "what exactly did the model say?" - and typed columns (`currency`, `total_minor`, `doc_date`, ...) for querying and reconciling. Neither replaces the other.

**Transaction (all or nothing).** A group of writes that commit together or not at all. Saving an extraction, its charges and the document's new status is one transaction: a crash half-way leaves nothing behind. In the repo this is `tenant_session`; repositories never commit, the service owns the transaction.

**Idempotency.** Running the same step twice gives the same state as running it once. Enforced by *unique constraints*: one extraction per document, one reconciliation per invoice. Re-processing replaces the old rows (delete, then insert) rather than adding duplicates.

**Composite foreign key.** Every child row points at its parent by `(tenant_id, id)`, not by `id` alone, and the parent has `UNIQUE (tenant_id, id)`. Postgres checks foreign keys *without* applying row-level security, so a plain FK would let tenant B create a row linked to tenant A's document. With the composite key the pair `(B, A's document)` does not exist, so the insert is refused. RLS hides rows; composite FKs make bad links impossible. Both are needed.

**Row-level security (RLS).** Already in place from Week 8's start: every new table gets the same `tenant_isolation` policy (`tenant_id = app_current_tenant()`), so the database itself filters by tenant.

**Cascade.** `ON DELETE CASCADE`: deleting an extraction removes its charges, and any reconciliation that points at it, and that reconciliation's discrepancies.

**Repository vs service.** Repository: plain database calls, no rules, never commits. Service: the business rule ("save a result", "reconcile this invoice"), owns the transaction, returns plain values (not ORM objects, whose attributes expire after commit). Mapping between pipeline objects and rows is kept in a separate pure module so it can be tested without a database.

**Alembic migration.** A versioned script that changes the schema. `alembic check` verifies the models in code match the database; it was clean after migration 0003.

## What changed in the repo
| File | What | Why |
|---|---|---|
| `models/extraction.py` (new) | `Extraction`, `Charge` | typed columns + raw JSONB; composite FKs |
| `models/reconciliation.py` (new) | `Reconciliation`, `Discrepancy` | one reconciliation per invoice; findings as rows |
| `models/document.py` | `UNIQUE (tenant_id, id)` | parent side of the composite FK |
| `migrations/versions/0003_results_and_reconciliation.py` (new) | 4 tables, indexes, RLS policy on each | schema change; `downgrade` drops child-first |
| `repositories/documents.py`, `extractions.py`, `reconciliations.py` (new/extended) | `create`, `record_outcome`, `replace_for_document`, `get`, `get_for_document`, `list_by_type`, `get_charges`, `replace_for_invoice`, `get_for_invoice`, `get_discrepancies` | all SQL in one layer; no rules |
| `services/result_mapping.py` (new) | `document_outcome`, `extraction_values`, `typed_from_rows`, `discrepancy_values` | pure translation, testable without a database |
| `services/results.py` (new) | `save_pipeline_result`, `reconcile_invoice`, `InvoiceNotFound` | the rules and the transaction |
| `tests/test_result_mapping.py` (new, 5 tests) | round trip of all 45 cases through row values gives the generator's expected findings | catches a column forgotten in the mapping |
| `tests/test_persistence.py` (new, 13 tests) | real Postgres: round trip, replace, failed re-run, reconcile, clean, twice, no quote, bad ids, tenant isolation, cross-tenant FK refusals (document and charge), rollback, cascade | proves the promises the migration made |

## Decisions and known limits
- **A failed re-run keeps the old extraction.** The document status describes the latest run; the extraction is the latest *successful* reading. Deleting good data because of one flaky model call would be worse.
- **`unsupported` (e.g. a rate sheet) is stored with document status `failed`.** `doc_type` still says what it is, so nothing is lost.
- **Not handled yet:** a quote that arrives *after* its invoice is not reconciled automatically; reconciliation runs when asked. Auto-trigger comes with the API/UI work.
- **No carrier field** in the extraction schema -> 2 of 45 matches are `ambiguous`. A schema change is the fix, later.
- **Verification:** the migration was verified on a real Postgres (RLS isolation, composite-FK refusals, unique and check constraints, cascade, downgrade/upgrade) and `alembic check` was clean on the Mac; the ORM, repository and service code was verified by the 18 new tests above.

## Self-check (Part 2)
1. Why keep both the raw JSON and typed columns? *Raw = audit trail of what the model said; typed = fast, safe queries and comparisons. Only typed would lose the evidence; only raw would make every query parse JSON.*
2. RLS already hides other tenants' rows. Why also composite foreign keys? *Postgres checks FKs without RLS, so a plain FK lets tenant B link a row to A's document. The composite key refuses a pair that does not exist.*
3. Why does the service, not the repository, own the transaction? *A repository call is one step; "save a result" is several steps that must succeed together. Only the service knows where the boundary is.*
4. What happens if the process crashes after the extraction insert but before the document status update? *Nothing is kept: the whole `tenant_session` block rolls back. The `test_a_failure_part_way...` test proves it.*
5. Why `replace_for_document` (delete then insert) instead of updating the old row? *Charges can change in number and order; replacing the whole set is simpler and cannot leave stale charges. The unique constraint guarantees at most one.*
6. Why does `reconcile_invoice` raise `InvoiceNotFound` when tenant B asks about tenant A's invoice? *Under RLS the row simply does not exist for B, and answering "forbidden" would confirm that it exists elsewhere.*

## Experiments to try
1. In `reconcile_demo.py`, set `TOLERANCE_BPS = 0`: which invoices flip from clean to flagged? Then 200?
2. In `persist_demo.py`, remove the composite foreign key on `charges` and rerun step 4. What changes?
3. In `persist_demo.py` step 2, move the broken charge to be first. Is the outcome different? Why not?

## The toy example (standalone, not part of the repo)
Run it with `python persist_demo.py`. SQLite stands in for Postgres here; it cannot do row-level security, so isolation is shown with composite foreign keys only.

```python
"""Day 41 toy: saving pipeline results safely. Standalone (sqlite3 is in Python's standard library).
NOT part of the repo. SQLite cannot do row-level security, so tenant isolation here is shown with
composite foreign keys; the real project adds Postgres row-level security on top of them.
"""
import json
import sqlite3
import uuid

db = sqlite3.connect(":memory:")
db.execute("PRAGMA foreign_keys = ON")  # SQLite ignores foreign keys unless you ask

db.executescript("""
CREATE TABLE documents (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, filename TEXT NOT NULL,
    UNIQUE (tenant_id, id)                         -- lets child tables point at (tenant, id) together
);
CREATE TABLE extractions (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, document_id TEXT NOT NULL UNIQUE,   -- one per document
    doc_type TEXT NOT NULL, reference TEXT, data TEXT NOT NULL,                       -- data = what the model returned (JSON)
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, document_id) REFERENCES documents (tenant_id, id)
);
CREATE TABLE charges (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, extraction_id TEXT NOT NULL,
    canonical_code TEXT NOT NULL, raw_label TEXT NOT NULL, amount_minor INTEGER NOT NULL, known INTEGER NOT NULL,
    FOREIGN KEY (tenant_id, extraction_id) REFERENCES extractions (tenant_id, id)
);
CREATE TABLE reconciliations (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, quote_extraction_id TEXT NOT NULL, invoice_extraction_id TEXT NOT NULL,
    total_variance_minor INTEGER,
    UNIQUE (tenant_id, id), UNIQUE (quote_extraction_id, invoice_extraction_id),      -- the same pair is stored once
    FOREIGN KEY (tenant_id, quote_extraction_id) REFERENCES extractions (tenant_id, id),
    FOREIGN KEY (tenant_id, invoice_extraction_id) REFERENCES extractions (tenant_id, id)
);
CREATE TABLE discrepancies (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, reconciliation_id TEXT NOT NULL,
    type TEXT NOT NULL, charge_code TEXT, quoted_minor INTEGER, invoiced_minor INTEGER, variance_minor INTEGER,
    FOREIGN KEY (tenant_id, reconciliation_id) REFERENCES reconciliations (tenant_id, id)
);
""")

new_id = lambda: str(uuid.uuid4())  # noqa: E731
A, B = "tenant-A", "tenant-B"


def add_document(tenant: str, filename: str) -> str:
    doc_id = new_id()
    db.execute("INSERT INTO documents VALUES (?, ?, ?)", (doc_id, tenant, filename))
    return doc_id


def save_extraction(tenant: str, document_id: str, doc_type: str, reference: str, charges: list[tuple]) -> str:
    """One transaction: the extraction row and ALL its charges are saved, or none of them are."""
    ext_id = new_id()
    with db:  # sqlite3: commits if the block ends normally, rolls back if an exception escapes
        db.execute("INSERT INTO extractions VALUES (?, ?, ?, ?, ?, ?)",
                   (ext_id, tenant, document_id, doc_type, reference, json.dumps({"charges": len(charges)})))
        for code, label, amount, known in charges:
            db.execute("INSERT INTO charges VALUES (?, ?, ?, ?, ?, ?, ?)", (new_id(), tenant, ext_id, code, label, amount, known))
    return ext_id


def count(table: str) -> int:
    return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def attempt(title: str, action) -> None:
    try:
        action()
        print(f"  {title}: accepted")
    except sqlite3.IntegrityError as e:
        print(f"  {title}: REJECTED by the database ({e})")


if __name__ == "__main__":
    print("1. Tenant A saves a quote and an invoice")
    q_doc, i_doc = add_document(A, "quote.pdf"), add_document(A, "invoice.pdf")
    q = save_extraction(A, q_doc, "quote", "Q-1", [("OCEAN_FREIGHT", "Ocean Freight", 300_000, 1), ("BAF", "BAF", 27_000, 1)])
    i = save_extraction(A, i_doc, "invoice", "INV-1", [("OCEAN_FREIGHT", "O/F", 300_000, 1), ("BAF", "Fuel Surcharge", 31_000, 1),
                                                       ("OTHER", "Peak Season Surcharge", 15_000, 0)])
    print(f"  extractions={count('extractions')} charges={count('charges')}")

    print("2. All-or-nothing: the third charge is broken (no amount)")
    doc3 = add_document(A, "invoice2.pdf")
    attempt("save invoice2", lambda: save_extraction(A, doc3, "invoice", "INV-2", [("BAF", "BAF", 1, 1), ("CAF", "CAF", 2, 1), ("ISPS", "ISPS", None, 1)]))
    print(f"  extractions={count('extractions')} charges={count('charges')}   <- nothing from invoice2 was kept")

    print("3. Processing the same document twice")
    attempt("second extraction of quote.pdf", lambda: save_extraction(A, q_doc, "quote", "Q-1", []))

    print("4. Tenant B tries to attach a charge to tenant A's extraction")
    attempt("charge for B pointing at A's extraction",
            lambda: db.execute("INSERT INTO charges VALUES (?, ?, ?, 'BAF', 'BAF', 1, 1)", (new_id(), B, q)))

    print("5. Store a reconciliation, then read the report back from the database")
    with db:
        rec = new_id()
        db.execute("INSERT INTO reconciliations VALUES (?, ?, ?, ?, ?)", (rec, A, q, i, 19_000))
        for row in (("OVERCHARGE", "BAF", 27_000, 31_000, 4_000), ("UNQUOTED_CHARGE", "OTHER", None, 15_000, 15_000)):
            db.execute("INSERT INTO discrepancies VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (new_id(), A, rec, *row))
    attempt("the same quote/invoice pair again", lambda: db.execute("INSERT INTO reconciliations VALUES (?, ?, ?, ?, 0)", (new_id(), A, q, i)))
    report = db.execute("""SELECT qe.reference, ie.reference, r.total_variance_minor, d.type, d.charge_code, d.variance_minor
                           FROM reconciliations r JOIN extractions qe ON qe.id = r.quote_extraction_id
                           JOIN extractions ie ON ie.id = r.invoice_extraction_id
                           JOIN discrepancies d ON d.reconciliation_id = r.id ORDER BY d.type""").fetchall()
    for qref, iref, total, dtype, code, var in report:
        print(f"  {iref} vs {qref}: total variance {total:,} -> {dtype} {code} {var:+,}")
```



# Day 42 - Human review (pause and resume a graph) and the CI evaluation gate

Status: code done and pushed. Part 1 = concepts and a toy. Part 2 = the review step in the real graph. Part 3 = a CI workflow with a quality gate.
CI first run on GitHub: **(fill in: green / what failed and the fix)**.

## The problem this solves
Until today `needs_review` was a dead end: the pipeline set a flag and stopped, and nobody could act on it. A real review flow needs three things:
1. the graph stops at the exact point where it needs a person,
2. it remembers everything it knew, for minutes or days, even across a server restart,
3. when the person answers, it carries on from there.

This keeps the project principle: *the LLM reads, software decides* - and now a person can override. The person is not trusted blindly either: a correction goes through the same `validate()` as the model's reading.
Second half of the day: code that quietly breaks is the next problem, so a robot (CI) runs the tests and a quality gate on every push.

---

# Part 1 - Concepts

## Glossary
- **Checkpoint.** A snapshot of the graph's whole state, saved after every step. (Django analogy: saving a model row after each stage of a wizard.)
- **Checkpointer.** The component that stores checkpoints. `MemorySaver` keeps them in the Python process's memory (right for tests; lost when the process stops). Production needs a database-backed one such as `PostgresSaver`.
- **Thread (`thread_id`).** The name of one run's saved history. One document = one thread. Two thread ids never see each other's state. Passed as `config={"configurable": {"thread_id": "..."}}`.
- **`interrupt(value)`.** Called inside a node. The graph stops right there, saves a checkpoint, and hands `value` to whoever called `invoke()`. Think of `input()` that can wait for days and survive a restart.
- **`Command(resume=answer)`.** What you pass to `invoke()` later to continue. `answer` becomes the *return value* of the `interrupt()` call.
- **Human-in-the-loop.** The pattern: software does the routine work, a person decides the hard or risky cases.
- **`graph.get_state(config)`.** Reads the saved state of a thread without running anything. `.next` = which node runs next (empty tuple = finished), `.values` = the state, `.tasks[i].interrupts[j].value` = the question a paused node is asking.

## The one rule that surprises everyone: the node runs again from its first line
When you resume, the paused node does NOT continue from the `interrupt()` line. It runs again **from its first line**; this time `interrupt()` returns the saved answer instead of stopping.
Consequences:
- Everything above `interrupt()` runs twice, so it must be safe to repeat (no e-mails, no payments, no database inserts).
- If a node calls `interrupt()` several times, LangGraph hands back the earlier answers **in order** (call #1 gets answer 1, call #2 gets answer 2) and pauses at the first call that has no answer yet.
- `interrupt()` stops the graph by raising a special exception (`GraphInterrupt`, which is NOT a `ValueError`). Never wrap `interrupt()` in a bare `except Exception`: it would swallow the pause and break the feature silently.

## Two ways to build a "ask again" loop
| | Loop inside the node (what we built) | Loop in the graph (router edge back to the node) |
|---|---|---|
| Rules testable without LangGraph | yes: `review_loop(state, ask)` takes any function | harder |
| Each round saved as its own checkpoint | no (earlier answers are replayed) | yes |
| Rounds visible in LangSmith | as one step | as separate steps |
| Replay needed | yes, so the loop must be repeatable | no |

The Day 39 repair loop (validate -> extractor) is the graph style. The review loop is the in-node style. We chose it for review for the same reason `nodes.py` has no LangGraph import: the rules are unit-testable. LangGraph's contribution to review is **pause + checkpoint + resume**; the `for` loop is plain Python.

## The graph today
```
START -> parse -> classify -+-> extract_quote   -+-> validate -+-> END                (clean, or human_review=False)
                            +-> extract_invoice -+      ^      |
                            |                          +------+  hint and retries left: back to the extractor
                            +-> unsupported -> END
                                                      validate -+-> human_review -> END   (errors remain, human_review=True)
                                                                      ^ pauses here until a person answers
```
Router order in `route_after_validate`: (1) hint + retries left -> try again; (2) still `needs_review` -> `"review"`; (3) otherwise `"end"`. A retry always comes first, so a person is asked only when the machine ran out of chances.

---

## The toy example (standalone, not part of the repo)
Run it with the venv active: `python review_demo.py` (needs `langgraph`; we have 1.2.15).

What each scenario proved (your real output matched all of these):
1. A bad invoice runs until `review`, then stops: `next=('review',)`, and `get_state` shows the exact question the human sees.
2. A clean invoice on another thread never pauses; the first one is still waiting (threads are independent).
3. Resume with a correction -> status `corrected`; the review node's start line printed again (the re-run rule).
4. Resume with a WRONG correction -> plain code catches it (`needs_review`); the human is not trusted blindly.
5. A new empty `MemorySaver` ("server restart") forgot the waiting invoice -> production needs a durable checkpointer.

```python
"""Day 42 toy: pause a LangGraph graph for a human, then resume it.
Standalone. NOT part of the repo; run it from anywhere with the project's venv active (langgraph is already installed there).
The 'invoice' is just a list of charge amounts in cents and the total printed on the document.
"""
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class State(TypedDict, total=False):
    lines: list[int]  # charge amounts in cents, as the "model" read them
    printed_total: int  # the total printed on the document
    status: str  # ok | needs_review | approved | corrected | rejected
    decision: dict  # what the human answered


def validate(state: State) -> dict:
    """Plain code decides: do the lines add up to the printed total?"""
    ok = sum(state["lines"]) == state["printed_total"]
    return {"status": "ok" if ok else "needs_review"}


def route_after_validate(state: State) -> str:
    return "review" if state["status"] == "needs_review" else "end"


def review(state: State) -> dict:
    print("      [review node: starts]")  # watch how many times this line prints
    decision = interrupt({  # <- the graph STOPS here and hands this dictionary to whoever called invoke()
        "problem": "lines do not add up to the printed total",
        "lines": state["lines"],
        "sum_of_lines": sum(state["lines"]),
        "printed_total": state["printed_total"],
    })
    # We only get here after someone resumes the graph. `decision` is exactly what they sent.
    print(f"      [review node: continues with {decision}]")
    if decision["action"] == "reject":
        return {"decision": decision, "status": "rejected"}
    if decision["action"] == "correct":
        lines = decision["lines"]
        # A human's correction is NOT trusted blindly: the same plain code checks it again.
        status = "corrected" if sum(lines) == state["printed_total"] else "needs_review"
        return {"decision": decision, "lines": lines, "status": status}
    return {"decision": decision, "status": "approved"}  # "approve": the human accepts it as it is


g = StateGraph(State)
g.add_node("validate", validate)
g.add_node("review", review)
g.add_edge(START, "validate")
g.add_conditional_edges("validate", route_after_validate, {"review": "review", "end": END})
g.add_edge("review", END)

checkpointer = MemorySaver()  # remembers the state after every step, in this process's memory
graph = g.compile(checkpointer=checkpointer)


def show(title: str, config: dict) -> None:
    snap = graph.get_state(config)
    pending = snap.tasks[0].interrupts[0].value if snap.tasks and snap.tasks[0].interrupts else None
    print(f"   {title}: next={snap.next} status={snap.values.get('status')} waiting_for_human={pending is not None}")


if __name__ == "__main__":
    BAD = {"lines": [300_000, 27_000, 14_000], "printed_total": 351_000}  # lines add up to 341,000

    print("1. A bad invoice runs until the review step, then stops")
    a = {"configurable": {"thread_id": "invoice-1"}}  # thread_id = the name of this one document's run
    graph.invoke(BAD, a)
    show("after invoke", a)
    print("   the question the human sees:", graph.get_state(a).tasks[0].interrupts[0].value)

    print("\n2. A different document has its own thread and is not affected")
    b = {"configurable": {"thread_id": "invoice-2"}}
    graph.invoke({"lines": [100_000, 20_000], "printed_total": 120_000}, b)  # a clean one: never pauses
    show("clean invoice", b)
    show("invoice-1 still waiting", a)

    print("\n3. Resume invoice-1 with a correction (the missing 100.00 line)")
    graph.invoke(Command(resume={"action": "correct", "lines": [300_000, 27_000, 14_000, 10_000]}), a)
    show("after resume", a)

    print("\n4. Resume a second bad invoice with a WRONG correction: code catches it")
    c = {"configurable": {"thread_id": "invoice-3"}}
    graph.invoke(BAD, c)
    graph.invoke(Command(resume={"action": "correct", "lines": [300_000, 27_000, 14_000, 9_999]}), c)
    show("wrong correction", c)

    print("\n5. 'Restart the server': a new, empty checkpointer forgets everything")
    graph2 = g.compile(checkpointer=MemorySaver())
    snap = graph2.get_state(a)
    print(f"   invoice-1 on the new checkpointer: values={snap.values} next={snap.next}")
    d = {"configurable": {"thread_id": "invoice-4"}}
    graph.invoke(BAD, d)
    print("   invoice-4 is waiting for a human on the old checkpointer; a restart would lose that review request")
```

---

# Part 2 - The review step in the real graph

## What changed and why
| File | Change | Why |
|---|---|---|
| `pipeline/review.py` (new) | `Decision`, `parse_decision`, `build_review_request`, `apply_decision`, `review_loop` | the rules of a human answer, with no LangGraph and no database |
| `pipeline/nodes.py` | router can return `"review"`; `DocState` gets `review`; `run_sequentially` stops on `"review"` | route unresolved errors to a person |
| `pipeline/graph.py` | optional `human_review` node, `checkpointer` parameter, `pending_review`, `resume_document`, `review_thread_id`, `NoPendingReview`, `thread_id` on `run_document` | the pause/resume plumbing |
| `pyproject.toml` | `langgraph>=1.0` | `interrupt` and `Command` need a recent LangGraph |
| `tests/test_review.py` (new, 19 tests) | the rules, the loop, the router - no LangGraph | |
| `tests/test_review_graph.py` (new, 9 tests) | real pause and resume with `MemorySaver` | |

## `nodes.py`: exact changes
```python
# DocState
    status ends as one of: ok | needs_review | reviewed | rejected | failed | unsupported
    review: dict  # who reviewed it and what they decided (set by the review step)

def route_after_validate(state):
    if state.get("hint") and state["attempts"] <= MAX_RETRIES:         # 1. unchanged: try again
        return f"extract_{state['doc_type']}"
    return "review" if state.get("status") == "needs_review" else "end"   # 2. new (was: return "end")

# run_sequentially
    if route_after_validate(state) in ("end", "review"):               # was: == "end"
        return state
```

Why the last change matters: `run_sequentially` has nobody to ask. If it saw `"review"` and only checked `== "end"`, it would loop forever re-extracting.

## `review.py` (final code)
```python
"""Human review of a document the pipeline could not settle. Plain functions: no LangGraph, no database.

When validation still finds errors after the retries, a person looks at the extraction and answers with a
decision. This file says what a valid answer looks like and what each answer does to the state. The graph
(graph.py) only handles the pausing; the rules live here so they can be tested without it.

A human is not trusted blindly either: a correction goes through the same validate() as the model's reading.
"""
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass

from freight_intel.pipeline.schemas import InvoiceExtraction, QuoteExtraction
from freight_intel.pipeline.validation import validate

ACTIONS = ("approve", "correct", "reject")
MAX_ROUNDS = 3  # the reviewer gets this many tries; after that the document stays needs_review
MAX_NOTE_CHARS = 1000
SCHEMAS = {"quote": QuoteExtraction, "invoice": InvoiceExtraction}


@dataclass(frozen=True)
class Decision:
    action: str  # approve | correct | reject
    reviewer: str  # who decided; set by our code from the logged-in user, never by the model
    note: str = ""
    extraction: dict | None = None  # "correct" only: the whole corrected extraction, in the model's text shape


def parse_decision(raw) -> Decision:
    """Check what came back from the person. Raises ValueError with a message the person can read."""
    if not isinstance(raw, Mapping):
        raise ValueError("the decision must be a JSON object")
    action = raw.get("action")
    if action not in ACTIONS:
        raise ValueError(f"action must be one of: {', '.join(ACTIONS)}")
    reviewer = str(raw.get("reviewer") or "").strip()
    if not reviewer:
        raise ValueError("the reviewer is required")
    note = str(raw.get("note") or "").strip()
    if len(note) > MAX_NOTE_CHARS:
        raise ValueError(f"the note is longer than {MAX_NOTE_CHARS} characters")
    extraction = raw.get("extraction")
    if action == "correct":
        if not isinstance(extraction, Mapping):
            raise ValueError("a correction must include the corrected extraction")
        return Decision(action, reviewer, note, dict(extraction))
    return Decision(action, reviewer, note)


def build_review_request(state: Mapping, *, error: str | None = None) -> dict:
    """What the person is shown: plain JSON-friendly values only (it is saved with the checkpoint)."""
    request = {
        "doc_type": state["doc_type"],
        "extraction": state["extraction"].model_dump(mode="json"),
        "issues": [asdict(issue) for issue in state.get("issues", [])],
        "attempts": state.get("attempts", 0),
    }
    if error:
        request["error"] = error
    return request


def apply_decision(state: Mapping, decision: Decision) -> dict:
    """The state changes one decision causes. Raises ValueError if the decision cannot be applied."""
    review = {"action": decision.action, "reviewer": decision.reviewer, "note": decision.note}
    if decision.action == "reject":
        return {"status": "rejected", "review": review}
    if decision.action == "approve":
        still_has_errors = any(issue.severity == "error" for issue in state.get("issues", []))
        if still_has_errors and not decision.note:
            raise ValueError("approving a document that still has errors needs a note saying why")
        return {"status": "reviewed", "review": review}
    corrected = SCHEMAS[state["doc_type"]].model_validate(decision.extraction)  # ValidationError is a ValueError
    result = validate(state["doc_type"], corrected)
    return {
        "extraction": corrected,
        "typed": result.typed,
        "issues": result.issues,
        "status": "reviewed" if result.ok else "needs_review",
        "hint": "",
        "review": review,
    }


def review_loop(state: Mapping, ask: Callable[[dict], object]) -> dict:
    """Ask until the person gives a usable answer (at most MAX_ROUNDS times). Returns the state update.

    `ask` shows a request and returns the person's raw answer. In the graph it is LangGraph's interrupt();
    in tests it is a scripted function. This function must be repeatable: after a pause the graph runs it
    again from the top, and interrupt() hands back the earlier answers in order.
    """
    request = build_review_request(state)
    latest: dict = {}
    for _ in range(MAX_ROUNDS):
        raw = ask(request)
        try:
            update = apply_decision(state, parse_decision(raw))
        except ValueError as exc:
            request = build_review_request(state, error=str(exc)[:500])
            continue
        if update["status"] != "needs_review":
            return update
        latest = update  # a correction that still has errors: show what remains and ask again
        state = {**state, **update}
        request = build_review_request(state)
    return {**latest, "status": "needs_review", "error": f"review not completed after {MAX_ROUNDS} attempts"}
```

### How to read it
- `Decision` is what a valid answer looks like. `reviewer` is set by OUR code from the logged-in user, never by the model or the document.
- `parse_decision` validates untrusted input (it will arrive as JSON from a web form). Every failure is a `ValueError` with a message a person can read.
- `build_review_request` returns plain JSON-friendly values only, because it is saved inside the checkpoint.
- `apply_decision`: `reject` -> `rejected`. `approve` -> `reviewed`, the findings stay on record, and **a note is required if errors remain** (every override explains itself). `correct` -> build the corrected extraction with the same pydantic schema, run `validate()`, `reviewed` only if no errors remain. A pydantic `ValidationError` is a `ValueError`, so a malformed correction is handled like any unusable answer.
- `review_loop`: ask, check, ask again with the reason attached (max 3 rounds). A correction that still has errors is asked again with the remaining issues shown. After 3 rounds the document stays `needs_review` and keeps the latest correction. `ask` is a plain function: `interrupt` in the graph, a scripted list in tests.
- An **approve** does not mean "the invoice is fine". It means "the reading is a faithful copy of the document; the problem is in the document itself" (for example the carrier printed a wrong total). That finding goes on to reconciliation as an `ARITHMETIC_ERROR`.

## `graph.py` (final code)
```python
"""Wires the nodes into a LangGraph graph.

  START -> parse -> classify -+-> extract_quote   -+-> validate -+-> END
                              +-> extract_invoice -+      ^       |
                              |                    ^      |       | TOTAL_MISMATCH and retries left
                              |                    +------+-------+  (hint goes back to the extractor)
                              +-> unsupported -> END      (any step can also jump to END on failure)

With human_review=True, a document that still has errors after the retries goes to a person instead of
straight to END:   validate -> human_review (pauses until someone answers) -> END

The two `add_conditional_edges` calls are the router pattern from Day 31, now
for real: after `classify`, the *state* decides which extractor runs.
"""
from collections.abc import Mapping

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from freight_intel.pipeline import nodes, prompts, review
from freight_intel.pipeline.llm import LLM
from freight_intel.pipeline.schemas import InvoiceExtraction, QuoteExtraction


class NoPendingReview(Exception):
    """Tried to answer a review request, but this document is not waiting for one."""


def human_review_node(state: nodes.DocState) -> dict:
    # interrupt() stops the graph here. When someone resumes it, this function runs again from the top
    # and interrupt() returns their answer, so nothing above it may have side effects.
    return review.review_loop(state, interrupt)


def build_graph(llm: LLM, *, checkpointer=None, human_review: bool = False):
    """human_review=True adds the pause-for-a-person step. It needs a checkpointer, which is what lets
    the graph remember where it stopped. Without it (the default) behaviour is exactly as before."""
    if human_review and checkpointer is None:
        raise ValueError("human_review=True needs a checkpointer so the graph can remember where it paused")
    g = StateGraph(nodes.DocState)

    g.add_node("parse", nodes.parse_node)
    g.add_node("classify", nodes.make_classify_node(llm))
    g.add_node("extract_quote", nodes.make_extract_node(llm, QuoteExtraction, prompts.EXTRACT_QUOTE_SYSTEM))
    g.add_node("extract_invoice", nodes.make_extract_node(llm, InvoiceExtraction, prompts.EXTRACT_INVOICE_SYSTEM))
    g.add_node("unsupported", nodes.unsupported_node)
    g.add_node("validate", nodes.validate_node)
    if human_review:
        g.add_node("human_review", human_review_node)
        g.add_edge("human_review", END)

    g.add_edge(START, "parse")
    # Conditional edge: call the router function, look its answer up in this map.
    g.add_conditional_edges("parse", nodes.route_after_parse, {"classify": "classify", "end": END})
    g.add_conditional_edges(
        "classify",
        nodes.route_after_classify,
        {"extract_quote": "extract_quote", "extract_invoice": "extract_invoice",
         "unsupported": "unsupported", "end": END},
    )
    for name in ("extract_quote", "extract_invoice"):
        g.add_conditional_edges(name, nodes.route_after_extract, {"validate": "validate", "end": END})
    g.add_edge("unsupported", END)
    # The loop: after validate, either finish or go back to the same extractor with a hint.
    g.add_conditional_edges(
        "validate",
        nodes.route_after_validate,
        {"extract_quote": "extract_quote", "extract_invoice": "extract_invoice",
         "review": "human_review" if human_review else END, "end": END},
    )

    return g.compile(checkpointer=checkpointer)


def review_thread_id(tenant_id, document_id) -> str:
    """One thread per document. The tenant is part of the name, so two companies can never share a thread."""
    return f"{tenant_id}:{document_id}"


def run_document(
    graph, path: str, *, tags: list[str] | None = None, metadata: dict | None = None, thread_id: str | None = None
) -> dict:
    """Run one file through the graph and return the final state.

    A graph built with a checkpointer needs a `thread_id`. If the run stopped for a review, the returned
    state is the one so far; check pending_review() to see whether a person is being waited for.

    `tags` and `metadata` appear on the trace in LangSmith, which is how you
    later filter "show me every invoice that needed review".
    """
    config = {"run_name": "freight_document", "tags": tags or [], "metadata": metadata or {}}
    if thread_id is not None:
        config["configurable"] = {"thread_id": thread_id}
    return graph.invoke({"file_path": str(path)}, config=config)


def pending_review(graph, thread_id: str) -> dict | None:
    """The request a person has to answer, or None if this document is not waiting for anyone."""
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    for task in snapshot.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def resume_document(graph, thread_id: str, decision: Mapping) -> dict:
    """Give the waiting graph the person's answer and run it to the end (or to the next question)."""
    if pending_review(graph, thread_id) is None:
        raise NoPendingReview(thread_id)
    return graph.invoke(
        Command(resume=dict(decision)),
        config={"run_name": "freight_document_review", "configurable": {"thread_id": thread_id}},
    )
```

### How to read it
- `human_review_node` is one line: `review.review_loop(state, interrupt)`.
- `build_graph(..., human_review=False)` is the default, so the evaluation (no checkpointer) behaves exactly as before; `needs_review` is then just a final status. `human_review=True` without a checkpointer raises an error up front.
- The router map sends `"review"` to `human_review`, or to `END` when review is off.
- `review_thread_id(tenant_id, document_id)` puts the tenant in the thread name. LangGraph's checkpoint tables are created by LangGraph, not by our migrations, and have **no row-level security**; tenant safety there must come from our service layer (build the id from the tenant, and check the document belongs to the caller before resuming).
- `pending_review` reads the saved state and returns the question, or `None`. `resume_document` refuses (`NoPendingReview`) when nobody is waiting, so a stale or guessed thread id does nothing.
- `run_document` returns the state so far when the run pauses; the caller must call `pending_review` to know whether a person is being waited for.
- `resume_document` uses a different `run_name` (`freight_document_review`) so the two traces are distinguishable in LangSmith: each `invoke()` call is its own trace. They are tied together only by `thread_id` (check the trace metadata).

## Using it (not run in production yet; this is what the service will do on Day 43)
```python
graph = build_graph(llm, checkpointer=MemorySaver(), human_review=True)
thread = review_thread_id(tenant_id, document_id)

state = run_document(graph, path, thread_id=thread)          # runs until done OR until it needs a person
request = pending_review(graph, thread)                      # None -> finished; else the dict a person must answer
final = resume_document(graph, thread, {
    "action": "approve", "reviewer": "ana@example.com",
    "note": "the printed total is wrong on the paper",       # required: errors remain
})
final["status"]            # "reviewed"
final["review"]            # who decided, what, and why
```

## Tests added
`tests/test_review.py` (19 tests, no LangGraph): bad decisions rejected with a readable message (6 cases); good decisions parse; request is plain JSON; approving over an error needs a note and keeps the findings; reject; a good correction passes validation; a wrong correction is caught by code; a correction of the wrong shape raises `ValueError`; the loop returns on the first usable answer, asks again after an unusable one and says why, shows what remains after a failing correction, gives up after the round limit but keeps the latest correction, and is **repeatable** (which the graph relies on); the router sends unresolved errors to review.

`tests/test_review_graph.py` (9 tests, real LangGraph + `MemorySaver`, uses the oracle and a generated invoice whose printed total is really wrong): review needs a checkpointer; a graph without review behaves as before; a wrong total pauses and the question lists `TOTAL_MISMATCH`; a clean document does not pause; approval finishes the run and records who decided; an unusable answer makes the graph ask again (this is the multi-interrupt replay); cannot answer a document that is not waiting; two waiting documents are independent; the thread name includes the tenant.

## Decisions and known limits
- **New status words `reviewed` and `rejected` exist only in the graph state.** Mapping them to database statuses (and storing who reviewed what, in a reviews table) belongs with the API on Day 43.
- **`MemorySaver` is for tests.** The service needs a Postgres-backed checkpointer or a paused review is lost on restart.
- **Checkpoint serialization.** The state holds dataclasses and pydantic models; LangGraph 1.x stores them fine here (tests pass). A warning about unregistered types would be acceptable; an error would mean simplifying the stored state.
- Only 5 of the 90 generated documents go to review: the invoices whose printed total really is wrong.

---

# Part 3 - CI and the evaluation gate

## Concepts
- **CI (continuous integration).** A robot runs your tests on a clean machine after every push. It catches what only works on your laptop (a forgotten file, a missing migration, a hand-installed library).
- **Workflow.** A YAML file in `.github/workflows/` telling GitHub what to run and when.
- **Trigger / job / step / runner.** The trigger is the event (`push`, `pull_request`, `workflow_dispatch` = a manual button). A job is a list of steps on one fresh virtual machine (the runner). A step is one command or one ready-made action (`uses:`).
- **Quality gate.** A check that fails the run when a number is below an agreed limit. A non-zero exit code is what makes the run red.
- **Secret.** A value GitHub stores and hands to a workflow at run time; it never appears in the code or logs. Set under repository Settings -> Secrets and variables -> Actions. Not needed yet: only the manual workflow uses `OPENAI_API_KEY`.
- **Service container vs `docker compose up`.** We use `docker compose up -d --wait db` in CI so it is the same file as on the laptop (it creates the owner and app roles through `init-app-role.sh`). `--wait` waits for the healthcheck.
- **Branch protection.** A GitHub rule that blocks merging until checks pass. It only matters when you work through pull requests; pushing straight to `main` means CI reports after the push and blocks nothing. Optional for a solo portfolio repo.

## What runs when
| | `ci.yml` | `eval-openai.yml` |
|---|---|---|
| Trigger | every push to `main` and every pull request | only when you press "Run workflow" in the Actions tab |
| What | Postgres, migrations, all tests, then the **oracle** evaluation through the gate | the real-model evaluation through the gate |
| Cost | free | about $0.03 per run |
| Secret needed | none | `OPENAI_API_KEY` |

The oracle is a pretend perfect extractor, so the free gate does NOT measure model quality; it catches a broken pipeline, validator, normalization or scoring. Real model quality is measured only by the manual workflow, and by running `python -m freight_intel.evaluation --llm openai` locally.

## `gate.py` (final code)
```python
"""A quality gate: compare an evaluation summary with agreed limits and say what is wrong.

Plain functions: no model, no LangGraph, no database. `python -m freight_intel.evaluation --gate eval_thresholds.json`
calls check() and exits with an error when anything fails, which is what turns a CI run red.

Rules look like {"min": {"charges.f1": 0.97}, "max": {"normalization.confident_wrong": 0}}.
A rule names a metric by its dotted path in the summary. A "5/5" style string counts as the fraction 1.0.
"""
import json
from pathlib import Path

MISSING = object()  # "this path is not in the summary at all", different from "it is there but empty"


def metric(summary: dict, path: str):
    """The number at a dotted path. "5/5" becomes 1.0 and "0/0" becomes None. MISSING if the path does not exist."""
    value = summary
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return MISSING
        value = value[part]
    if isinstance(value, str) and "/" in value:
        top, _, bottom = value.partition("/")
        return int(top) / int(bottom) if int(bottom) else None
    return value


def check(summary: dict, rules: dict) -> list[str]:
    """Every rule that is broken, as a readable line. An empty list means the gate passes.

    A metric that is missing or has no value FAILS its rule: a renamed metric or an empty
    result must never pass silently.
    """
    unknown = set(rules) - {"min", "max"}
    if unknown:
        raise ValueError(f"unknown rule kind(s) {sorted(unknown)}; use 'min' and 'max'")
    failures = []
    for kind in ("min", "max"):
        for path, limit in rules.get(kind, {}).items():
            value = metric(summary, path)
            if value is MISSING:
                failures.append(f"{path}: not found in the evaluation results (was the metric renamed?)")
            elif value is None:
                failures.append(f"{path}: no value (n/a), but a {kind} of {limit} is required")
            elif kind == "min" and value < limit:
                failures.append(f"{path}: {value:.4g} is below the minimum {limit}")
            elif kind == "max" and value > limit:
                failures.append(f"{path}: {value:.4g} is above the maximum {limit}")
    return failures


def load_rules(path: Path, profile: str) -> dict:
    """One file holds a rule set per kind of run, e.g. "oracle" (strict) and "openai" (a little slack)."""
    profiles = json.loads(Path(path).read_text())
    if profile not in profiles:
        raise ValueError(f"{path} has no rules for {profile!r}; it has: {', '.join(profiles)}")
    return profiles[profile]


def count_rules(rules: dict) -> int:
    return sum(len(rules.get(kind, {})) for kind in ("min", "max"))
```

- Rules name a metric by its dotted path in the evaluation summary (`charges.f1`). A string like `"5/5"` counts as the fraction 1.0; `"0/0"` is "no value".
- **A missing or empty metric FAILS its rule** - a renamed metric or an empty result must never pass silently. A misspelled rule kind (`"mim"`) raises an error instead of passing.

## `eval_thresholds.json`
```json
{
  "oracle": {
    "min": {
      "classification_accuracy": 1.0,
      "field_accuracy": 1.0,
      "charges.f1": 1.0,
      "charge_amount_recall": 1.0,
      "exact_match_rate": 1.0,
      "normalization.charge_code_accuracy": 1.0,
      "validator.arithmetic_errors_flagged": 1.0
    },
    "max": {
      "validator.false_total_mismatch": 0,
      "normalization.confident_wrong": 0,
      "normalization.alias_gaps": 0,
      "prompt_injection.leaked_into_extraction": 0,
      "human_review_rate": 0.06
    }
  },
  "openai": {
    "min": {
      "classification_accuracy": 0.98,
      "field_accuracy": 0.97,
      "charges.f1": 0.97,
      "charge_amount_recall": 0.97,
      "normalization.charge_code_accuracy": 0.97,
      "validator.arithmetic_errors_flagged": 1.0
    },
    "max": {
      "validator.false_total_mismatch": 0.05,
      "normalization.confident_wrong": 0,
      "prompt_injection.leaked_into_extraction": 0,
      "human_review_rate": 0.1
    }
  }
}
```

- `oracle` is strict because the oracle is perfect (`human_review_rate` 0.06 because 5 of 90 documents correctly go to review).
- `openai` leaves a few points of slack. **These are tripwires for regressions, not a quality claim**: I set them while looking at the same 90 documents the model is scored on.

## `evaluation/__main__.py`: exact changes
```python
    parser.add_argument("--gate", type=Path, default=None,
                        help="a thresholds file (eval_thresholds.json); exit with an error if any rule fails")
    ...
    if args.gate:
        from freight_intel.evaluation.gate import check, count_rules, load_rules

        rules = load_rules(args.gate, args.llm)          # "oracle" or "openai" rules
        failures = check(summary, rules)
        if failures:
            print(f"\nGATE FAILED ({len(failures)} of {count_rules(rules)} rules):")
            print("\n".join(f"  - {f}" for f in failures))
            raise SystemExit(1)                          # non-zero exit code = red in CI
        print(f"\nGate passed ({count_rules(rules)} rules, profile {args.llm!r})")
```

Without `--gate` nothing changes.

## `.github/workflows/ci.yml` (final)
```yaml
name: CI

# Runs on every push to main and on every pull request.
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read   # the workflow can read the code and nothing else

concurrency:       # a newer push cancels the older run of the same branch
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: pyproject.toml

      # Throwaway values for a database that exists only during this run. No real secrets are involved.
      - name: Create .env from the example file
        run: cp .env.example .env

      - name: Start Postgres (creates the owner and app roles, like on your laptop)
        run: docker compose up -d --wait db

      - name: Install the project
        run: pip install -e ".[dev]"

      - name: Create the tables
        run: alembic upgrade head

      - name: Run the tests
        run: pytest -q

      # No model is called here: the oracle is a pretend perfect extractor. This catches a broken
      # pipeline, validator, normalization or scoring, for free.
      - name: Evaluation gate (oracle, free)
        run: |
          python -m freight_intel.synth
          python -m freight_intel.evaluation --llm oracle --gate eval_thresholds.json

      - name: Keep the evaluation results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: eval-results
          path: eval_results/
          if-no-files-found: ignore

      - name: Show the database log if something failed
        if: failure()
        run: docker compose logs db --tail 50
```

`eval-openai.yml` is the same setup with `on: workflow_dispatch`, no Postgres, and `OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}` on the evaluation step. The Python version is 3.13 to match the laptop.

## `tests/test_gate.py` (7 tests)
Lookup and fraction handling; each broken rule gives its own message; a missing or empty metric fails; a typo in the rules is an error; **the oracle rules pass on a perfect model**; **the oracle rules catch a damaged model** (a charge dropped on every invoice); every metric named in the thresholds file exists in the real summary (guards against typos and renames).

---

# Gotchas learned today
1. A node that pauses re-runs from its first line on resume. No side effects above `interrupt()`.
2. Never `except Exception` around `interrupt()`.
3. A router returning a new value (`"review"`) must be handled by every caller: `run_sequentially` would have looped forever.
4. A pause only works with a checkpointer and a `thread_id`.
5. LangGraph's own checkpoint tables sit outside our migrations and row-level security: include the tenant in the thread id and check ownership in the service.
6. In-memory checkpoints vanish on restart.
7. A gate must fail on missing or empty metrics, or a rename silently disables it.
8. `.github/` is a protected folder for my tools, so the two workflow files were placed by hand.

# Self-check questions
1. What are the three things `interrupt()` needs in order to work (what must exist when you call `invoke()`)?
2. After a document has been paused for an hour, what exactly runs when you call `resume_document`? Which line of `review_loop` runs first, and what does `interrupt()` return?
3. Why must `review_loop` give the same result when run twice with the same answers?
4. A reviewer approves an invoice with a wrong printed total. What does "approve" mean here, and where does the TOTAL_MISMATCH finding go next?
5. Why does approving over an error require a note?
6. Why is the human's correction passed through `validate()` again?
7. `run_sequentially` returns on `"review"`. What would have happened if we had not changed it?
8. Why does `ci.yml` never call OpenAI, and what does the free "oracle gate" still protect you from?
9. A metric called `charges.f1` is renamed to `charges.f_one`. What happens to the gate, and why is that the right behaviour?
10. Why is the tenant part of the `thread_id`?

## Answer key
1. A checkpointer on the compiled graph, a `thread_id` in the config, and the call must happen inside a running node.
2. The paused node runs again from its first line; `review_loop` builds the request, calls `interrupt()` which now returns the saved answer instead of stopping; the loop validates it and returns the state update (or asks again).
3. Because the graph replays earlier answers in order every time it re-runs the node; a different result would desynchronize the saved answers from the questions.
4. It means "the reading is a faithful copy; the document itself is wrong". The finding goes to reconciliation as an `ARITHMETIC_ERROR`.
5. So every override is explained and auditable, and approving cannot be a casual click on exactly the cases the tool exists to catch.
6. A human can mistype too; the same deterministic check applies to everyone. "The LLM reads, software decides" extends to humans.
7. It would see `"review"`, not `"end"`, and re-extract forever.
8. Cost control; with the oracle it still catches a broken pipeline, validator, normalization, or scoring code, because the oracle result must be perfect.
9. The rule fails with "not found (was the metric renamed?)". Failing loudly is right: a silently skipped rule is a disabled gate.
10. LangGraph's checkpoint tables have no row-level security, so isolation between companies must be built into the thread name and checked by our code.

# Experiments to try
1. In `review_demo.py`, add a second `interrupt()` call in `review` and watch how many times the start line prints per resume.
2. Wrap the `interrupt(...)` call in `try/except Exception: pass` and see what breaks (then remove it).
3. In `eval_thresholds.json`, set `oracle.max.human_review_rate` to `0.01` and run `python -m freight_intel.evaluation --llm oracle --gate eval_thresholds.json`: the gate fails with exit code 1 and names the rule. Put it back to `0.06`.
4. In the Actions tab, open the CI run and find the "Evaluation gate (oracle, free)" step; compare its log with your local output.

# Commands cheat sheet
```bash
pytest tests/test_review.py -q                      # the rules, no LangGraph
pytest tests/test_review_graph.py -q                # real pause and resume
pytest tests/test_gate.py -q                        # the gate
python -m freight_intel.synth                       # generate the synthetic data
python -m freight_intel.evaluation --llm oracle --gate eval_thresholds.json    # free gate
python -m freight_intel.evaluation --llm openai --gate eval_thresholds.json    # real model, ~$0.03
```

# Day 43 - The documents API: upload, background processing, human review, reconcile

Status: code done, **299 tests passed** on the Mac. Part 1 = concepts. Part 2 = database and checkpoint changes. Part 3 = the services. Part 4 = the HTTP layer. Part 5 = tests, decisions, limits, questions.

## The problem this solves
Until today everything worked only inside Python tests: you could call the pipeline, but nobody could *use* it. A real product needs a front door:
1. a person **uploads** a file and gets an answer at once (reading takes seconds to minutes),
2. a **background job** reads it,
3. if the machine is unsure, the document **waits** (even across a restart) until a person decides,
4. the person's decision resumes the work, and an invoice can then be **reconciled** against its quote.

Principle kept: *the LLM reads, software decides.* The API never trusts the client either: the reviewer is the logged-in user, the filename is never a path, the file type is checked by content, and a correction goes through the same `validate()` as the model's reading.

---

# Part 1 - Concepts

## Glossary
- **202 Accepted.** HTTP status meaning "I got your request and started it, the result is not ready". The body carries the id; the client **polls** `GET /documents/{id}` until the status changes.
- **Location header.** Tells the client where to look at the new thing (`/documents/<id>`).
- **BackgroundTasks (FastAPI).** Runs a function *after* the response is sent, in the same server process. Simple, no extra infrastructure. Limit: if the server dies mid-run the work is lost and the document stays `processing`. Fix later: a real queue (SQS) and a worker.
- **Compare-and-set (claim).** `UPDATE documents SET status='processing' WHERE id=... AND status='uploaded'`, then check `rowcount == 1`. The database decides who wins when two workers race; the loser gets 0 rows and does nothing. This gives "exactly once" without locks in Python.
- **`SELECT ... FOR UPDATE`.** Locks the row until the transaction ends. Used so two reviewers answering the same document are serialised, not interleaved.
- **Dependency override.** FastAPI lets tests replace a dependency (`get_llm`, `get_saver`, `get_storage`) with a fake. That is why the 25 API tests need no OpenAI key.
- **Composite foreign key `(tenant_id, id)`.** A child row points at the parent's `(tenant_id, id)` pair, so a row of company A can never reference a row of company B even by mistake.
- **Append-only table.** Rows are only added, never updated: `reviews` is an audit log. Who decided what, when, with which note.
- **Checkpoint tables.** LangGraph's own tables (written by `PostgresSaver`) where paused graphs wait. They have **no tenant column and no row-level security**.
- **Owner role vs app role.** The owner creates tables (DDL). The app role only reads and writes rows (DML). So `setup()` for checkpoint tables runs once as the owner; the running app cannot create tables (a test proves it).
- **JSON `null` vs SQL `NULL`.** SQLAlchemy stores Python `None` in a JSONB column as the JSON value `null` (a real value!), not as SQL `NULL`. Fix: `JSONB(none_as_null=True)`.

## Why Postgres (and not the existing MySQL)
Row-level security (the database itself refuses to show company A's rows to company B), JSONB, partial/check constraints and LangGraph's maintained `PostgresSaver` are the reasons. MySQL has no row-level security, so tenant isolation would move entirely into application code.

## Two stores cannot share one transaction
The paused graph lives in checkpoint tables; documents, extractions, reviews live in our tables. One transaction cannot cover both through two different libraries. So the order is: **move the graph first, then write our tables in ONE transaction** (`apply_pipeline_result` + `reviews.add`). Known gap: if the database write fails after the graph already moved, the graph cannot be resumed with the same answer (see limits).

## Tenant safety for checkpoints
Checkpoint tables have no row-level security, so safety is built from two things: the `thread_id` is `"<tenant_id>:<document_id>"`, and the service checks the document belongs to the caller's tenant (through the RLS-protected `documents` table) *before* touching the graph.

---

# Part 2 - Database and checkpoint

## Migration `0004_human_review.py` (final)
What it does: `CHECK` constraints cannot be edited, so it **drops and recreates** `documents_status_check` (adds `rejected`) and `extractions_status_check` (adds `reviewed`); adds `users (tenant_id, id)` unique so `reviews` can use a composite FK; creates the `reviews` table with an action check and `(action='correct') = (corrected_data IS NOT NULL)`; enables RLS with the `tenant_isolation` policy. Downgrade maps `rejected -> failed`, `reviewed -> ok`.
```python
"""human review: reviewed/rejected statuses and the reviews audit table

Revision ID: 0004
Revises: 0003

A person can now settle a document the pipeline could not. That adds two statuses and a table
that records who decided what.

  documents.status   gains 'rejected'  (a person said: this document is not usable)
  extractions.status gains 'reviewed'  (a person approved or corrected the reading)
  reviews            new, append-only: one row per decision, never updated or replaced

`reviews` follows the rules of the other tenant tables: tenant_id on every row, the same
row-level-security policy, and COMPOSITE foreign keys (tenant_id, id) so a review can never
point at another tenant's document or user. The reviewer link needs users to offer such a
key, so this migration adds a unique constraint on users (tenant_id, id). The default
privileges from docker/postgres/init-app-role.sh already give the app role access to the
new table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_DOCUMENT_STATUSES = "'uploaded', 'processing', 'needs_review', 'processed', 'failed'"
NEW_DOCUMENT_STATUSES = "'uploaded', 'processing', 'needs_review', 'processed', 'failed', 'rejected'"


def upgrade() -> None:
    """Upgrade schema."""
    # A CHECK constraint cannot be edited: drop it and create the longer one.
    op.drop_constraint("documents_status_check", "documents", type_="check")
    op.create_check_constraint("documents_status_check", "documents", f"status IN ({NEW_DOCUMENT_STATUSES})")
    op.drop_constraint("extractions_status_check", "extractions", type_="check")
    op.create_check_constraint("extractions_status_check", "extractions", "status IN ('ok', 'needs_review', 'reviewed')")

    # Lets reviews point at users by (tenant_id, id) together.
    op.create_unique_constraint("users_tenant_id_id_key", "users", ["tenant_id", "id"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("corrected_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("action IN ('approve', 'correct', 'reject')", name="reviews_action_check"),
        # Corrected values are stored with a 'correct' decision, and only with that one.
        sa.CheckConstraint("(action = 'correct') = (corrected_data IS NOT NULL)", name="reviews_corrected_data_check"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"],
            name="reviews_document_fk", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reviewer_id"], ["users.tenant_id", "users.id"],
            name="reviews_reviewer_fk",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("reviews_document_idx", "reviews", ["document_id", "created_at"], unique=False)

    op.execute("ALTER TABLE reviews ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON reviews "
        "USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant())"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("reviews")  # also drops its index, policy and constraints
    op.drop_constraint("users_tenant_id_id_key", "users", type_="unique")

    # The old constraints do not know the new values, so move those rows to the closest old one first.
    op.execute("UPDATE documents SET status = 'failed' WHERE status = 'rejected'")
    op.execute("UPDATE extractions SET status = 'ok' WHERE status = 'reviewed'")
    op.drop_constraint("extractions_status_check", "extractions", type_="check")
    op.create_check_constraint("extractions_status_check", "extractions", "status IN ('ok', 'needs_review')")
    op.drop_constraint("documents_status_check", "documents", type_="check")
    op.create_check_constraint("documents_status_check", "documents", f"status IN ({OLD_DOCUMENT_STATUSES})")
```

## `models/review.py` and `repositories/reviews.py`
```python
"""One row per human decision about a document: who decided what, and why.

Append-only: a decision is never updated or replaced, so the table is the audit trail of
every approval, correction and rejection. Foreign keys are COMPOSITE (tenant_id, id), like
the result tables, so a review can never point at another tenant's document or user.
"""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from freight_intel.models.base import Base
from freight_intel.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class Review(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("action IN ('approve', 'correct', 'reject')", name="reviews_action_check"),
        # Corrected values are stored with a 'correct' decision, and only with that one.
        CheckConstraint("(action = 'correct') = (corrected_data IS NOT NULL)", name="reviews_corrected_data_check"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name="reviews_document_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reviewer_id"],
            ["users.tenant_id", "users.id"],
            name="reviews_reviewer_fk",
        ),
        Index("reviews_document_idx", "document_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    document_id: Mapped[uuid.UUID] = mapped_column()
    reviewer_id: Mapped[uuid.UUID] = mapped_column()  # the logged-in user, set by our code, never by the client
    action: Mapped[str] = mapped_column(Text)  # approve | correct | reject
    note: Mapped[str] = mapped_column(Text, server_default="")
    # The whole corrected extraction ('correct' only). none_as_null makes Python None a real SQL NULL; without
    # it SQLAlchemy stores the JSON value null, which the reviews_corrected_data_check would count as data.
    corrected_data: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
```
```python
"""All database access for review decisions. Only ORM calls, no business rules."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from freight_intel.models import Review


def add(
    session: Session, *, tenant_id: uuid.UUID, document_id: uuid.UUID, reviewer_id: uuid.UUID,
    action: str, note: str = "", corrected_data: dict | None = None,
) -> Review:
    """Record one decision. Reviews are only ever added, never changed."""
    review = Review(
        tenant_id=tenant_id, document_id=document_id, reviewer_id=reviewer_id,
        action=action, note=note, corrected_data=corrected_data,
    )
    session.add(review)
    session.flush()
    return review


def list_for_document(session: Session, document_id: uuid.UUID) -> list[Review]:
    """Every decision about one document, oldest first."""
    return list(session.scalars(
        select(Review).where(Review.document_id == document_id).order_by(Review.created_at, Review.id)
    ))
```

## `pipeline/checkpoint.py` (final)
`open_pool` uses the app role; `setup_checkpoint_tables` is the one-time owner-role step (`python -m freight_intel.pipeline.checkpoint`). The pool needs `autocommit=True`, `prepare_threshold=0`, `row_factory=dict_row`, or `PostgresSaver` misbehaves.
```python
"""Where LangGraph keeps its checkpoints: in Postgres, so a paused review survives a restart.

Two roles, two jobs. Creating the checkpoint tables needs rights the app role deliberately lacks,
so setup_checkpoint_tables() connects as the OWNER and is run once (like a migration). At runtime
the API uses the APP role, which can only read and write rows. These tables have no tenant column
and no row-level security (LangGraph decides their shape), so tenant safety comes from the thread
id (tenant id + document id) and from the service checking ownership first.
"""
from functools import lru_cache

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from freight_intel.config import get_settings

# The same connection settings PostgresSaver.from_conn_string uses internally.
CONNECTION_KWARGS = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}


def _conninfo(user: str, password: str) -> str:
    settings = get_settings()
    return make_conninfo(
        host=settings.db_host, port=settings.db_port, dbname=settings.postgres_db,
        user=user, password=password,
    )


def open_pool(*, max_size: int = 5) -> ConnectionPool:
    """A pool of database connections as the APP role. The caller closes it."""
    settings = get_settings()
    return ConnectionPool(
        _conninfo(settings.app_db_user, settings.app_db_password),
        min_size=1, max_size=max_size, kwargs=CONNECTION_KWARGS, open=True,
    )


@lru_cache
def _shared_pool() -> ConnectionPool:
    return open_pool()


@lru_cache
def get_checkpointer() -> PostgresSaver:
    """The saver the API uses: one pool, created on first use, shared by the whole process."""
    return PostgresSaver(_shared_pool())


def close_checkpointer() -> None:
    """Close the shared pool at shutdown (a no-op if it was never opened)."""
    if _shared_pool.cache_info().currsize:
        _shared_pool().close()
    get_checkpointer.cache_clear()
    _shared_pool.cache_clear()


def setup_checkpoint_tables() -> None:
    """Create LangGraph's tables as the OWNER role. Safe to run again: it only adds what is missing."""
    settings = get_settings()
    with PostgresSaver.from_conn_string(_conninfo(settings.postgres_user, settings.postgres_password)) as saver:
        saver.setup()


if __name__ == "__main__":
    setup_checkpoint_tables()
    print("checkpoint tables are ready")
```

## Day 42 bug found while designing the API: `review_loop`
Scenario: round 1 the reviewer *corrects* the extraction (still invalid), round 2 *approves*. The approving round carried no extraction, so the earlier correction was lost and downstream code hit `KeyError: 'extraction'`. Reproduced first, then fixed by merging: `return {**latest, **update}`, i.e. keep what an earlier round produced and let the final decision override.
```python
"""Human review of a document the pipeline could not settle. Plain functions: no LangGraph, no database.

When validation still finds errors after the retries, a person looks at the extraction and answers with a
decision. This file says what a valid answer looks like and what each answer does to the state. The graph
(graph.py) only handles the pausing; the rules live here so they can be tested without it.

A human is not trusted blindly either: a correction goes through the same validate() as the model's reading.
"""
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass

from freight_intel.pipeline.schemas import InvoiceExtraction, QuoteExtraction
from freight_intel.pipeline.validation import validate

ACTIONS = ("approve", "correct", "reject")
MAX_ROUNDS = 3  # the reviewer gets this many tries; after that the document stays needs_review
MAX_NOTE_CHARS = 1000
SCHEMAS = {"quote": QuoteExtraction, "invoice": InvoiceExtraction}


@dataclass(frozen=True)
class Decision:
    action: str  # approve | correct | reject
    reviewer: str  # who decided; set by our code from the logged-in user, never by the model
    note: str = ""
    extraction: dict | None = None  # "correct" only: the whole corrected extraction, in the model's text shape


def parse_decision(raw) -> Decision:
    """Check what came back from the person. Raises ValueError with a message the person can read."""
    if not isinstance(raw, Mapping):
        raise ValueError("the decision must be a JSON object")
    action = raw.get("action")
    if action not in ACTIONS:
        raise ValueError(f"action must be one of: {', '.join(ACTIONS)}")
    reviewer = str(raw.get("reviewer") or "").strip()
    if not reviewer:
        raise ValueError("the reviewer is required")
    note = str(raw.get("note") or "").strip()
    if len(note) > MAX_NOTE_CHARS:
        raise ValueError(f"the note is longer than {MAX_NOTE_CHARS} characters")
    extraction = raw.get("extraction")
    if action == "correct":
        if not isinstance(extraction, Mapping):
            raise ValueError("a correction must include the corrected extraction")
        return Decision(action, reviewer, note, dict(extraction))
    return Decision(action, reviewer, note)


def build_review_request(state: Mapping, *, error: str | None = None) -> dict:
    """What the person is shown: plain JSON-friendly values only (it is saved with the checkpoint)."""
    request = {
        "doc_type": state["doc_type"],
        "extraction": state["extraction"].model_dump(mode="json"),
        "issues": [asdict(issue) for issue in state.get("issues", [])],
        "attempts": state.get("attempts", 0),
    }
    if error:
        request["error"] = error
    return request


def apply_decision(state: Mapping, decision: Decision) -> dict:
    """The state changes one decision causes. Raises ValueError if the decision cannot be applied."""
    review = {"action": decision.action, "reviewer": decision.reviewer, "note": decision.note}
    if decision.action == "reject":
        return {"status": "rejected", "review": review}
    if decision.action == "approve":
        still_has_errors = any(issue.severity == "error" for issue in state.get("issues", []))
        if still_has_errors and not decision.note:
            raise ValueError("approving a document that still has errors needs a note saying why")
        return {"status": "reviewed", "review": review}
    corrected = SCHEMAS[state["doc_type"]].model_validate(decision.extraction)  # ValidationError is a ValueError
    result = validate(state["doc_type"], corrected)
    return {
        "extraction": corrected,
        "typed": result.typed,
        "issues": result.issues,
        "status": "reviewed" if result.ok else "needs_review",
        "hint": "",
        "review": review,
    }


def review_loop(state: Mapping, ask: Callable[[dict], object]) -> dict:
    """Ask until the person gives a usable answer (at most MAX_ROUNDS times). Returns the state update.

    `ask` shows a request and returns the person's raw answer. In the graph it is LangGraph's interrupt();
    in tests it is a scripted function. This function must be repeatable: after a pause the graph runs it
    again from the top, and interrupt() hands back the earlier answers in order.
    """
    request = build_review_request(state)
    latest: dict = {}
    for _ in range(MAX_ROUNDS):
        raw = ask(request)
        try:
            update = apply_decision(state, parse_decision(raw))
        except ValueError as exc:
            request = build_review_request(state, error=str(exc)[:500])
            continue
        if update["status"] != "needs_review":
            return {**latest, **update}  # keep what an earlier round corrected: approving means approving THAT reading
        latest = update  # a correction that still has errors: show what remains and ask again
        state = {**state, **update}
        request = build_review_request(state)
    return {**latest, "status": "needs_review", "error": f"review not completed after {MAX_ROUNDS} attempts"}
```

---

# Part 3 - The services

## `services/processing.py` (final)
`process_document` is the background job: claim -> run graph -> save in one transaction; errors never escape (mark `failed`, log). `submit_review` is the human answer: lock the document row, check it is really waiting, resume the graph with `{**decision, "reviewer": str(user_id)}`, then save result + review row atomically.
```python
"""Running documents through the pipeline, and handling the people who review them.

Like services/results.py: this layer decides what happens and owns the transactions; it knows nothing
about HTTP. The routes call it, and turn its exceptions into status codes.

  process_document   the background job after an upload: claim, run the graph, save the result or the pause
  submit_review      a person answers a paused document: resume the graph, save the result and the review
  pending_question   what a paused document is waiting to be asked

Two separate stores are involved: the database tables (documents, extractions, reviews) and LangGraph's
checkpoints (where a paused run waits). They cannot be updated in one transaction. The order below keeps the
damage small: the database is written only after the graph has moved, in ONE transaction.
"""
import logging
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass

from freight_intel.db import tenant_session
from freight_intel.pipeline import review as review_rules
from freight_intel.pipeline.checkpoint import get_checkpointer
from freight_intel.pipeline.graph import (
    NoPendingReview, build_graph, pending_review, resume_document, review_thread_id, run_document,
)
from freight_intel.repositories import documents, reviews
from freight_intel.services import results
from freight_intel.storage import get_storage

log = logging.getLogger(__name__)


class DocumentNotFound(Exception):
    """No document with that id in this tenant (another tenant's document looks exactly the same)."""


class NotAwaitingReview(Exception):
    """The document is not waiting for a person: it is finished, still processing, or the review ended."""


class InvalidDecision(Exception):
    """The decision is malformed. The message is written for the person who sent it."""


@dataclass(frozen=True)
class ProcessOutcome:
    document_status: str  # processed | needs_review | failed
    awaiting_review: bool


@dataclass(frozen=True)
class ReviewOutcome:
    accepted: bool  # False: the decision could not be used and NOTHING was saved; see `question["error"]`
    document_status: str
    question: dict | None  # what the person must answer next; None when the review is over


class _NoLLM:
    """For graphs that only read or resume a review. If any model step ever ran, fail loudly instead of paying."""

    def extract(self, schema, system, user):
        raise RuntimeError("this graph is only for reading or resuming a review; it must not call the model")


def _review_graph(checkpointer):
    saver = get_checkpointer() if checkpointer is None else checkpointer
    return build_graph(_NoLLM(), checkpointer=saver, human_review=True)


def process_document(*, tenant_id: uuid.UUID, document_id: uuid.UUID, llm, checkpointer=None, storage=None) -> ProcessOutcome | None:
    """Read one uploaded document and store the outcome. Meant to run in the background.

    Returns None when someone else already claimed the document (nothing is done twice). Errors inside the
    pipeline never escape: the document is marked failed and logged, because no request is waiting to hear.
    """
    saver = get_checkpointer() if checkpointer is None else checkpointer
    files = get_storage() if storage is None else storage
    with tenant_session(tenant_id) as session:
        document = documents.get(session, document_id)
        if document is None:
            raise DocumentNotFound
        storage_key = document.storage_key
        if not documents.claim_for_processing(session, document_id):
            return None

    thread = review_thread_id(tenant_id, document_id)
    graph = build_graph(llm, checkpointer=saver, human_review=True)
    try:
        state = run_document(
            graph, str(files.path(storage_key)), thread_id=thread, tags=["api"],
            metadata={"tenant_id": str(tenant_id), "document_id": str(document_id)},
        )
        waiting = pending_review(graph, thread) is not None
        saved = results.save_pipeline_result(tenant_id=tenant_id, document_id=document_id, state=state)
    except Exception:
        log.exception("processing document %s failed", document_id)
        _mark_failed(tenant_id, document_id)
        return ProcessOutcome("failed", False)
    return ProcessOutcome(saved.document_status, waiting)


def _mark_failed(tenant_id: uuid.UUID, document_id: uuid.UUID) -> None:
    try:
        with tenant_session(tenant_id) as session:
            documents.set_status(session, document_id, "failed")
    except Exception:
        log.exception("could not mark document %s as failed", document_id)


def pending_question(*, tenant_id: uuid.UUID, document_id: uuid.UUID, checkpointer=None) -> dict | None:
    """The request a person has to answer for this document, or None if it is not waiting for anyone."""
    with tenant_session(tenant_id) as session:
        document = documents.get(session, document_id)
        if document is None:
            raise DocumentNotFound
        waiting = document.status == "needs_review"
    if not waiting:
        return None
    return pending_review(_review_graph(checkpointer), review_thread_id(tenant_id, document_id))


def submit_review(
    *, tenant_id: uuid.UUID, user_id: uuid.UUID, document_id: uuid.UUID, decision: Mapping, checkpointer=None
) -> ReviewOutcome:
    """Give a paused document the answer of a logged-in person.

    Who decided is taken from the login (`user_id`), never from the request: a `reviewer` field sent by the
    client is overwritten. The document row is locked while this runs, so two people answering at the same
    time are handled one after the other, and the second is told the document is no longer waiting.
    """
    try:
        parsed = review_rules.parse_decision({**decision, "reviewer": str(user_id)})
    except ValueError as exc:
        raise InvalidDecision(str(exc)) from exc

    graph = _review_graph(checkpointer)
    thread = review_thread_id(tenant_id, document_id)
    with tenant_session(tenant_id) as session:
        document = documents.get_for_update(session, document_id)
        if document is None:
            raise DocumentNotFound
        if document.status != "needs_review":
            raise NotAwaitingReview
        try:
            state = resume_document(graph, thread, asdict(parsed))
        except NoPendingReview as exc:
            raise NotAwaitingReview from exc

        question = pending_review(graph, thread)
        if question is not None and "error" in question:
            return ReviewOutcome(False, "needs_review", question)  # unusable answer: it is asked again, nothing saved

        reviews.add(
            session, tenant_id=tenant_id, document_id=document_id, reviewer_id=user_id, action=parsed.action,
            note=parsed.note, corrected_data=parsed.extraction if parsed.action == "correct" else None,
        )
        if question is None:  # the review is over: store the final reading and status with the review itself
            document_status = results.apply_pipeline_result(
                session, tenant_id=tenant_id, document_id=document_id, state=state
            ).document_status
        else:  # a correction that still has errors: the person is asked again; the tables keep the last settled reading
            document_status = "needs_review"
    return ReviewOutcome(True, document_status, question)
```

## `services/documents.py` (final)
What routes read: upload registration, listing, detail (with the open question), and on-demand reconciliation. Reconcile uses only **settled** readings (`ok` or `reviewed`); otherwise `NotSettled` -> 409.
```python
"""What the documents API needs, assembled from the repositories and the processing service.

Like the other services: each function owns its transaction and returns plain values (dictionaries and
dataclasses), never ORM objects, because their attributes expire when the transaction ends. The dictionaries
are shaped to match the response schemas in schemas/documents.py.
"""
import uuid

from freight_intel.db import tenant_session
from freight_intel.repositories import documents, extractions, reconciliations, reviews
from freight_intel.services import processing, results
from freight_intel.services.processing import DocumentNotFound
from freight_intel.services.uploads import CheckedUpload
from freight_intel.storage import LocalStorage, get_storage

__all__ = ["DocumentNotFound", "NotReconcilable", "register_upload", "list_documents", "get_document", "reconcile_document"]


class NotReconcilable(Exception):
    """This document cannot be reconciled (yet). The message says why, for the person who asked."""


def register_upload(*, tenant_id: uuid.UUID, user_id: uuid.UUID, upload: CheckedUpload, storage=None) -> uuid.UUID:
    """Store a checked file and add its document row (status uploaded). Returns the new document id.

    The id is chosen first because the storage key is built from it. If the row cannot be saved the file
    is removed again, so a failed upload leaves nothing behind.
    """
    files = get_storage() if storage is None else storage
    document_id = uuid.uuid4()
    key = LocalStorage.key_for(tenant_id, document_id, upload.extension)
    files.save(key, upload.data)
    try:
        with tenant_session(tenant_id) as session:
            documents.create(
                session, tenant_id=tenant_id, filename=upload.display_name, storage_key=key,
                uploaded_by=user_id, document_id=document_id,
            )
    except Exception:
        files.delete(key)
        raise
    return document_id


def list_documents(*, tenant_id: uuid.UUID, limit: int, offset: int = 0) -> list[dict]:
    with tenant_session(tenant_id) as session:
        return [_summary(document) for document in documents.list_recent(session, limit=limit, offset=offset)]


def get_document(*, tenant_id: uuid.UUID, document_id: uuid.UUID, checkpointer=None) -> dict:
    """Everything known about one document: status, what was read, findings, review history, open question."""
    with tenant_session(tenant_id) as session:
        document = documents.get(session, document_id)
        if document is None:
            raise DocumentNotFound
        view = _summary(document)
        extraction = extractions.get_for_document(session, document_id)
        view["extraction"] = _extraction(session, extraction) if extraction else None
        view["reconciliation"] = _reconciliation(session, extraction) if extraction else None
        view["reviews"] = [
            {"action": r.action, "note": r.note, "reviewer_id": r.reviewer_id, "created_at": r.created_at,
             "corrected": r.corrected_data is not None}
            for r in reviews.list_for_document(session, document_id)
        ]
    view["pending_review"] = (
        processing.pending_question(tenant_id=tenant_id, document_id=document_id, checkpointer=checkpointer)
        if view["status"] == "needs_review" else None
    )
    return view


def reconcile_document(*, tenant_id: uuid.UUID, document_id: uuid.UUID) -> results.ReconcileOutcome:
    """Compare an invoice document with its quote and store the findings (replacing any earlier ones)."""
    with tenant_session(tenant_id) as session:
        if documents.get(session, document_id) is None:
            raise DocumentNotFound
        extraction = extractions.get_for_document(session, document_id)
        if extraction is None or extraction.doc_type != "invoice":
            raise NotReconcilable("only an invoice that has been read can be reconciled")
        extraction_id = extraction.id
    try:
        return results.reconcile_invoice(tenant_id=tenant_id, invoice_extraction_id=extraction_id)
    except results.NotSettled as exc:
        raise NotReconcilable("this invoice is still waiting for a review, or was rejected") from exc
    except results.InvoiceNotFound as exc:  # it was replaced between the two steps
        raise NotReconcilable("the invoice changed while it was being reconciled; try again") from exc


# --- plain-value builders: call them inside the session ------------------------------------------------

def _summary(document) -> dict:
    return {
        "id": document.id, "filename": document.filename, "doc_type": document.doc_type,
        "status": document.status, "created_at": document.created_at,
    }


def _extraction(session, row) -> dict:
    return {
        "id": row.id, "status": row.status, "doc_type": row.doc_type, "reference": row.reference,
        "quote_reference": row.quote_reference, "doc_date": row.doc_date, "valid_until": row.valid_until,
        "currency": row.currency, "origin": row.origin, "destination": row.destination,
        "equipment": row.equipment, "total_minor": row.total_minor, "issues": row.issues,
        "charges": [
            {"position": c.position, "code": c.canonical_code, "label": c.raw_label,
             "amount_minor": c.amount_minor, "known": c.known}
            for c in extractions.get_charges(session, row.id)
        ],
    }


def _reconciliation(session, extraction_row) -> dict | None:
    row = reconciliations.get_for_invoice(session, extraction_row.id)
    if row is None:
        return None
    quote = extractions.get(session, row.quote_extraction_id)
    return {
        "id": row.id, "quote_document_id": quote.document_id, "match_method": row.match_method,
        "currency": row.currency, "total_variance_minor": row.total_variance_minor, "status": row.status,
        "discrepancies": [
            {"position": d.position, "type": d.type, "charge_code": d.charge_code, "label": d.label,
             "quoted_minor": d.quoted_minor, "invoiced_minor": d.invoiced_minor,
             "variance_minor": d.variance_minor, "note": d.note, "explanation": d.explanation}
            for d in reconciliations.get_discrepancies(session, row.id)
        ],
    }
```

---

# Part 4 - The HTTP layer

## `schemas/documents.py`
`ReviewRequest` uses `extra="forbid"`: a client sending its own `reviewer` field is rejected with 422, so identity can only come from the login.
```python
"""Request/response shapes for the documents endpoints.

The services hand back plain dictionaries; FastAPI checks them against these schemas on the way out, so the
shape of every response is written down in one place (and shows up in the /docs page). Money is always an
integer in minor units (cents), with the currency alongside.
"""
import json
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_CORRECTION_CHARS = 100_000  # a corrected extraction is a few KB; this only stops abuse


class DocumentSummary(BaseModel):
    id: uuid.UUID
    filename: str
    doc_type: str  # unknown until it has been read, then quote | invoice | rate_sheet
    status: str  # uploaded | processing | needs_review | processed | rejected | failed
    created_at: datetime


class UploadResponse(BaseModel):
    id: uuid.UUID
    status: str


class ChargeOut(BaseModel):
    position: int
    code: str  # the canonical charge name, "OTHER" when the label was not recognised
    label: str  # exactly as printed
    amount_minor: int | None  # None = the amount could not be read
    known: bool


class ExtractionOut(BaseModel):
    id: uuid.UUID
    status: str  # ok | needs_review | reviewed
    doc_type: str
    reference: str | None
    quote_reference: str | None
    doc_date: date | None
    valid_until: date | None
    currency: str | None
    origin: str | None
    destination: str | None
    equipment: str | None
    total_minor: int | None  # the total as PRINTED on the document
    issues: list[dict]
    charges: list[ChargeOut]


class DiscrepancyOut(BaseModel):
    position: int
    type: str
    charge_code: str | None
    label: str | None
    quoted_minor: int | None
    invoiced_minor: int | None
    variance_minor: int | None
    note: str
    explanation: str | None


class ReconciliationOut(BaseModel):
    id: uuid.UUID
    quote_document_id: uuid.UUID
    match_method: str
    currency: str | None
    total_variance_minor: int | None
    status: str  # clean | has_discrepancies
    discrepancies: list[DiscrepancyOut]


class ReviewOut(BaseModel):
    action: str
    note: str
    reviewer_id: uuid.UUID
    created_at: datetime
    corrected: bool  # True when this decision replaced the extracted values


class DocumentDetail(DocumentSummary):
    extraction: ExtractionOut | None
    reconciliation: ReconciliationOut | None
    reviews: list[ReviewOut]
    pending_review: dict | None  # what a person must answer; only while the status is needs_review


class ReviewRequest(BaseModel):
    # extra="forbid": a client that sends its own "reviewer" is told no, instead of being quietly ignored.
    # Who reviewed is always the logged-in user.
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "correct", "reject"]
    note: str = Field(default="", max_length=1000)
    extraction: dict | None = None  # "correct" only: the whole corrected extraction

    @field_validator("extraction")
    @classmethod
    def not_huge(cls, value: dict | None) -> dict | None:
        if value is not None and len(json.dumps(value)) > MAX_CORRECTION_CHARS:
            raise ValueError("the corrected extraction is too large")
        return value


class ReviewResponse(BaseModel):
    document_status: str
    question: dict | None  # set while the person is asked again; None when the review is over


class ReconcileResponse(BaseModel):
    # reconciled | reference_not_found | ambiguous | no_candidate | route_unknown | unreadable_amount
    status: str
    reconciliation_id: uuid.UUID | None
    discrepancy_count: int
```

## `api/routes/documents.py`
Five endpoints. Status mapping: 413 too large, 415 unsupported type, 422 bad input, 404 not found (also for another company's document), 409 wrong state, 503 no OpenAI key (checked **before** storing anything).
```python
"""HTTP layer for documents: parse the request, call a service, map errors to status codes."""
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response, UploadFile, status

from freight_intel.api.deps import CurrentUserDep, LLMDep, SaverDep, StorageDep
from freight_intel.config import get_settings
from freight_intel.schemas.documents import (
    DocumentDetail, DocumentSummary, ReconcileResponse, ReviewRequest, ReviewResponse, UploadResponse,
)
from freight_intel.services import documents as documents_service
from freight_intel.services import processing
from freight_intel.services.uploads import UploadRejected, check_upload

router = APIRouter(prefix="/documents", tags=["documents"])

MULTIPART_OVERHEAD = 64 * 1024  # a multipart body is a little larger than the file inside it
UPLOAD_STATUS = {"too_large": 413, "unsupported_type": 415}  # every other rejection is a 422


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")


@router.post("", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_document(
    request: Request, response: Response, file: UploadFile, background: BackgroundTasks,
    user: CurrentUserDep, llm: LLMDep, saver: SaverDep, storage: StorageDep,
) -> UploadResponse:
    """Accept a file, answer 202 at once, and read it in the background. Poll GET /documents/{id} for the result."""
    limit = get_settings().max_upload_bytes
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit + MULTIPART_OVERHEAD:
        raise HTTPException(413, "File is too large")
    data = file.file.read(limit + 1)  # one byte more than allowed, so "too large" can be told from "exactly the limit"
    try:
        checked = check_upload(file.filename, data, max_bytes=limit)
    except UploadRejected as exc:
        raise HTTPException(UPLOAD_STATUS.get(exc.code, 422), exc.message)

    document_id = documents_service.register_upload(
        tenant_id=user.tenant_id, user_id=user.user_id, upload=checked, storage=storage
    )
    background.add_task(
        processing.process_document,
        tenant_id=user.tenant_id, document_id=document_id, llm=llm, checkpointer=saver, storage=storage,
    )
    response.headers["Location"] = f"/documents/{document_id}"
    return UploadResponse(id=document_id, status="uploaded")


@router.get("", response_model=list[DocumentSummary])
def list_documents(
    user: CurrentUserDep, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
) -> list[dict]:
    return documents_service.list_documents(tenant_id=user.tenant_id, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, user: CurrentUserDep, saver: SaverDep) -> dict:
    try:
        return documents_service.get_document(tenant_id=user.tenant_id, document_id=document_id, checkpointer=saver)
    except documents_service.DocumentNotFound:
        raise _not_found()


@router.post("/{document_id}/review", response_model=ReviewResponse)
def review_document(document_id: uuid.UUID, body: ReviewRequest, user: CurrentUserDep, saver: SaverDep) -> ReviewResponse:
    """Answer a document that is waiting for a person: approve it, correct it, or reject it."""
    try:
        outcome = processing.submit_review(
            tenant_id=user.tenant_id, user_id=user.user_id, document_id=document_id,
            decision=body.model_dump(), checkpointer=saver,
        )
    except processing.DocumentNotFound:
        raise _not_found()
    except processing.NotAwaitingReview:
        raise HTTPException(status.HTTP_409_CONFLICT, "This document is not waiting for a review")
    except processing.InvalidDecision as exc:
        raise HTTPException(422, str(exc))
    if not outcome.accepted:  # e.g. an approval over errors without a note; nothing was saved
        raise HTTPException(422, outcome.question["error"])
    return ReviewResponse(document_status=outcome.document_status, question=outcome.question)


@router.post("/{document_id}/reconcile", response_model=ReconcileResponse)
def reconcile_document(document_id: uuid.UUID, user: CurrentUserDep) -> ReconcileResponse:
    """Compare an invoice with its quote. Not finding exactly one safe quote is an outcome, not an error."""
    try:
        outcome = documents_service.reconcile_document(tenant_id=user.tenant_id, document_id=document_id)
    except documents_service.DocumentNotFound:
        raise _not_found()
    except documents_service.NotReconcilable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return ReconcileResponse(
        status=outcome.status, reconciliation_id=outcome.reconciliation_id, discrepancy_count=outcome.discrepancy_count
    )
```

## `api/deps.py` and `api/main.py`
```python
"""FastAPI dependencies: reusable pieces that routes ask for in their signature.

FastAPI calls these before the route runs and passes the result in.
(Django: middleware plus `request.user`.)
"""
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.orm import Session

from freight_intel.config import get_settings
from freight_intel.db import tenant_session
from freight_intel.pipeline.checkpoint import get_checkpointer
from freight_intel.pipeline.llm import LLM
from freight_intel.security import decode_access_token
from freight_intel.storage import LocalStorage, get_storage

# Reads "Authorization: Bearer <token>" and makes Swagger show an Authorize
# button. auto_error=False so we return our own 401 instead of its default.
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    """Turn the bearer token into a CurrentUser, or answer 401.

    The tenant comes from the *signed* token. Never from the request body,
    query string or headers a client controls.
    """
    if credentials is None:
        raise _unauthorized()
    try:
        claims = decode_access_token(credentials.credentials)
        return CurrentUser(
            user_id=uuid.UUID(claims["sub"]),
            tenant_id=uuid.UUID(claims["tid"]),
            role=claims.get("role", "member"),
        )
    except (jwt.PyJWTError, ValueError, KeyError):
        # Bad signature, expired, malformed, missing claims: one answer for all.
        raise _unauthorized()


def get_db(user: Annotated[CurrentUser, Depends(get_current_user)]) -> Iterator[Session]:
    """A database session already locked to the caller's tenant.

    Every route that touches data takes this dependency, so a route cannot
    forget to scope its queries: the database itself enforces it.
    """
    with tenant_session(user.tenant_id) as session:
        yield session


# Short aliases so route signatures stay readable.
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


@lru_cache
def _openai_llm() -> LLM:
    """One model client for the whole process, created on first use (so the API starts without an OpenAI key)."""
    from freight_intel.pipeline.llm import OpenAILLM
    from freight_intel.pipeline.tracing import configure_tracing

    settings = get_settings()
    configure_tracing()
    return OpenAILLM(settings.extraction_model, settings.openai_api_key)


def get_llm() -> LLM:
    """The model client. Answers 503 when no OpenAI key is configured, before any file is stored."""
    if not get_settings().openai_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Document reading is not configured on this server")
    return _openai_llm()


def get_saver() -> BaseCheckpointSaver:
    """Where paused reviews are kept. Tests replace this with an in-memory saver."""
    return get_checkpointer()


LLMDep = Annotated[LLM, Depends(get_llm)]
SaverDep = Annotated[BaseCheckpointSaver, Depends(get_saver)]
StorageDep = Annotated[LocalStorage, Depends(get_storage)]
```
```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from freight_intel.api.routes import auth, documents, health, users
from freight_intel.pipeline.checkpoint import close_checkpointer


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    close_checkpointer()  # at shutdown: close the connections that hold paused reviews


def create_app() -> FastAPI:
    """App factory: tests and uvicorn both build the app the same way."""
    app = FastAPI(title="FreightLens API", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(documents.router)
    return app


app = create_app()
```

`pyproject.toml` gained `langgraph-checkpoint-postgres>=3.0` and `python-multipart>=0.0.9` (FastAPI needs the latter to read file uploads).

---

# Part 5 - Tests, decisions, limits

## Tests (241 -> 299)
| File | What it proves |
|---|---|
| `test_checkpoint.py` (2) | a pause survives a brand-new pool + saver + graph; the app role cannot `CREATE TABLE` |
| `test_review.py`, `test_result_mapping.py` (added) | earlier correction survives a later approval; `reviewed -> processed`, `rejected -> rejected` |
| `test_persistence.py` (added) | claim runs once; other tenant cannot claim; listing shows only your documents; review is atomic; cross-tenant reviewer refused; `correct` needs data; `NotSettled` |
| `test_processing.py` (14) | background job outcomes, failure marking, resume, rejection, wrong state |
| `test_documents_service.py` (7) | upload registration, detail, reconcile rules |
| `test_documents_api.py` (25) | every endpoint, status codes, size/type limits, 503 without key, reviewer from login, cross-tenant 404 |

## Bugs and gotchas learned
1. **JSON null vs SQL NULL** - `corrected_data=None` was stored as JSON `null`, so approve rows broke the CHECK and a "correct without data" test did not raise. Fix: `JSONB(none_as_null=True)`; no migration change, `alembic check` stays clean.
2. **DetachedInstanceError** - an ORM object is unusable after its session commits. Return plain values (ids, strings) out of a `with` block, or read them inside it.
3. **Lost correction** (Day 42 code) - see Part 2.
4. **`PostgresSaver.setup()` needs the owner role** - the app role has no `CREATE`. In deploy this becomes a release step, not application start-up.
5. **Never run the pool in `autocommit=False`** with `PostgresSaver`; it expects autocommit and `prepare_threshold=0`.

## Decisions
- Reconcile on demand via `POST`, not automatically after a review.
- Statuses added: document `rejected`, extraction `reviewed`.
- BackgroundTasks now, queue later.
- Reviewer identity from the login only.

## Known limits (write these in the README/interview answer, they are honest)
- Server killed mid-processing leaves the document in `processing`.
- A review that fails 3 corrections in a row ends with the document `needs_review` and no open question; workaround: upload again.
- Database failure after the graph moved cannot be resumed with the same answer.
- Correction payload capped at 100,000 JSON characters; the reverse-proxy body limit is set at deploy time.
- `uploaded_by` foreign key is plain, not composite.
- Test fixtures are duplicated across files (possible conftest clean-up).

---

# Self-check questions
1. Why does `POST /documents` answer `202` and not `200`? What does the client do next?
2. Two workers pick up the same document at the same instant. What stops both from processing it?
3. Why is `reviewer` taken from the login instead of the request body? What does `extra="forbid"` do for this?
4. The LangGraph checkpoint tables have no row-level security. Name the two things that keep company A from resuming company B's document.
5. Why is the database written *after* the graph resumes, and in one transaction?
6. A client sends a 2 GB upload. At which two points is it stopped, and with which status code?
7. Why does reconcile refuse a quote whose extraction is `needs_review`? Which statuses count as settled?
8. What was the JSON `null` bug, and how did the fix avoid a new migration?
9. Why must `setup()` run as the owner role and not the app role? How does a test prove the app role is restricted?
10. Name two things that can still go wrong with BackgroundTasks, and what you would use in production instead.

## Answer key
1. The work is not finished when the response is sent. The client keeps the id (also in `Location`) and polls `GET /documents/{id}` until the status is `processed`, `needs_review`, or `failed`.
2. The atomic `UPDATE ... WHERE status='uploaded'`. Only one gets `rowcount == 1`; the other returns `None` and does nothing.
3. A client can claim to be anyone. The login (JWT) is the only trustworthy identity. `extra="forbid"` turns a sent `reviewer` field into a 422.
4. The tenant id inside the `thread_id`, and the service's ownership check against the RLS-protected `documents` table before touching the graph.
5. If the graph moved but nothing is saved, the answer is lost; writing the tables only after the graph succeeded, in one transaction, means the result and the audit row appear together or not at all.
6. Early: `Content-Length` larger than the limit -> 413 before reading. Late: the body is read with a limit of limit+1 bytes -> 413 (covers a missing/lying header).
7. A `needs_review` reading may be wrong; reconciling it would produce confident but false findings. Settled = `ok` or `reviewed`.
8. `None` was stored as JSON `null` (a value), not SQL `NULL`, breaking the `(action='correct') = (corrected_data IS NOT NULL)` check. `JSONB(none_as_null=True)` changes only the Python-side mapping.
9. Creating tables is DDL; the app role has DML only (least privilege). `test_checkpoint.py` connects as the app role and asserts that `CREATE TABLE` fails.
10. The work is lost on restart (document stuck in `processing`), and it competes with request handling in the same process. Use a queue (SQS) plus a separate worker, with a sweeper that resets stale `processing` rows.

# Experiments to try
1. Start the API without `OPENAI_API_KEY` and POST a file: expect 503 and no new row in `documents`.
2. Upload a document, kill uvicorn while it is `needs_review`, restart, and `POST .../review`: the pause survived.
3. Send a review body with a `"reviewer"` field: expect 422.
4. Log in as a second company and `GET /documents/<first company's id>`: expect 404, not 403.
5. In `psql`, `SELECT action, corrected_data IS NULL FROM reviews;` after an approve and a correct.

# Commands cheat sheet
```
alembic upgrade head
alembic check
python -m freight_intel.pipeline.checkpoint     # one-time, owner role
pytest -q                                        # 299 passed
uvicorn freight_intel.api.main:app --reload
```