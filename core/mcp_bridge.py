"""
MCP (Model Context Protocol) Bridge & Tool Dispatcher
Bridges Qwen-35b / external LLMs directly to executable MCP tools.
"""

from typing import Dict, Any, List, Optional
import json
import re
from core.observability import log_agent_step
from mcp_server.tools import (
    query_inventory_tool,
    update_stock_tool,
    update_threshold_tool,
    add_item_tool,
    delete_item_tool,
    manage_category_tool,
    approve_prs_tool,
    calculate_financials_tool,
    dispatch_notification_tool
)


MCP_TOOL_DEFINITIONS = [
    {
        "name": "query_inventory",
        "description": "Query items in the warehouse catalog. Can filter by search query, category, or stock status ('low', 'out', 'normal').",
        "parameters": {
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Search keyword or product name"},
                "category": {"type": "string", "description": "Category filter"},
                "status_filter": {"type": "string", "enum": ["low", "out", "normal"]}
            }
        }
    },
    {
        "name": "update_threshold",
        "description": "Update minimum and/or maximum stock thresholds for a product.",
        "parameters": {
            "type": "object",
            "properties": {
                "sku": {"type": "string", "description": "Product SKU or exact item name"},
                "min_stock": {"type": "integer", "description": "Minimum stock threshold"},
                "max_stock": {"type": "integer", "description": "Maximum stock threshold"}
            },
            "required": ["sku"]
        }
    },
    {
        "name": "update_stock",
        "description": "Adjust the current physical stock quantity for a product.",
        "parameters": {
            "type": "object",
            "properties": {
                "sku": {"type": "string", "description": "Product SKU"},
                "change_amount": {"type": "integer", "description": "Amount to add (positive) or deduct (negative)"},
                "reason": {"type": "string", "description": "Reason for stock adjustment"}
            },
            "required": ["sku", "change_amount"]
        }
    },
    {
        "name": "add_item",
        "description": "Register a new product item into the warehouse catalog database.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Product name"},
                "category": {"type": "string", "description": "Product category"},
                "unit_price": {"type": "number", "description": "Price per unit in IDR"},
                "current_stock": {"type": "integer", "description": "Initial stock quantity"},
                "min_stock": {"type": "integer", "description": "Min stock threshold"},
                "max_stock": {"type": "integer", "description": "Max stock threshold"},
                "unit": {"type": "string", "description": "Unit (pcs, karton, pouch, box, roll)"},
                "supplier_name": {"type": "string", "description": "Supplier name"}
            },
            "required": ["name", "category", "unit_price"]
        }
    },
    {
        "name": "delete_item",
        "description": "Delete a product from the database.",
        "parameters": {
            "type": "object",
            "properties": {
                "sku": {"type": "string", "description": "Product SKU to delete"}
            },
            "required": ["sku"]
        }
    },
    {
        "name": "manage_category",
        "description": "Add or delete a category in the database.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "delete"]},
                "category_name": {"type": "string", "description": "Category name"}
            },
            "required": ["action", "category_name"]
        }
    },
    {
        "name": "approve_prs",
        "description": "Approve Purchase Requisitions in batch or targeted by criteria (e.g. above X IDR, below X IDR, or all pending).",
        "parameters": {
            "type": "object",
            "properties": {
                "filter_status": {"type": "string", "default": "pending_approval"},
                "min_amount": {"type": "number", "description": "Only approve PRs with total greater than this amount in IDR"},
                "max_amount": {"type": "number", "description": "Only approve PRs with total less than this amount in IDR"},
                "pr_number": {"type": "string", "description": "Specific PR number to approve"}
            }
        }
    },
    {
        "name": "calculate_financials",
        "description": "Compute and summarize all financial calculations: total PR liabilities, pending approval values, approved POs, and total warehouse inventory asset valuation.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "default": "prs"}
            }
        }
    },
    {
        "name": "dispatch_notification",
        "description": "Send notification to external channels (email, Telegram, WhatsApp) via n8n.",
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "enum": ["email", "telegram", "whatsapp"]},
                "recipient": {"type": "string"},
                "message": {"type": "string"},
                "subject": {"type": "string"}
            },
            "required": ["channel", "recipient", "message"]
        }
    }
]


class MCPBridge:
    """Executes MCP tools selected by AI Agents."""

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches tool execution to the corresponding MCP tool function."""
        log_agent_step(
            step_name="MCP Tool Dispatch",
            agent_name="MCPBridge",
            status="running",
            message=f"Executing MCP tool '{tool_name}' with args: {arguments}"
        )

        try:
            if tool_name == "query_inventory":
                res = await query_inventory_tool(**arguments)
                return {"status": "success", "action_type": "summary", "data": res}
            elif tool_name == "update_threshold":
                res = await update_threshold_tool(**arguments)
                return {"status": "success", "action_type": "update_threshold", "data": res}
            elif tool_name == "update_stock":
                res = await update_stock_tool(**arguments)
                return {"status": "success", "action_type": "update_stock", "data": res}
            elif tool_name == "add_item":
                res = await add_item_tool(**arguments)
                return {"status": "success", "action_type": "add_item", "data": res}
            elif tool_name == "delete_item":
                res = await delete_item_tool(**arguments)
                return {"status": "success", "action_type": "delete_item", "data": res}
            elif tool_name == "manage_category":
                res = await manage_category_tool(**arguments)
                return {"status": "success", "action_type": "add_category" if arguments.get("action") == "add" else "delete_category", "data": res}
            elif tool_name == "approve_prs":
                res = await approve_prs_tool(**arguments)
                return {"status": "success", "action_type": "approve_prs", "data": res}
            elif tool_name == "calculate_financials":
                res = await calculate_financials_tool(**arguments)
                return {"status": "success", "action_type": "calculate_financials", "data": res}
            elif tool_name == "dispatch_notification":
                res = await dispatch_notification_tool(**arguments)
                return {"status": "success", "action_type": "notify", "data": res}
            else:
                return {"status": "error", "message": f"Unknown MCP tool: '{tool_name}'"}
        except Exception as e:
            log_agent_step(
                step_name="MCP Tool Error",
                agent_name="MCPBridge",
                status="error",
                message=f"Error executing MCP tool '{tool_name}': {str(e)}"
            )
            return {"status": "error", "message": str(e)}


mcp_bridge = MCPBridge()
