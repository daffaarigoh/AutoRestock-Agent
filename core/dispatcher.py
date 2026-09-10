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
        leave_id: str | None = None,
        leave_data: dict[str, Any] | None = None,
        base_url: str | None = None
    ) -> dict[str, Any]:
        """
        Sends a rich HTML email notification with optional PDF attachment and interactive Approve/Reject action buttons.
        Falls back to smart simulation if SMTP credentials are not configured.
        """
        if settings.PUBLIC_URL:
            base_url = base_url or settings.PUBLIC_URL.rstrip("/")
        else:
            host = "127.0.0.1" if settings.API_HOST in ["0.0.0.0", ""] else settings.API_HOST
            base_url = base_url or f"http://{host}:{settings.API_PORT}"
        recipient = recipient_email or settings.DEFAULT_RECIPIENT_EMAIL or settings.SMTP_EMAIL or "zeiniahalfiah@gmail.com"
        is_smtp_configured = bool(settings.SMTP_EMAIL and settings.SMTP_PASSWORD)

        # Build default rich HTML for Leave Request if not provided
        if not html_content and leave_id:
            approve_link = f"{base_url}/api/approval/leave-quick-action?leave_id={leave_id}&action=APPROVE"
            reject_link = f"{base_url}/api/approval/leave-quick-action?leave_id={leave_id}&action=REJECT"
            pdf_link = f"{base_url}/api/documents/leave/{leave_id}/download"
            
            ldata = leave_data or {}
            applicant_name = ldata.get("applicant_name") or ldata.get("employee_name") or "Karyawan Pemohon"
            job_title = ldata.get("job_title") or "Staff Operasional"
            dept = ldata.get("department") or "Human Resources & Field Operations"
            start_date = ldata.get("start_date") or "-"
            end_date = ldata.get("end_date") or "-"
            days_req = ldata.get("days_requested") or 1
            reason = ldata.get("reason") or "Keperluan Pribadi / Mendesak"
            substitute = ldata.get("substitute_name") or ldata.get("substitute_employee_id") or "-"
            
            type_map = {
                "ANNUAL_LEAVE": "Cuti Tahunan",
                "SICK_LEAVE": "Cuti Sakit",
                "SPECIAL_LEAVE": "Cuti Khusus / Alasan Penting",
                "EMERGENCY_LEAVE": "Cuti Alasan Mendesak",
                "MATERNITY_LEAVE": "Cuti Melahirkan"
            }
            raw_type = str(ldata.get("leave_type") or "ANNUAL_LEAVE").upper()
            type_label = type_map.get(raw_type, raw_type)
            
            html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pengajuan Cuti Karyawan | {leave_id}</title>
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
            text-transform: uppercase;
            letter-spacing: 0.05em;
            background: #FEF3C7;
            color: #92400E;
            border-radius: 4px;
            border: 1px solid #FCD34D;
        }}
        .table-details {{
            width: 100%;
            border-collapse: collapse;
            margin: 18px 0;
            font-size: 13px;
        }}
        .table-details td {{
            padding: 9px 12px;
            border-bottom: 1px solid #E2E8F0;
        }}
        .table-details td.label {{
            color: #64748B;
            width: 38%;
            font-weight: 500;
        }}
        .table-details td.value {{
            color: #0F172A;
            font-weight: 600;
        }}
        .instruction-box {{
            background: #EFF6FF;
            border-left: 3px solid #2563EB;
            padding: 12px 16px;
            margin: 18px 0 24px 0;
            font-size: 12.5px;
            color: #1E40AF;
            line-height: 1.6;
        }}
        .btn-container {{
            margin: 28px 0 16px 0;
            text-align: center;
        }}
        .btn {{
            display: inline-block;
            padding: 11px 22px;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            border-radius: 6px;
            margin: 4px 6px;
            letter-spacing: 0.02em;
        }}
        .btn-approve {{
            background: #15803D;
            color: #FFFFFF !important;
            border: 1px solid #166534;
        }}
        .btn-reject {{
            background: #FFFFFF;
            color: #B91C1C !important;
            border: 1px solid #F87171;
        }}
        .btn-doc {{
            background: #F8FAFC;
            color: #334155 !important;
            border: 1px solid #CBD5E1;
            font-size: 12px;
            padding: 8px 16px;
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
            <p class="corp-subtitle">Divisi Human Resources & Field Operations</p>
        </div>
        <div class="email-body">
            <div class="doc-badge-row">
                <div>
                    <span style="font-size: 11px; color: #64748B; text-transform: uppercase; font-weight: 600;">Nomor Dokumen Cuti:</span><br>
                    <span class="doc-id">{leave_id}</span>
                </div>
                <div style="text-align: right;">
                    <span class="status-pill">Menunggu Persetujuan HR</span>
                </div>
            </div>

            <p style="margin-top: 0; font-size: 14px; font-weight: 600; color: #0F172A;">Kepada Yth. Tim Human Resources / Manajer Operasional,</p>
            <p style="font-size: 13.5px; color: #334155; margin-bottom: 12px;">
                Permohonan pengajuan cuti kerja baru telah diajukan melalui sistem operasional mandiri karyawan dan memerlukan peninjauan serta otorisasi resmi Anda:
            </p>

            <table class="table-details">
                <tr>
                    <td class="label">Karyawan Pemohon</td>
                    <td class="value">{applicant_name} ({job_title})</td>
                </tr>
                <tr>
                    <td class="label">Departemen</td>
                    <td class="value">{dept}</td>
                </tr>
                <tr>
                    <td class="label">Jenis Permohonan</td>
                    <td class="value">{type_label}</td>
                </tr>
                <tr>
                    <td class="label">Periode Cuti</td>
                    <td class="value">{start_date} s/d {end_date} ({days_req} hari kerja)</td>
                </tr>
                <tr>
                    <td class="label">Personil Pengganti</td>
                    <td class="value">{substitute}</td>
                </tr>
                <tr>
                    <td class="label">Alasan Cuti</td>
                    <td class="value">{reason}</td>
                </tr>
            </table>

            <div class="instruction-box">
                <strong>Ketentuan Otorisasi:</strong><br>
                1. <strong>Setujui (APPROVE)</strong>: Pengajuan cuti diverifikasi secara resmi. Status pada basis data HR dan berkas PDF otomatis diperbarui menjadi Disetujui.<br>
                2. <strong>Tolak (REJECT)</strong>: Permohonan cuti dibatalkan dan kuota cuti tahunan karyawan tidak dikurangi.
            </div>

            <div class="btn-container">
                <a href="{approve_link}" class="btn btn-approve" target="_blank">SETUJUI PERMOHONAN CUTI</a>
                <a href="{reject_link}" class="btn btn-reject" target="_blank">TOLAK PERMOHONAN</a>
            </div>
            <div style="text-align: center; margin-top: 8px;">
                <a href="{pdf_link}" class="btn btn-doc" target="_blank">Unduh Dokumen Berkas PDF Terlampir</a>
            </div>
        </div>
        <div class="corp-footer">
            <strong>PT Bali Towerindo Sentra Tbk</strong><br>
            Wisma Kodel Lantai 6, Jl. H.R. Rasuna Said Kav. B-4, Jakarta Selatan 12920<br>
            <em>Pemberitahuan otomatis dari Enterprise Operations Portal. Menekan tombol persetujuan langsung memperbarui status di database utama.</em>
        </div>
    </div>
</body>
</html>"""

        # Build default rich HTML if not provided
        elif not html_content and pr_number:
            approve_link = f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=APPROVE"
            reject_link = f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=REJECT"
            pdf_link = f"{base_url}/api/documents/pr/{pr_number}/download"
            from datetime import datetime
            today_str = datetime.now().strftime("%d %B %Y, %H:%M WIB")
            
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
            text-transform: uppercase;
            letter-spacing: 0.05em;
            background: #FEF3C7;
            color: #92400E;
            border-radius: 4px;
            border: 1px solid #FCD34D;
        }}
        .content-box {{
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 16px;
            margin: 18px 0;
            font-size: 13.5px;
            color: #334155;
            white-space: pre-line;
            line-height: 1.6;
        }}
        .instruction-box {{
            background: #EFF6FF;
            border-left: 3px solid #2563EB;
            padding: 12px 16px;
            margin: 18px 0 24px 0;
            font-size: 12.5px;
            color: #1E40AF;
        }}
        .btn-container {{
            margin: 28px 0 16px 0;
            text-align: center;
        }}
        .btn {{
            display: inline-block;
            padding: 11px 22px;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            border-radius: 6px;
            margin: 4px 6px;
            letter-spacing: 0.02em;
        }}
        .btn-approve {{
            background: #15803D;
            color: #FFFFFF !important;
            border: 1px solid #166534;
        }}
        .btn-reject {{
            background: #FFFFFF;
            color: #B91C1C !important;
            border: 1px solid #F87171;
        }}
        .btn-doc {{
            background: #F8FAFC;
            color: #334155 !important;
            border: 1px solid #CBD5E1;
            font-size: 12px;
            padding: 8px 16px;
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

            <div class="content-box">{content_text}</div>

            <div class="instruction-box">
                <strong>Ketentuan Otorisasi:</strong><br>
                1. <strong>Setujui (APPROVE)</strong>: Sistem akan segera menerbitkan Purchase Order (PO) resmi ke rekanan vendor terdaftar.<br>
                2. <strong>Tolak (REJECT)</strong>: Proses pengadaan dihentikan dan pengalokasian anggaran dibatalkan.
            </div>

            <div class="btn-container">
                <a href="{approve_link}" class="btn btn-approve" target="_blank">SETUJUI PENGAJUAN (APPROVE)</a>
                <a href="{reject_link}" class="btn btn-reject" target="_blank">TOLAK PENGAJUAN (REJECT)</a>
            </div>
            <div style="text-align: center; margin-top: 8px;">
                <a href="{pdf_link}" class="btn btn-doc" target="_blank">Unduh Dokumen Draf Resmi (PDF)</a>
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
                    "approve_url": f"{base_url}/api/approval/leave-quick-action?leave_id={leave_id}&action=APPROVE" if leave_id else (f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=APPROVE" if pr_number else ""),
                    "reject_url": f"{base_url}/api/approval/leave-quick-action?leave_id={leave_id}&action=REJECT" if leave_id else (f"{base_url}/api/approval/quick-action?pr_number={pr_number}&action=REJECT" if pr_number else ""),
                    "pdf_url": f"{base_url}/api/documents/leave/{leave_id}/download" if leave_id else (f"{base_url}/api/documents/pr/{pr_number}/download" if pr_number else "")
                }
            }

        try:
            if attachment_path and Path(attachment_path).exists():
                msg = MIMEMultipart("mixed")
                msg["From"] = settings.SMTP_EMAIL
                msg["To"] = recipient
                msg["Subject"] = subject

                alt_part = MIMEMultipart("alternative")
                alt_part.attach(MIMEText(content_text, "plain"))
                if html_content:
                    alt_part.attach(MIMEText(html_content, "html"))
                msg.attach(alt_part)

                with open(attachment_path, "rb") as f:
                    part = MIMEApplication(f.read(), Name=Path(attachment_path).name)
                part["Content-Disposition"] = f'attachment; filename="{Path(attachment_path).name}"'
                msg.attach(part)
            else:
                msg = MIMEMultipart("alternative")
                msg["From"] = settings.SMTP_EMAIL
                msg["To"] = recipient
                msg["Subject"] = subject
                msg.attach(MIMEText(content_text, "plain"))
                if html_content:
                    msg.attach(MIMEText(html_content, "html"))

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
                "message": f"Gagal mengirim email via SMTP: {e!s}"
            }


dispatcher = MultiChannelDispatcher()

