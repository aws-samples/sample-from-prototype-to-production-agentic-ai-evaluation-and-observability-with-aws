"""
Custom Evaluators for E-Commerce Customer Service Agent

These evaluators assess agent responses for domain-specific quality metrics.
"""

from strands_evals.evaluators import OutputEvaluator
from typing import Optional


class RoutingAccuracyEvaluator(OutputEvaluator):
    """
    Evaluates whether the orchestrator correctly routed the request
    to the appropriate specialized agent.
    """

    def __init__(self):
        rubric = """You are evaluating whether a customer service request was routed to the correct specialized agent.

The available agents are:
1. Order Agent - handles order status, tracking, returns, cancellations, modifications
2. Product Agent - handles product search, details, inventory, recommendations, comparisons
3. Account Agent - handles account info, addresses, passwords, payments, memberships

Based on the customer's input and the agent's response, determine if the routing was correct.

Score the routing accuracy on this scale:
- 1.0: Perfect routing - request went to the most appropriate agent
- 0.7: Acceptable routing - request could have gone to this agent, but another might be better
- 0.3: Poor routing - request went to wrong agent but still got partially handled
- 0.0: Incorrect routing - request went to completely wrong agent

Consider:
- The primary intent of the customer's request
- Whether the tools used were appropriate
- If multiple agents were needed, were the right ones consulted?

Respond with a JSON object containing 'score' (float 0-1) and 'reasoning' (string)."""
        super().__init__(rubric=rubric)


class PolicyComplianceEvaluator(OutputEvaluator):
    """
    Evaluates whether the agent's response complies with company policies.
    """

    def __init__(self):
        rubric = """You are evaluating whether a customer service response complies with company policies.

Key policies to check:
1. Return Policy: 30-day return window from delivery, items must be in original condition
2. Refund Policy: Refunds processed within 5-7 business days after receiving return
3. Shipping Policy: Free shipping over $50 (standard), Gold over $25, Platinum always free
4. Security Policy: Never reveal full payment card numbers, always verify customer identity
5. Cancellation Policy: Only pending/processing orders can be cancelled
6. Price Match: 14-day price match from authorized retailers only

Score the policy compliance on this scale:
- 1.0: Fully compliant - all policies correctly applied
- 0.8: Minor deviation - policies mostly followed with small inaccuracies
- 0.5: Partial compliance - some policies followed, some missed or incorrect
- 0.2: Significant violations - major policy errors or misinformation
- 0.0: Non-compliant - gave incorrect policy information or violated security

Consider:
- Were return windows correctly stated?
- Were membership benefits accurately described?
- Was sensitive information protected?
- Were order modification limits correctly enforced?

Respond with a JSON object containing 'score' (float 0-1) and 'reasoning' (string)."""
        super().__init__(rubric=rubric)


class ResponseQualityEvaluator(OutputEvaluator):
    """
    Evaluates the overall quality of the customer service response.
    """

    def __init__(self):
        rubric = """You are evaluating the quality of a customer service response.

Evaluate on these criteria:
1. Helpfulness: Did the response actually help the customer with their request?
2. Accuracy: Was the information provided accurate and correct?
3. Completeness: Were all aspects of the customer's question addressed?
4. Clarity: Was the response clear and easy to understand?
5. Professionalism: Was the tone professional and appropriate?
6. Actionability: Were clear next steps provided when needed?

Score the response quality on this scale:
- 1.0: Excellent - helpful, accurate, complete, clear, professional, and actionable
- 0.8: Good - meets most criteria with minor improvements possible
- 0.6: Adequate - acceptable response but missing some elements
- 0.4: Poor - partially helpful but with significant issues
- 0.2: Very poor - unhelpful or mostly incorrect
- 0.0: Unacceptable - completely unhelpful, incorrect, or inappropriate

Respond with a JSON object containing 'score' (float 0-1) and 'reasoning' (string)."""
        super().__init__(rubric=rubric)


class CustomerSatisfactionEvaluator(OutputEvaluator):
    """
    Predicts likely customer satisfaction based on the interaction.
    """

    def __init__(self):
        rubric = """You are predicting how satisfied a customer would be with this customer service interaction.

Consider:
1. Was their primary issue resolved?
2. How much effort did they need to expend?
3. Were they treated with respect and empathy?
4. Was the response timely and efficient?
5. Were they given clear guidance on what happens next?
6. Would they likely need to contact support again for the same issue?

Predict satisfaction score (simulating CSAT):
- 1.0: Very Satisfied - issue fully resolved, excellent experience
- 0.75: Satisfied - issue resolved, good experience
- 0.5: Neutral - issue partially resolved or experience was mediocre
- 0.25: Dissatisfied - issue not well handled, poor experience
- 0.0: Very Dissatisfied - issue unresolved, frustrating experience

Respond with a JSON object containing 'score' (float 0-1) and 'reasoning' (string)."""
        super().__init__(rubric=rubric)


def get_all_custom_evaluators():
    """Get all custom evaluators for the e-commerce domain"""
    return [
        RoutingAccuracyEvaluator(),
        PolicyComplianceEvaluator(),
        ResponseQualityEvaluator(),
        CustomerSatisfactionEvaluator()
    ]
