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