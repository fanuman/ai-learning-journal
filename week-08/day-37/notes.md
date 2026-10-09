# Day 37 - FreightLens foundation: tenant isolation, layered auth, synthetic data

**Date completed:** _(fill in)_

## What I learned

**Tenant isolation lives in the database, and the tests prove it.** Row-level security (RLS) makes
Postgres itself filter every query by the current tenant. The API connects as a separate, non-superuser
role, because owners and superusers bypass RLS and a test run as the owner would prove nothing. The
tenant id comes only from the signed token, is set per transaction with `set_config(..., true)`, and
forgetting to set it returns zero rows instead of everyone's rows ("fail closed"). I also disabled RLS
on purpose and watched 7 of 10 tests fail, which shows the suite can actually catch a leak.

**A user belongs to a tenant; a role says what they can do there.** `tenant_id` answers "whose data",
`role` answers "what may they do". One email belongs to one company in v1. A memberships table would
allow one person in many companies, and is a known trade-off for later.

**Layers keep each file's job small.** Routes parse HTTP, services hold rules and transactions,
repositories talk to the database, models describe tables, schemas describe what crosses the API.
Registration became pure ORM (one transaction, tenant then admin user, rolled back together on a
duplicate email). The only non-ORM call left is the login lookup, isolated in one repository function,
because at login the tenant isn't known yet and RLS hides every user.

**Small Python details that matter.** `*` in a signature forces keyword arguments, so two strings
like `email` and `password_hash` can't be swapped silently. `expire_on_commit` means reading an
attribute after the `with` block ends triggers a reload, so IDs are captured inside it. A bare
`echo >>` onto a file without a trailing newline glued `JWT_SECRET` onto the database password and
broke 21 tests: always check the shape of a config file before appending to it.

**Test data with known answers is what makes AI evaluation honest.** The generator produces fictional
carriers, quotes and invoices in PDF, Excel and email, with messiness (different number styles, date
styles, charge-name spellings between quote and invoice, port names versus codes) and with seeded
errors whose correct answer is recorded. Money is always integer minor units. Everything is driven by
a seed, so the same seed gives the same dataset and evaluation numbers stay comparable.

## Today's exercise

Built the repo foundation (Compose + Postgres, owner/app roles, Alembic migrations generated from
models), 11 isolation tests, a layered auth API (register, login, `/me`, argon2, JWT) with 19 tests,
and synthetic data generator v1 with 31 tests: 45 cases, nine scenario slots (clean x2, rounding
noise, overcharge, unquoted charge, missing charge, currency mismatch, expired quote, arithmetic
error), four carrier templates, and seven invoices containing a hostile "ignore previous instructions"
line to test prompt injection later.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Whether a memberships table should replace `users.tenant_id` once a second customer needs it
- Whether synthetic documents are realistic enough; plan is to ask someone from the industry to
  review a sample
- How the extractor will cope with dates like 05.10.2026 versus 10/05/2026 (the generator avoids
  slash dates so the ground truth stays unambiguous; real documents won't)

## Practice task
Add a fifth carrier template to `domain.CARRIERS` (pick a new number style, date format and label
pack), regenerate with `python -m freight_intel.synth`, and open one of its PDFs. Then add a test that
checks the new carrier appears in the dataset.