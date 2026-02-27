"""
Utility helpers for the e-commerce agent workshop notebooks.
"""

import json
from decimal import Decimal

from mcp_servers.product_mcp_server import get_product_details


def get_product(product_id:str):
    return json.loads(get_product_details(product_id))