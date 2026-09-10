import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


def _format_markdown_to_html(text: str) -> str:
    """Converts markdown (headings, bold, tables, code) into clean inline-styled HTML for email clients."""
    if not text:
        return ""
    import re
    lines = text.strip().split("\n")
    html_out = []
    in_table = False
    table_rows = []

    def flush_table(t_rows):
        if not t_rows:
            return ""
        tbl_html = ['<div style="overflow-x: auto; margin: 16px 0;"><table style="width: 100%; border-collapse: collapse; font-size: 12.5px; font-family: inherit; border: 1px solid #E2E8F0; background: #FFFFFF;">']
        for idx, row in enumerate(t_rows):
            cols = [c.strip() for c in row.split("|")[1:-1]]
            if not cols or all(re.match(r'^:?-+:?$', c) for c in cols):
                continue
            if idx == 0:
                tbl_html.append('<tr style="background: #F8FAFC; color: #334155; font-weight: 700; border-bottom: 2px solid #CBD5E1;">')
                for c in cols:
                    tbl_html.append(f'<th style="padding: 10px 12px; border: 1px solid #E2E8F0; text-align: left;">{_format_inline(c)}</th>')
                tbl_html.append('</tr>')
            else:
                bg = "#F8FAFC" if idx % 2 == 1 else "#FFFFFF"
                tbl_html.append(f'<tr style="background: {bg}; border-bottom: 1px solid #E2E8F0;">')
                for c in cols:
                    tbl_html.append(f'<td style="padding: 8px 12px; border: 1px solid #E2E8F0;">{_format_inline(c)}</td>')
                tbl_html.append('</tr>')
        tbl_html.append('</table></div>')
        return "".join(tbl_html)

    def _format_inline(s: str) -> str:
        s = re.sub(r'`([^`]+)`', r'<code style="background: #F1F5F9; color: #2563EB; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 11.5px;">\1</code>', s)
        s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
        s = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', s)
        return s

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            in_table = True
            table_rows.append(stripped)
        else:
            if in_table:
                html_out.append(flush_table(table_rows))
                table_rows = []
                in_table = False

            if stripped.startswith("### "):
                html_out.append(f'<h3 style="color: #0F172A; font-size: 15px; font-weight: 700; margin: 18px 0 8px 0;">{_format_inline(stripped[4:])}</h3>')
            elif stripped.startswith("## "):
                html_out.append(f'<h2 style="color: #0F172A; font-size: 17px; font-weight: 700; margin: 20px 0 10px 0;">{_format_inline(stripped[3:])}</h2>')
            elif stripped.startswith("# "):
                html_out.append(f'<h1 style="color: #0F172A; font-size: 19px; font-weight: 800; margin: 22px 0 12px 0;">{_format_inline(stripped[2:])}</h1>')
            elif stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2:
                html_out.append(f'<p style="color: #64748B; font-size: 12.5px; font-style: italic; margin: 6px 0;">{_format_inline(stripped[1:-1])}</p>')
            elif stripped:
                html_out.append(f'<p style="color: #334155; font-size: 13px; line-height: 1.6; margin: 8px 0;">{_format_inline(stripped)}</p>')
            else:
                html_out.append('<div style="height: 6px;"></div>')

    if in_table:
        html_out.append(flush_table(table_rows))

    return "".join(html_out)


