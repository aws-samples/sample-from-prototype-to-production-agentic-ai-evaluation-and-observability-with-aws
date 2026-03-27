# Deployment Configuration for Failure Cases
#
# This file defines deployment settings that differ from the working version.
# When using the deployment notebook (03-production-deployment.ipynb) with
# failure cases, override WORKSHOP_PREFIX to avoid resource conflicts.
#
# Usage in the deployment notebook:
#   1. Set AGENT_DIR to point to this directory
#   2. Change WORKSHOP_PREFIX to 'ecommerce-workshop-broken'
#
# This allows both the working agent and the broken agent to coexist,
# so Module 04 can continue using the working agent while failure cases
# are deployed separately.

WORKSHOP_PREFIX = "ecommerce-workshop-broken"
RUNTIME_NAME = "ecommerce_workshop_broken_product_catalog_agent"
