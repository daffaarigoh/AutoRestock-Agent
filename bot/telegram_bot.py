"""
Telegram Bot Integration Module
Provides two-way manager approvals, stock alerts, and interactive bot commands.
"""

import httpx
from typing import Optional, Dict, Any
from core.config import settings
from core.schemas import PurchaseRequisition, DiscrepancyReport, PRStatus
from core.observability import log_agent_step
from database.db import db


class TelegramBot:
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""

    async def send_message(self, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> bool:
        """Sends a notification message to the configured manager Telegram chat."""
        if not self.token or not self.chat_id:
            # Fallback logging if token is not set in development
            log_agent_step(
                step_name="Telegram Dispatch (Simulated)",
                agent_name="TelegramBot",
                status="info",
                message=f"[Mock Telegram Alert]: {text[:100]}..."
            )
            return True

        try:
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{self.base_url}/sendMessage", json=payload)
                return resp.status_code == 200
        except Exception as e:
            log_agent_step(
                step_name="Telegram Dispatch",
                agent_name="TelegramBot",
                status="error",
                message=f"Failed to send Telegram message: {str(e)}"
            )
            return False

    async def send_pr_alert(self, pr: PurchaseRequisition) -> bool:
        """Sends an interactive PR approval request with approve/reject buttons."""
        items_preview = "\n".join([f"• {it.item_name} ({it.quantity} {it.unit})" for it in pr.items[:4]])
        if len(pr.items) > 4:
            items_preview += f"\n• ... dan {len(pr.items) - 4} item lainnya"

        text = (
            f"🔔 <b>PERMINTAAN PERSETUJUAN PO (PR)</b>\n\n"
            f"<b>Nomor PR:</b> <code>{pr.pr_number}</code>\n"
            f"<b>Supplier:</b> {pr.supplier_name}\n"
            f"<b>Total:</b> Rp {pr.grand_total:,.0f}\n"
            f"<b>Urgensi:</b> {pr.urgency}\n\n"
            f"<b>Item yang dipesan:</b>\n{items_preview}\n\n"
            f"Silakan tinjau dan lakukan konfirmasi persetujuan."
        )

        inline_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Setujui PR", "callback_data": f"approve_{pr.pr_number}"},
                    {"text": "❌ Tolak PR", "callback_data": f"reject_{pr.pr_number}"}
                ]
            ]
        }

        return await self.send_message(text, reply_markup=inline_keyboard)

    async def send_discrepancy_alert(self, report: DiscrepancyReport) -> bool:
        """Sends an alert when warehouse audit discrepancies are detected."""
        disc_text = "\n".join([f"⚠️ {d.item_name}: Selisih {d.diff_quantity:+d} ({d.reason})" for d in report.discrepancies])
        text = (
            f"🚨 <b>PERINGATAN AUDIT GUDANG</b>\n\n"
            f"<b>Dokumen:</b> <code>{report.doc_number}</code> ({report.doc_type.value})\n"
            f"<b>Total Selisih:</b> {report.total_discrepancies} item\n\n"
            f"{disc_text}\n\n"
            f"Tindakan fisik recount diperlukan."
        )
        return await self.send_message(text)


telegram_bot = TelegramBot()
