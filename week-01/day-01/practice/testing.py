from openai import OpenAI
import tiktoken

model="gpt-4o-mini"

def calculate_token_cost(messages):
    total_tokens = 0
    encoding = tiktoken.encoding_for_model(model)

    for msg in messages:
        tokens = encoding.encode(msg['content'])
        total_tokens += len(tokens)

    return total_tokens

# print_cost("Explain what an API is in one sentence.")
total_cost = calculate_token_cost([
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain what an API is in one sentence."}
])
print(total_cost)

# client = OpenAI()  # automatically reads OPENAI_API_KEY from your environment

# response = client.chat.completions.create(
#     model="gpt-4o-mini",
#     messages=[
#         {"role": "system", "content": "You are a helpful assistant."},
#         {"role": "user", "content": "Explain what an API is in one sentence."}
#     ]
# )

# print(response.choices[0].message.content)

# print(response.usage)


# stream = client.chat.completions.create(
#     model="gpt-4o-mini",
#     messages=[{"role": "user", "content": "Write a short poem about the ocean."}],
#     stream=True
# )

# for chunk in stream:
#     delta = chunk.choices[0].delta.content
#     if delta:
#         print(delta, end="", flush=True)

