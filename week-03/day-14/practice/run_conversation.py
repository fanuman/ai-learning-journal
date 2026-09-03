from openai import OpenAI, pydantic_function_tool
from pydantic import BaseModel, Field
from datetime import datetime
import json

from vector_search_module import retrieve

client = OpenAI()

class GetCurrentTime(BaseModel):
    """Get the current date and time."""
    pass

class SearchDocuments(BaseModel):
    """Search the AI governance corpus (NIST AI RMF, NIST Generative AI Profile, OWASP Top 10 for LLMs) for relevant information."""
    query: str = Field(..., description="The search query")

tools = [
    pydantic_function_tool(GetCurrentTime),
    pydantic_function_tool(SearchDocuments),
]

print("\n------------------------")
print("Tools:", tools)
print("------------------------\n")

def get_current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def search_documents(query):
    chunks, distances = retrieve(query, k=3)
    return "\n\n".join(chunks)

available_functions = {
    "GetCurrentTime": get_current_time,
    "SearchDocuments": search_documents,
}

def run_conversation(user_message):
    messages = [
        {"role": "system", "content": "You have access to SearchDocuments and GetCurrentTime. For ANY question about AI governance, security, prompt injection, or risk management topics, you MUST call SearchDocuments first and ground your answer in the results — even if you believe you already know the answer. Do not answer from your own knowledge for these topics."},
        {"role": "user", "content": user_message}
    ]
    response = client.chat.completions.create(model="gpt-4o-mini", messages=messages, tools=tools)
    response_message = response.choices[0].message

    print("\n------------------------")
    print("response_message, response_message.tool_calls:", response_message, response_message.tool_calls)
    print("------------------------\n")

    if not response_message.tool_calls:
        return response_message.content  # model answered directly, no tool needed

    messages.append(response_message)

    for tool_call in response_message.tool_calls:
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)
        result = available_functions[function_name](**function_args)

        print("\n------------------------")
        print("result:", result)
        print("------------------------\n")

        

        messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": str(result)})

        print("\n------------------------")
        print("messages before second call:", messages)
        print("------------------------\n")

    second_response = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
    return second_response.choices[0].message.content


if __name__ == "__main__":
    # final_response = run_conversation("WWhat time is it right now?")
    # final_response = run_conversation("What is prompt injection?")
    final_response = run_conversation("What's 2+2?")

    print("\n------------------------")
    print("final_response:", final_response)
    print("------------------------\n")