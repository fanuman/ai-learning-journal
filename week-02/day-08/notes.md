# Day 8 - RAG architecture: naive retrieval and generation pipeline

**Date completed:** _(fill in)_

## What I learned

**RAG in plain English**
Retrieval-Augmented Generation fixes the exact problem from Day 1 (the model confidently
guessing the wrong date) - instead of relying purely on what the model memorized during
training, retrieve relevant real documents first, hand them to the model as context, and ask it
to answer using that material. Closed-book exam (no RAG) vs open-book exam (RAG) - the model
doesn't need to know everything, it needs to be handed the right material and be good at reading
it.

**The naive pipeline - four steps**
1. Chunk documents into smaller pieces (kept simple today - smarter chunking is Day 9)
2. Embed each chunk, store in a vector DB (Day 6 + Day 7)
3. At query time, embed the question, retrieve top-k most similar chunks
4. Stuff those chunks into the prompt, ask the model to answer using them

Called "naive" because there's no re-ranking, no query rewriting, and (before today's bonus) no
relevance threshold - it always trusts the top-k results whether they're actually good matches or
not.

**Design choice: invented facts to prove retrieval is actually working**
Used a fictional "Acme Corp" employee handbook with specific invented numbers (45 days remote
work, $75 stipend, 16/6 weeks parental leave, 22/27 days vacation). If the model answers with the
exact invented number, that's real proof retrieval worked - there's no way it guessed a made-up
company's exact policy from training data alone.

**The grounding instruction - direct callback to Day 2**
```
Answer the question using ONLY the context below. If the answer isn't in the context,
say "I don't have information about that."
```
Vector search always returns *something*, relevant or not. Without this explicit instruction, the
model might answer from its own training data anyway when retrieval pulls back irrelevant chunks
- silently defeating the point of RAG. This one line is what forces it to stay grounded.

## Code I wrote

Built `day8_first_rag_app.py`: `retrieve()`, `build_prompt()`, `generate_answer()` wired
together into a working pipeline over the Acme documents in a Chroma collection.

**Near-miss, not an actual bug:** initially reused the collection name `my_documents` from Day 7,
which would have mixed Day 7's leftover test sentences (cat/feline/stock market/movie) in with
today's Acme documents - a real risk, since it would stay invisible until a query happened to
surface the wrong dataset's content. Confirmed this specific run was actually fine because
`delete_collection` had already been called first. Still switched to a dedicated collection name
(`acme_handbook`) going forward as a permanent habit, rather than relying on remembering to
manually clear a shared collection between projects.

**Bonus: empirically-validated relevance threshold.** Added a distance check before calling the
LLM at all:
```python
if all(distance >= 0.5 for distance in distances):
    return "I don't have information about that. (No Document Matches)"
```
`all(...)` matters here - only bail out when *every* retrieved chunk is weak (retrieval genuinely
failed), not just when the top match is merely decent rather than excellent.

## Test results

**Question 1 (answerable): "How many days can I work from abroad?"**
```
0.3973 - remote work policy chunk (correct match)
0.5523 - vacation policy chunk
0.7209 - parental leave chunk
Answer: You can work from abroad for up to 45 days per year.
```
Correct answer, correct source chunk ranked first.

**Question 2 (unanswerable): "What is Acme's stock price?"**
```
0.5410 - home office stipend chunk (best available, still a bad match)
0.5730 - parental leave chunk
0.5893 - vacation policy chunk
Answer: I don't have information about that. (No Document Matches)
```
LLM call was skipped entirely - the `return` fires before `build_prompt()` or the API call ever
run, saving both cost and latency on a query already known to have no answer.

**The `0.5` threshold isn't arbitrary - the data validates it.** Best real match scored 0.3973;
best fake-question match scored 0.5410. There's a genuine gap between "actually relevant" and
"best of a bad bunch," and 0.5 sits right in that gap. This is the same judgment-call principle
as Day 3's production wrapper: don't spend an expensive step (a full LLM call) on something a
cheap earlier signal (retrieval distance) already indicates will fail.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Noted: `0.5` is tuned to this dataset and this embedding model specifically, not a universal
  constant - a different document set could need a different cutoff. This eyeballed calibration
  is effectively the seed of what becomes formal RAG evaluation in Week 3 (Day 13) - systematically
  measuring retrieval quality instead of checking two examples by eye.
- Noted for later polish (not urgent): the per-call distance debug print should become a
  `verbose=False` parameter or proper logging before this ends up behind a real API endpoint, so
  production logs aren't flooded with retrieval debug output on every request.

## Practice task
`day8_first_rag_app.py` - first working naive RAG pipeline: Acme Corp fictional handbook stored
in Chroma, `retrieve()` + `build_prompt()` + `generate_answer()` wired together, tested against
one answerable and one unanswerable question, plus an empirically-validated distance threshold
that skips the LLM call entirely when retrieval genuinely fails. Located in `practice/`.