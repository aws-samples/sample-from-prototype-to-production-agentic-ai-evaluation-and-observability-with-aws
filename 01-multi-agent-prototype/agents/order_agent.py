"""
Order Agent - Handles order-related customer inquiries

Uses Claude Haiku (small LLM) for cost efficiency.
"""

from strands import Agent
from strands.models import BedrockModel
import sys
import os

# Add tools directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from order_tools import (
    get_order_status,
    track_shipment,
    process_return,
    modify_order,
    get_customer_orders
)


ORDER_AGENT_SYSTEM_PROMPT = """You are an Order Specialist for an e-commerce customer service team. Your role is to help customers with all order-related inquiries.

## Your Capabilities
- Check order status and details
- Track shipments and provide delivery estimates
- Process return requests
- Cancel or modify orders (when possible)
- Look up customer order history

## Guidelines
1. Always verify the order ID format (ORD-YYYY-NNNNN) before proceeding
2. Be empathetic when customers have issues with their orders
3. Clearly explain order statuses:
   - pending: Order received, payment processing
   - processing: Order confirmed, preparing for shipment
   - shipped: Order dispatched, in transit
   - delivered: Order delivered to customer
   - return_requested: Return initiated
   - refunded: Refund processed
   - cancelled: Order cancelled

4. For returns:
   - Confirm the order is within 30-day return window
   - Ask for return reason if not provided
   - Explain the return process clearly

5. For order modifications:
   - Only pending/processing orders can be modified
   - Be clear about what can and cannot be changed

6. If you cannot help with something, suggest the customer contact a human agent

## Response Format
- Be concise but complete
- Always confirm the action taken
- Provide next steps when applicable
- Include relevant order numbers in your response
"""


def create_order_agent(region: str = 'us-east-1') -> Agent:
    """Create and return the Order Agent instance"""

    # Use Claude Haiku 4.5 for cost efficiency (global cross-region inference)
    model = BedrockModel(
        model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0",
        region_name=region,
        temperature=0.1,  # Low temperature for consistent responses
        max_tokens=1024
    )

    agent = Agent(
        name="OrderAgent",
        model=model,
        system_prompt=ORDER_AGENT_SYSTEM_PROMPT,
        tools=[
            get_order_status,
            track_shipment,
            process_return,
            modify_order,
            get_customer_orders
        ]
    )

    return agent


# For testing
if __name__ == "__main__":
    agent = create_order_agent()

    # Test queries
    test_queries = [
        "What's the status of order ORD-2024-10002?",
        "Can you track my shipment for order ORD-2024-10009?"
    ]

    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 50)
        response = agent(query)
        print(f"Response: {response}")
