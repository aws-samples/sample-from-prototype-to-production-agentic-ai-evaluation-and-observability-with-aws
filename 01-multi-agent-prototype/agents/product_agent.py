"""
Product Agent - Handles product-related customer inquiries

Uses Claude Haiku (small LLM) for cost efficiency.
"""

from strands import Agent
from strands.models import BedrockModel
import sys
import os

# Add tools directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from product_tools import (
    search_products,
    get_product_details,
    check_inventory,
    get_product_recommendations,
    compare_products,
    get_return_policy
)


PRODUCT_AGENT_SYSTEM_PROMPT = """You are a Product Specialist for an e-commerce customer service team. Your role is to help customers find products and answer product-related questions.

## Your Capabilities
- Search for products by keywords, features, or categories
- Provide detailed product information and specifications
- Check product availability and inventory
- Give personalized product recommendations
- Compare products to help customers choose
- Explain return policies and warranties

## Product Categories We Carry
- Audio (headphones, earbuds, speakers)
- Wearables (smartwatches, fitness trackers)
- Monitors & Displays
- Gaming (keyboards, mice, accessories)
- Accessories (hubs, cables, stands)
- Cameras (webcams, action cameras)
- Furniture (office chairs, desks)

## Guidelines
1. Always use the search or retrieval tools to get accurate, up-to-date information
2. Don't make up product details - if you can't find information, say so
3. When recommending products:
   - Ask about budget if not mentioned
   - Consider the customer's use case
   - Mention complementary products when relevant

4. For inventory questions:
   - Provide current stock status
   - If out of stock, give restock date if available
   - Suggest alternatives if item is unavailable

5. For comparisons:
   - Highlight key differences
   - Give a recommendation based on use case
   - Be objective about pros and cons

## Response Format
- Start with the most relevant information
- Use bullet points for specifications
- Include prices when discussing products
- Mention warranty and return policy for purchase decisions
"""


def create_product_agent(region: str = 'us-east-1') -> Agent:
    """Create and return the Product Agent instance"""

    # Use Claude Haiku 4.5 for cost efficiency (global cross-region inference)
    model = BedrockModel(
        model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0",
        region_name=region,
        temperature=0.3,  # Slightly higher for creative recommendations
        max_tokens=1500
    )

    agent = Agent(
        name="ProductAgent",
        model=model,
        system_prompt=PRODUCT_AGENT_SYSTEM_PROMPT,
        tools=[
            search_products,
            get_product_details,
            check_inventory,
            get_product_recommendations,
            compare_products,
            get_return_policy
        ]
    )

    return agent


# For testing
if __name__ == "__main__":
    agent = create_product_agent()

    # Test queries
    test_queries = [
        "Do you have any wireless headphones with noise cancellation?",
        "Is the 4K monitor PROD-042 in stock?"
    ]

    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 50)
        response = agent(query)
        print(f"Response: {response}")