class MultiChannelDispatcher:
    """
    Unified multi-channel integration dispatcher:
    1. DuckDB Database (Saves structured historical data and tracks workflow progress)
    2. Email Dispatcher (Sends SMTP mail with optional PDF attachment / zero-config simulation)
    """

    @classmethod
    async def dispatch_email(
        cls,
        recipient_email: str | None = None,
        subject: str = "Notifikasi Pengadaan Inventaris",
        content_text: str = "",
        attachment_path: str | None = None,
        html_content: str | None = None,
        pr_number: str | None = None,
        base_url: str | None = None
    ) -> dict[str, Any]:
        """
        Sends a rich HTML email notification with optional PDF attachment and interactive Approve/Reject action buttons.
        Falls back to smart simulation if SMTP credentials are not configured.
        """
        import re
        if settings.PUBLIC_URL:
            base_url = base_url or settings.PUBLIC_URL.rstrip("/")
        else:
            host = "127.0.0.1" if settings.API_HOST in ["0.0.0.0", ""] else settings.API_HOST
            base_url = base_url or f"http://{host}:{settings.API_PORT}"
        recipient = recipient_email or settings.DEFAULT_RECIPIENT_EMAIL
        is_smtp_configured = bool(settings.SMTP_EMAIL and settings.SMTP_PASSWORD)

        # Auto-detect PR number from subject, attachment_path, or content_text if not explicitly given
        if not pr_number:
            candidates = [attachment_path or "", subject or "", content_text or ""]
            for cand in candidates:
                m = re.search(r'\b(PR[-_]\d{8}[-_]\d{6}|PR[-_]\d{4}[-_]\d{3})\b', cand)
                if m:
                    pr_number = m.group(1).replace('_', '-')
                    break

        # Build default rich HTML if not provided
        if not html_content:
            if pr_number:
                approve_link = f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=APPROVE"
                reject_link = f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=REJECT"
                pdf_link = f"{base_url}/api/documents/pr/{pr_number}/download"
                
                formatted_body = _format_markdown_to_html(content_text)
                html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pemberitahuan Pengadaan Barang | {pr_number}</title>
    <style>
        body {{
            margin: 0;
            padding: 24px 12px;
            background-color: #F1F5F9;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            color: #0F172A;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }}
        .email-wrapper {{
            max-width: 620px;
            margin: 0 auto;
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        }}
        .corp-header {{
            background: #0F172A;
            color: #FFFFFF;
            padding: 22px 28px;
            border-bottom: 3px solid #2563EB;
        }}
        .corp-title {{
            font-size: 15px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin: 0;
            color: #F8FAFC;
        }}
        .corp-subtitle {{
            font-size: 12px;
            color: #94A3B8;
            margin: 4px 0 0 0;
            letter-spacing: 0.02em;
        }}
        .email-body {{
            padding: 28px;
        }}
        .doc-badge-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 14px;
            border-bottom: 1px solid #E2E8F0;
        }}
        .doc-id {{
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 13px;
            font-weight: 700;
            color: #1D4ED8;
        }}
        .status-pill {{
            display: inline-block;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 700;
            background: #FEF3C7;
            color: #92400E;
            border: 1px solid #FCD34D;
            border-radius: 4px;
        }}
        .instruction-box {{
            background: #EFF6FF;
            border-left: 3px solid #2563EB;
            padding: 12px 16px;
            margin: 18px 0 24px 0;
            font-size: 12.5px;
            color: #1E40AF;
        }}
        .corp-footer {{
            background: #F8FAFC;
            border-top: 1px solid #E2E8F0;
            padding: 18px 28px;
            font-size: 11.5px;
            color: #64748B;
            line-height: 1.6;
        }}
    </style>
</head>
<body>
    <div class="email-wrapper">
        <div class="corp-header">
            <h1 class="corp-title">PT Bali Towerindo Sentra Tbk</h1>
            <p class="corp-subtitle">Divisi Supply Chain Management & Pengadaan Logistik</p>
        </div>
        <div class="email-body">
            <div class="doc-badge-row">
                <div>
                    <span style="font-size: 11px; color: #64748B; text-transform: uppercase; font-weight: 600;">Nomor Dokumen:</span><br>
                    <span class="doc-id">{pr_number}</span>
                </div>
                <div style="text-align: right;">
                    <span class="status-pill">Menunggu Otorisasi</span>
                </div>
            </div>

            <p style="margin-top: 0; font-size: 14px; font-weight: 600; color: #0F172A;">Kepada Yth. Leader / Manajer Operasional Pengadaan,</p>
            <p style="font-size: 13.5px; color: #334155; margin-bottom: 12px;">
                Sistem monitoring logistik mendeteksi ketersediaan material infrastruktur telah menyentuh batas minimum stok kerja (Reorder Point). Dokumen pengajuan pembelian (Purchase Requisition) resmi telah disusun untuk permohonan persetujuan Anda:
            </p>

            <div style="margin: 16px 0;">{formatted_body}</div>

            <div class="instruction-box">
                <strong>Ketentuan Otorisasi:</strong><br>
                1. <strong>Setujui (APPROVE)</strong>: Sistem akan segera menerbitkan Purchase Order (PO) resmi ke rekanan vendor terdaftar.<br>
                2. <strong>Tolak (REJECT)</strong>: Proses pengadaan dihentikan dan pengalokasian anggaran dibatalkan.
            </div>

            <div style="margin: 28px 0 16px 0; text-align: center;">
                <a href="{approve_link}" style="display: inline-block; padding: 12px 24px; font-size: 13px; font-weight: 700; color: #FFFFFF !important; background-color: #15803D; border: 1px solid #166534; border-radius: 6px; text-decoration: none; margin: 4px 6px; letter-spacing: 0.02em;" target="_blank">SETUJUI PENGAJUAN (APPROVE)</a>
                <a href="{reject_link}" style="display: inline-block; padding: 12px 24px; font-size: 13px; font-weight: 700; color: #B91C1C !important; background-color: #FFFFFF; border: 1px solid #F87171; border-radius: 6px; text-decoration: none; margin: 4px 6px; letter-spacing: 0.02em;" target="_blank">TOLAK PENGAJUAN (REJECT)</a>
            </div>
            <div style="text-align: center; margin-top: 8px;">
                <a href="{pdf_link}" style="display: inline-block; padding: 10px 20px; font-size: 12px; font-weight: 600; color: #2563EB !important; background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 6px; text-decoration: none; margin: 4px 6px;" target="_blank">Unduh Dokumen Draf Resmi (PDF)</a>
            </div>
        </div>
        <div class="corp-footer">
            <strong>PT Bali Towerindo Sentra Tbk</strong><br>
            Wisma Kodel Lantai 7, Jl. H.R. Rasuna Said Kav. B-4, Jakarta Selatan 12920<br>
            <em>Pemberitahuan otomatis dari Enterprise Operations Command Center. Tidak memerlukan balasan email.</em>
        </div>
    </div>
