# Day 1 - LLM API fundamentals (auth, requests, streaming, token counting)

**Date completed:** _(fill in)_

## What I learned

**The big picture**
An LLM API call is basically: your app sends a request (API key + a list of messages) to the
provider's server, the model generates a reply, and the reply comes back to your app.

```
Your app -> HTTPS request (API key + messages JSON) -> LLM provider -> Response (streamed back)
```

**Roles and message structure**
Every request is a list of messages, each with a role:
- `system` - instructions for how the model should behave (set once, up front)
- `user` - what the person is saying
- `assistant` - what the model said back (needed so the model remembers earlier turns)

```json
{
  "model": "gpt-4o-mini",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Explain what an API is in one sentence."}
  ]
}
```

**Tokens**
The model reads tokens, not words - small chunks of text (~4 characters per token in English,
roughly 75 words per 100 tokens). Tokens matter because:
- Billing is per token (input + output)
- Every model has a max context window measured in tokens

**Streaming vs non-streaming**
- Non-streaming: wait for the full reply, then get it all at once
- Streaming (`stream=True`): the reply arrives in small chunks as it's generated, so it can be
  printed/displayed word by word - this is the mechanism behind the "typing" effect in chat apps

**Anatomy of a streamed chunk**
Each chunk has `chunk.choices[0].delta.content` instead of the full `message.content` you get in
a non-streaming response. `delta` = "just the new bit since last time," not the whole message so
far. The first and last chunks carry `content = None` (they carry role/metadata instead), so every
loop needs an `if delta:` guard before printing.

`print(delta, end="", flush=True)`:
- `end=""` stops `print()` from adding a newline after every fragment (otherwise each word lands
  on its own line instead of flowing as one sentence)
- `flush=True` forces Python to push output to the terminal immediately instead of buffering it,
  which would delay everything and defeat the point of streaming

## Code I wrote

Built `day1_chatbot.py` - a terminal chatbot that:
- Keeps a running `messages` list (starting with a system message) so context persists across turns
- Loops: takes user input, sends the full conversation history with `stream=True`, prints the
  reply as it streams in
- Appends the model's full reply back into `messages` with role `"assistant"` (not `"system"` -
  see bug below) so the model remembers what it said
- Estimates token cost of the whole conversation after every turn using `tiktoken`
- Exits on `quit`

**Bug found and fixed:** originally appended the assistant's reply with `"role": "system"` instead
of `"role": "assistant"`. This mislabels the model's own past replies as if they were instructions
for how to behave, corrupting the conversation history over multiple turns. Fixed by changing the
role to `"assistant"`.

**Bonus 1 - precise token counting.** The original `calculate_token_cost` only counted tokens in
each message's `content`, undercounting the real number. OpenAI's actual formula adds fixed
overhead per message (for role/formatting) plus a priming overhead for the reply:

```python
def calculate_token_cost(messages, model=model):
    encoding = tiktoken.encoding_for_model(model)
    tokens_per_message = 3   # overhead per message (role + formatting)
    tokens_per_name = 1      # extra overhead if a "name" field is used

    total_tokens = 0
    for msg in messages:
        total_tokens += tokens_per_message
        for key, value in msg.items():
            total_tokens += len(encoding.encode(value))
            if key == "name":
                total_tokens += tokens_per_name

    total_tokens += 3  # every response is primed with "assistant" role
    return total_tokens
```

**Bonus 2 - real usage numbers from the stream itself.** Passing
`stream_options={"include_usage": True}` makes the final chunk carry a populated `.usage` field
with actual token counts - but that final chunk has an empty `choices` list, so the loop needs a
`if chunk.choices:` guard to avoid an `IndexError`:

```python
stream = openai_client.chat.completions.create(
    model=model,
    messages=messages,
    stream=True,
    stream_options={"include_usage": True}
)

response_text = ""
actual_usage = None
for chunk in stream:
    if chunk.choices:
        delta = chunk.choices[0].delta.content
        if delta:
            response_text += delta
    if chunk.usage:
        actual_usage = chunk.usage
```

Compared side by side: tiktoken gives a fast pre-send estimate, `chunk.usage` gives the real
post-send number. Good practice: estimate before sending, verify after receiving.

## Environment / tooling set up today
- Created OpenAI account, added $10 credit, moved to Usage tier 1
- Set an organization-level hard spend limit ($5) with "Enforce a hard limit" enabled, plus spend
  alerts at 80%/100%
- Generated API key, stored as an environment variable (not hardcoded)
- Set up 3 git repos (`ai-learning-journal`, `production-rag-agent`, `multiagent-platform`) with
  `.gitignore` blocking `.env`, pushed to GitHub over SSH
- Fixed VS Code interpreter pointing at the wrong Python environment so autocomplete works against
  the venv where packages are actually installed

## Questions / things that confused me
- _(fill in anything that's still fuzzy)_

## Practice task
`day1_chatbot.py` - streaming terminal chatbot with role-based conversation history and live token
cost estimation. Located in `practice/`.