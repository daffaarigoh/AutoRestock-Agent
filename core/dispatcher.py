import os
import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
from typing import Dict, Any, Optional, List
import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class MultiChannelDispatcher:
    """
    Unified multi-channel integration dispatcher:
    1. n8n Webhook Hub (Sends event & structured data to n8n workflows)
    2. Email Dispatcher (Sends SMTP mail with optional PDF attachment / zero-config simulation)
    3. Telegram Bot (Sends interactive approval alerts)
    """

    @classmethod
    async def dispatch_to_n8n(
        cls,
        event_name: str,
        payload: Dict[str, Any],
        custom_webhook_url: Optional[str] = None,
        base_url: str = "http://127.0.0.1:8000"
    ) -> Dict[str, Any]:
        """
        Sends structured event payload to n8n webhook endpoint with interactive approval links.
        Falls back to simulation mode if N8N_WEBHOOK_URL is not set.
        """
        webhook_url = custom_webhook_url or settings.N8N_WEBHOOK_URL
        pr_number = payload.get("pr_number", "")
        
        # Inject standard interactive action links
        payload["approve_url"] = f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=APPROVE"
        payload["reject_url"] = f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=REJECT"
        if "pdf_url" not in payload and pr_number:
            payload["pdf_url"] = f"/api/documents/pr/{pr_number}/download"
        payload["pdf_download_url"] = f"{base_url}{payload['pdf_url']}" if payload.get("pdf_url") else ""

        envelope = {
            "source": "AutoRestock-Agent",
            "event": event_name,
            "timestamp": payload.get("created_at") or payload.get("timestamp") or "",
            "data": payload
        }

        if not webhook_url:
            msg = f"[n8n SIMULASI] Webhook '{event_name}' siap dikirim ke n8n (Pasang N8N_WEBHOOK_URL di .env untuk pengiriman langsung)."
            logger.info(msg)
            return {
                "channel": "n8n",
                "status": "simulated",
                "message": msg,
                "event": event_name,
                "payload_preview": envelope
            }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(webhook_url, json=envelope)
                res.raise_for_status()
                return {
                    "channel": "n8n",
                    "status": "success",
                    "status_code": res.status_code,
                    "event": event_name,
                    "response": res.text
                }
        except Exception as e:
            logger.warning(f"Failed to post to n8n webhook: {e}")
            return {
                "channel": "n8n",
                "status": "error",
                "message": f"Gagal menghubungi n8n: {str(e)}",
                "event": event_name
            }

    @classmethod
    async def dispatch_email(
        cls,
        recipient_email: str,
        subject: str,
        content_text: str,
        attachment_path: Optional[str] = None,
        html_content: Optional[str] = None,
        pr_number: Optional[str] = None,
        base_url: str = "http://127.0.0.1:8000"
    ) -> Dict[str, Any]:
        """
        Sends a rich HTML email notification with optional PDF attachment and interactive Approve/Reject action buttons.
        Falls back to smart simulation if SMTP credentials are not configured.
        """
        recipient = recipient_email or settings.DEFAULT_RECIPIENT_EMAIL
        is_smtp_configured = bool(settings.SMTP_EMAIL and settings.SMTP_PASSWORD)

        # Build default rich HTML if not provided
        if not html_content and pr_number:
            approve_link = f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=APPROVE"
            reject_link = f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=REJECT"
            pdf_link = f"{base_url}/api/documents/pr/{pr_number}/download"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f1f5f9; margin: 0; padding: 20px; color: #1e293b; }}
                    .card {{ background: #ffffff; max-width: 600px; margin: 0 auto; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
                    .header {{ background: #1e293b; color: #ffffff; padding: 24px; text-align: center; }}
                    .body {{ padding: 24px; }}
                    .btn-group {{ margin: 28px 0 16px 0; text-align: center; display: flex; justify-content: center; gap: 12px; }}
                    .btn {{ display: inline-block; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 14px; margin: 0 6px; }}
                    .btn-approve {{ background-color: #16a34a; color: #ffffff !important; }}
                    .btn-reject {{ background-color: #dc2626; color: #ffffff !important; }}
                    .btn-pdf {{ background-color: #2563eb; color: #ffffff !important; }}
                    .footer {{ background: #f8fafc; padding: 16px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
                    .note {{ background: #eff6ff; border-left: 4px solid #3b82f6; padding: 12px; border-radius: 4px; font-size: 13px; color: #1e40af; margin: 16px 0; }}
                </style>
            </head>
            <body>
                <div class="card">
                    <div class="header">
                        <h2 style="margin:0; font-size: 20px;">🚨 Permintaan Persetujuan Restock Otomatis</h2>
                        <p style="margin: 6px 0 0 0; font-size: 14px; color: #94a3b8;">AutoRestock-Agent Procurement System</p>
                    </div>
                    <div class="body">
                        <p>Halo Manajer Pengadaan,</p>
                        <p>Sistem AI Agent telah mendeteksi kebutuhan restock barang kritis dan mengompilasi draf resmi Purchase Requisition <strong>{pr_number}</strong>.</p>
                        
                        <div style="background: #f8fafc; border-radius: 8px; padding: 16px; margin: 16px 0; border: 1px solid #e2e8f0; white-space: pre-line; font-size: 14px;">
                            {content_text}
                        </div>

                        <div class="note">
                            💡 <strong>Interaksi Satu-Klik:</strong><br>
                            • Klik <strong>Setujui (APPROVE)</strong>: Stok inventaris di database DuckDB akan langsung ditambahkan otomatis.<br>
                            • Klik <strong>Tolak (REJECT)</strong>: Pengadaan dibatalkan dan stok gudang tetap.
                        </div>

                        <div class="btn-group">
                            <a href="{approve_link}" class="btn btn-approve" target="_blank">✅ SETUJUI (APPROVE)</a>
                            <a href="{reject_link}" class="btn btn-reject" target="_blank">❌ TOLAK (REJECT)</a>
                        </div>
                        <div style="text-align: center; margin-top: 12px;">
                            <a href="{pdf_link}" class="btn btn-pdf" target="_blank">📄 Unduh Dokumen PDF Resmi</a>
                        </div>
                    </div>
                    <div class="footer">
                        AutoRestock-Agent &bull; Terintegrasi dengan DuckDB, LangGraph, Typst, & n8n
                    </div>
                </div>
            </body>
            </html>
            """

        if not is_smtp_configured:
            attach_info = f" (dengan lampiran: {Path(attachment_path).name})" if attachment_path and Path(attachment_path).exists() else ""
            msg = f"[EMAIL SIMULASI] Email berhasil disimulasikan ke '{recipient}' | Subjek: '{subject}'{attach_info}."
            logger.info(msg)
            return {
                "channel": "email",
                "status": "simulated",
                "recipient": recipient,
                "subject": subject,
                "message": msg,
                "content_preview": content_text[:150] + "..." if len(content_text) > 150 else content_text,
                "interactive_actions": {
                    "approve_url": f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=APPROVE" if pr_number else "",
                    "reject_url": f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=REJECT" if pr_number else ""
                }
            }

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = settings.SMTP_EMAIL
            msg["To"] = recipient
            msg["Subject"] = subject

            # Attach plain text and HTML
            part1 = MIMEText(content_text, "plain")
            msg.attach(part1)
            if html_content:
                part2 = MIMEText(html_content, "html")
                msg.attach(part2)

            if attachment_path and Path(attachment_path).exists():
                with open(attachment_path, "rb") as f:
                    part = MIMEApplication(f.read(), Name=Path(attachment_path).name)
                part["Content-Disposition"] = f'attachment; filename="{Path(attachment_path).name}"'
                msg.attach(part)

            with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_EMAIL, settings.SMTP_PASSWORD)
                server.send_message(msg)

            return {
                "channel": "email",
                "status": "success",
                "recipient": recipient,
                "subject": subject,
                "message": f"Email interaktif berhasil dikirim ke {recipient}."
            }
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return {
                "channel": "email",
                "status": "error",
                "recipient": recipient,
                "message": f"Gagal mengirim email via SMTP: {str(e)}"
            }


dispatcher = MultiChannelDispatcher()

