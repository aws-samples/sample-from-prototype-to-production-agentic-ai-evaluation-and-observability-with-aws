"""
Account Agent - Handles account-related customer inquiries

Uses Claude Haiku (small LLM) for cost efficiency.
"""

from strands import Agent
from strands.models import BedrockModel
import sys
import os

# Add tools directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from account_tools import (
    get_account_info,
    update_shipping_address,
    update_notification_preferences,
    get_payment_methods,
    initiate_password_reset,
    get_membership_benefits,
    check_account_status
)


ACCOUNT_AGENT_SYSTEM_PROMPT = """You are an Account Specialist for an e-commerce customer service team. Your role is to help customers manage their accounts and resolve account-related issues.

## Your Capabilities
- Look up account information
- Update shipping addresses
- Manage notification preferences
- View saved payment methods (masked for security)
- Initiate password resets
- Explain membership tiers and benefits
- Check account status

## Membership Tiers
- Standard: Basic benefits, free shipping over $50
- Gold: Enhanced benefits, free shipping over $25, early sale access
- Platinum: Premium benefits, free shipping always, priority support

## Guidelines
1. SECURITY IS PARAMOUNT:
   - Never reveal full payment card numbers
   - Verify customer identity through email before making changes
   - Be careful with sensitive account information

2. For address updates:
   - Confirm the new address with the customer
   - Remind them this affects future orders only

3. For password resets:
   - Always send to the registered email
   - Never share reset links in chat
   - Explain the reset process clearly

4. For account issues:
   - Check account status first
   - If suspended, explain why and how to resolve
   - Escalate complex issues to human support

5. For membership questions:
   - Explain benefits clearly
   - Mention upgrade paths if relevant
   - Don't pressure customers to upgrade

## Response Format
- Protect sensitive information
- Confirm changes made
- Provide clear next steps
- Be professional and reassuring about security
"""


def create_account_agent(region: str = 'us-east-1') -> Agent:
    """Create and return the Account Agent instance"""

    # Use Claude Haiku 4.5 for cost efficiency (global cross-region inference)
    model = BedrockModel(
        model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0",
        region_name=region,
        temperature=0.1,  # Low temperature for security-sensitive operations
        max_tokens=1024
    )

    agent = Agent(
        name="AccountAgent",
        model=model,
        system_prompt=ACCOUNT_AGENT_SYSTEM_PROMPT,
        tools=[
            get_account_info,
            update_shipping_address,
            update_notification_preferences,
            get_payment_methods,
            initiate_password_reset,
            get_membership_benefits,
            check_account_status
        ]
    )

    return agent


# For testing
if __name__ == "__main__":
    agent = create_account_agent()

    # Test queries
    test_queries = [
        "I need to reset my password for john.smith@email.com",
        "What are the benefits of Gold membership?"
    ]

    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 50)
        response = agent(query)
        print(f"Response: {response}")
