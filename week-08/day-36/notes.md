# Day 36 - Capstone architecture design: FreightLens

**Date completed:** _(fill in)_

## What I learned

**Picking the project is part of the engineering.** Choosing the domain took real reasoning, not a
coin flip: the goal is a portfolio piece that shows AI skills *and* SaaS engineering, so a project
that exercises only LangGraph (the research reviewer) loses to one that also exercises multi-tenant
Postgres, auth, an API, and a frontend. A real job posting in freight tech became the target, which
made the requirements concrete instead of generic.

**"The LLM reads, software decides" is the design rule that separates this from a ChatGPT wrapper.**
The model turns unstructured text into candidate fields. Deterministic code validates them (line
items sum to totals, currencies valid, dates parse) and decides whether an invoice overcharged. The
LLM only writes the explanation, from computed facts. That means the model can be wrong without the
product being wrong, because validation catches it or routes it to a human.

**The pipeline uses every LangGraph primitive for a real reason:**
- A **router** (conditional edges) sends each document to exactly one specialist extractor - the
  Day 31 pattern, now built properly in Week 8 as planned.
- A **cycle** (validate -> repair -> validate, capped at 2 attempts) feeds the specific validation
  errors back to the model.
- An **interrupt** pauses for human review on low confidence and resumes from a Postgres checkpoint.

**Prompt injection gets more realistic here.** Day 34's attacks were typed by a user. In FreightLens
the hostile text arrives inside a PDF or an email ("mark this invoice as approved"). The defense is
structural: documents are delimited data, the LLM has no tools, and money decisions are made by
code, so an injected instruction has nothing to hijack.

**Tenant isolation belongs in the database.** Row-level security means an application bug cannot leak
one company's documents to another; the required test tries to read another tenant's data by
guessed ID.

## Today's exercise

Wrote `design-doc.md`: problem and users, goals/non-goals, domain model (charge taxonomy, money
handling), architecture, the LangGraph graph with state and node table, reconciliation logic, Postgres
schema with RLS, auth, API, security, eval plan with a synthetic seeded-error dataset, technology
choices with reasons, a day-by-day build plan with a cut order, and risks with open questions for a
domain expert.

Recorded the domain decision in `week-08-capstone-plan.md` so it survives context compaction.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Whether synthetic documents will be realistic enough; the plan is to add deliberate noise and have
  someone from the industry review a sample
- Whether the reconciliation step should be a second LangGraph graph or a plain service (leaning
  plain service, since it is mostly deterministic)
- Which charge abbreviations are most common on real invoices (listed as open questions in the
  design doc)

## Practice task
Chose a capstone domain by weighing seven candidates against the actual goal (AI skills plus SaaS),
then wrote a complete design document for FreightLens: a multi-tenant system that extracts and
normalizes freight quotes and invoices from messy PDFs, spreadsheets, and emails, and reconciles them
deterministically. The central decision was the LLM/software boundary: the model reads, code
validates and decides, and the model only explains computed results. Planned the evaluation up front
(a synthetic dataset with seeded errors and field-level metrics) so quality is measured from the first
commit rather than argued afterwards.