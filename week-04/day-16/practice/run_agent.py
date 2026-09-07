from dotenv import load_dotenv
load_dotenv()

import json
from openai import OpenAI, pydantic_function_tool
from pydantic import BaseModel, Field
from typing import List

client = OpenAI()

INVENTORY = {
    "TP-JKT-001": {"name": "StormShield Rain Jacket", "price": 189.00, "stock": 34},
    "TP-POLE-006": {"name": "TrekLight Trekking Poles", "price": 89.00, "stock": 58},
    "TP-TNT-002": {"name": "AlpinePeak 2-Person Tent", "price": 329.00, "stock": 12},
}

class CheckAvailability(BaseModel):
    """Check the current price and stock level for a product by SKU."""
    sku: str = Field(..., description="Product SKU")

class CalculateTotal(BaseModel):
    """Sum a list of item prices into a subtotal."""
    prices: List[float] = Field(..., description="List of individual item prices to sum")

class ApplyDiscount(BaseModel):
    """Apply a percentage discount to a subtotal."""
    subtotal: float = Field(..., description="The subtotal before discount")
    discount_percent: float = Field(..., description="Discount percentage, e.g. 15 for 15%")

def check_availability(sku):
    product = INVENTORY.get(sku.upper())
    if not product:
        return f"No product found with SKU {sku}."
    status = "In stock" if product["stock"] > 0 else "Out of stock"
    return f"{product['name']}: ${product['price']:.2f}, {status} ({product['stock']} units)"

def calculate_total(prices):
    return f"Subtotal: ${sum(prices):.2f}"

def apply_discount(subtotal, discount_percent):
    return f"After {discount_percent}% discount: ${subtotal * (1 - discount_percent / 100):.2f}"

tools = [pydantic_function_tool(CheckAvailability), pydantic_function_tool(CalculateTotal), pydantic_function_tool(ApplyDiscount)]
available_functions = {"CheckAvailability": check_availability, "CalculateTotal": calculate_total, "ApplyDiscount": apply_discount}


def run_agent(user_message, max_iterations=6):
    messages = [
        {"role": "system", "content": """You are a helpful shopping assistant. Available products:
    - StormShield Rain Jacket (SKU: TP-JKT-001)
    - TrekLight Trekking Poles (SKU: TP-POLE-006)
    - AlpinePeak 2-Person Tent (SKU: TP-TNT-002)

    Use the exact SKU codes above when calling CheckAvailability. Use the available tools step by step to answer questions that require checking multiple products, calculating totals, or applying discounts."""},
        {"role": "user", "content": user_message}
    ]

    for iteration in range(max_iterations):
        response = client.chat.completions.create(model="gpt-4o-mini", messages=messages, tools=tools)
        response_message = response.choices[0].message
        messages.append(response_message)

        if not response_message.tool_calls:
            return response_message.content  # model decided it's done

        print(f"--- Iteration {iteration + 1} ---")
        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            print(f"  Action: {function_name}({args})")

            result = available_functions[function_name](**args)
            print(f"  Observation: {result}")

            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

    return "Agent stopped after reaching max iterations without a final answer."


if __name__ == "__main__":
    final_response = run_agent("What's 2+2")
    print("\n------------------------")
    print("final_response:", final_response)
    print("------------------------\n")