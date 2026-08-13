from openai import OpenAI
import tiktoken

model = 'gpt-4o-mini'

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

openai_client = OpenAI()

messages = [
    {"role": "system", "content": "You are an expert assistant to resolve user queries."},
]

while True:
    user_msg = input("User: ")

    if user_msg == "quit":
        break

    messages.append({"role": "user", "content": user_msg})

    stream = openai_client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True}
    )

    response_text = ""
    actual_usage = None
    print("System: ", end="", flush=True)
    for chunk in stream:
        if chunk.choices:                      # guard against the empty final chunk
            delta = chunk.choices[0].delta.content
            if delta:
                print(delta, end="", flush=True)
                response_text += delta
        if chunk.usage:
            actual_usage = chunk.usage          # only populated on the last chunk

    messages.append({"role": "assistant", "content": response_text})

    estimated_tokens = calculate_token_cost(messages)
    print(f"\nEstimated (tiktoken): {estimated_tokens}")
    if actual_usage:
        print(f"Actual (from API):    {actual_usage.total_tokens}")
    