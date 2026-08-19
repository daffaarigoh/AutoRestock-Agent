import os
import json
import logging
from typing import Optional, Dict, Any
try:
    import httpx
except ImportError:
    import httpx2 as httpx

from core.schemas import PurchaseRequisitionDoc

logger = logging.getLogger(__name__)


class TelegramApprovalBot:
    """
    Dispatches interactive Human-in-the-Loop approval requests to Warehouse Managers
    via Telegram Bot with inline keyboard buttons.
    """

    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.is_configured = bool(self.bot_token and self.chat_id)

    async def send_restock_approval_request(
        self,
        pr: PurchaseRequisitionDoc,
        callback_base_url: str = "http://localhost:8000"
    ) -> Dict[str, Any]:
        """
        Sends an approval card to the manager's Telegram chat.
        If no token is configured, safely simulates the dispatch and returns a success payload.
        """
        items_summary = "\n".join([
            f"  • *{item.name}*: {item.reorder_qty} {item.unit} @ Rp {item.unit_price:,.0f} -> _Vendor: {item.vendor_name}_"
            for item in pr.items
        ])

        message_text = (
            f"🚨 *PERMINTAAN PERSETUJUAN RESTOCK (PR)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 *No. Dokumen*: `{pr.pr_number}`\n"
            f"📅 *Tanggal*: {pr.created_at}\n\n"
            f"📦 *Daftar Barang Kritis*:\n{items_summary}\n\n"
            f"💰 *Total Estimasi Biaya*: *Rp {pr.total_budget:,.2f}*\n"
            f"🛡️ *Audit Nemotron-35*: `{pr.auditor_status}`\n"
            f"📝 *Catatan Auditor*: _{pr.auditor_notes}_\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Silakan tinjau dan berikan persetujuan:"
        )

        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Approve PR",
                        "callback_data": f"approve:{pr.pr_number}"
                    },
                    {
                        "text": "❌ Reject",
                        "callback_data": f"reject:{pr.pr_number}"
                    }
                ],
                [
                    {
                        "text": "📄 Pratinjau Web Dashboard",
                        "url": f"{callback_base_url}/#tab-pr"
                    }
                ]
            ]
        }

        if not self.is_configured:
            logger.info(f"[TELEGRAM SIMULATION] Alert sent for PR: {pr.pr_number} to Chat ID: {self.chat_id or 'DemoManagerChat'}")
            return {
                "status": "simulated",
                "message": "Notification dispatched in simulation mode (set TELEGRAM_BOT_TOKEN in .env for real delivery).",
                "pr_number": pr.pr_number,
                "preview_text": message_text,
            }

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message_text,
            "parse_mode": "Markdown",
            "reply_markup": reply_markup
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.post(url, json=payload)
                res.raise_for_status()
                return {"status": "sent", "response": res.json()}
            except Exception as e:
                logger.error(f"Failed to send Telegram message: {e}")
                return {"status": "error", "detail": str(e)}


telegram_bot = TelegramApprovalBot()