</body>
</html>"""
            else:
                formatted_body = _format_markdown_to_html(content_text)
                html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
    <style>
        body {{
            margin: 0;
            padding: 24px 12px;
            background-color: #F1F5F9;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: #0F172A;
            line-height: 1.5;
        }}
        .email-wrapper {{
            max-width: 650px;
            margin: 0 auto;
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        }}
        .corp-header {{
            background: #0F172A;
            color: #FFFFFF;
            padding: 20px 24px;
            border-bottom: 3px solid #2563EB;
        }}
        .corp-title {{
            font-size: 15px;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            margin: 0;
            color: #F8FAFC;
        }}
        .corp-subtitle {{
            font-size: 12px;
            color: #94A3B8;
            margin: 4px 0 0 0;
        }}
        .email-body {{
            padding: 24px;
        }}
        .corp-footer {{
            background: #F8FAFC;
            border-top: 1px solid #E2E8F0;
            padding: 16px 24px;
            font-size: 11.5px;
            color: #64748B;
            line-height: 1.6;
        }}
    </style>
</head>
<body>
    <div class="email-wrapper">
        <div class="corp-header">
            <h1 class="corp-title">PT Bali Towerindo Sentra Tbk</h1>
            <p class="corp-subtitle">Enterprise Operations Command Center & Logistics</p>
        </div>
        <div class="email-body">
            {formatted_body}
            <div style="text-align: center; margin: 24px 0 8px 0;">
                <a href="{base_url}/admin" style="display: inline-block; padding: 11px 22px; font-size: 12.5px; font-weight: 600; color: #FFFFFF !important; background-color: #2563EB; border-radius: 6px; text-decoration: none;" target="_blank">Buka Portal Manajemen Logistik</a>
            </div>
        </div>
        <div class="corp-footer">
            <strong>PT Bali Towerindo Sentra Tbk</strong><br>
            Wisma Kodel Lantai 7, Jl. H.R. Rasuna Said Kav. B-4, Jakarta Selatan 12920<br>
            <em>Pemberitahuan otomatis dari Enterprise Operations Command Center.</em>
        </div>
    </div>
</body>
</html>"""

        if not is_smtp_configured:
            attach_info = f" (dengan lampiran: {Path(attachment_path).name})" if attachment_path and Path(attachment_path).exists() else ""
            msg = f"[EMAIL SIMULASI] Email berhasil disimulasikan ke '{recipient}' | Subjek: '{subject}'{attach_info}."
            logger.info(msg)
            return {
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
            # RFC 2046 Standard: multipart/mixed at top level allows both multipart/alternative (text/html) and binary attachments
            outer = MIMEMultipart("mixed")
            outer["From"] = settings.SMTP_EMAIL
            outer["To"] = recipient
            outer["Subject"] = subject

            # Child alternative container for plain text and HTML representation
            body_alt = MIMEMultipart("alternative")
            part1 = MIMEText(content_text or "", "plain", "utf-8")
            body_alt.attach(part1)
            if html_content:
                part2 = MIMEText(html_content, "html", "utf-8")
                body_alt.attach(part2)
            outer.attach(body_alt)

            # Physical attachment (Typst PDF / document)
            if attachment_path and Path(attachment_path).exists():
                file_p = Path(attachment_path)
                with open(file_p, "rb") as f:
                    part_attach = MIMEApplication(f.read(), Name=file_p.name)
                part_attach["Content-Disposition"] = f'attachment; filename="{file_p.name}"'
                outer.attach(part_attach)
                logger.info(f"Attached document '{file_p.name}' to email for {recipient}")

            with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=15) as server:
                server.starttls()
                server.login(settings.SMTP_EMAIL, settings.SMTP_PASSWORD)
                server.send_message(outer)

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
                "message": f"Gagal mengirim email via SMTP: {e!s}"
            }


dispatcher = MultiChannelDispatcher()

