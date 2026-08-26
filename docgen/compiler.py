import os
from pathlib import Path

import typst

from agents.state import PurchaseRequisition

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = WORKSPACE_DIR / "docgen" / "templates" / "purchase_requisition.typ"
STORAGE_DIR = WORKSPACE_DIR / "storage"

# Structured sub-folders for documents
PENDING_DIR = STORAGE_DIR / "pending"
APPROVED_DIR = STORAGE_DIR / "approved"
REJECTED_DIR = STORAGE_DIR / "rejected"


def ensure_storage_directories():
    """Ensure structured storage directories exist."""
    os.makedirs(STORAGE_DIR, exist_ok=True)
    os.makedirs(PENDING_DIR, exist_ok=True)
    os.makedirs(APPROVED_DIR, exist_ok=True)
    os.makedirs(REJECTED_DIR, exist_ok=True)


def format_currency(amount: float) -> str:
    """Format float to Indonesian Rupiah currency string (e.g., Rp 1.250.000)."""
    return f"Rp {amount:,.0f}".replace(",", ".")


def escape_typst(text: str) -> str:
    """Escape special characters for Typst text blocks."""
    if text is None:
        return ""
    return str(text).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("$", "\\$").replace("#", "\\#")


def get_target_directory(status: str) -> Path:
    """Determine target storage sub-folder based on PR status."""
    status_upper = (status or "PENDING").upper()
    if "APPROV" in status_upper and "PENDING" not in status_upper:
        return APPROVED_DIR
    elif "REJECT" in status_upper:
        return REJECTED_DIR
    else:
        return PENDING_DIR


def generate_pr_pdf(pr: PurchaseRequisition | dict, output_path: str | Path | None = None) -> str:
    """
    Renders a PurchaseRequisition model into a Typst document and compiles it to PDF.
    Saves PDF into storage/pending/, storage/approved/, or storage/rejected/ based on status.
    File naming is cleanly {pr_number}.pdf.
    
    :param pr: PurchaseRequisition object or dict
    :param output_path: Optional custom output path for PDF
    :return: Absolute string path of generated PDF
    """
    if isinstance(pr, dict):
        pr = PurchaseRequisition(**pr)

    ensure_storage_directories()

    clean_pr_num = pr.pr_number.replace("/", "_").replace("\\", "_")
    
    if output_path is None:
        target_dir = get_target_directory(pr.status)
        output_file = target_dir / f"{clean_pr_num}.pdf"
    else:
        output_file = Path(output_path)

    # Read base Typst template
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        typst_content = f.read()

    # Build Typst table rows
    table_rows = []
    for idx, item in enumerate(pr.items, start=1):
        item_id_esc = escape_typst(item.item_id)
        name_esc = escape_typst(item.name)
        reason_esc = escape_typst(item.reason)
        vendor_esc = escape_typst(item.vendor_name)
        unit_esc = escape_typst(item.unit)
        unit_price_fmt = format_currency(item.unit_price)
        total_price_fmt = format_currency(item.total_price)

        row_str = f"""    [{idx}],
    [{item_id_esc}],
    [*{name_esc}*\\
    #text(size: 7.5pt, fill: rgb("#64748b"))[{reason_esc}]],
    [{item.current_stock} {unit_esc}],
    [*{item.reorder_qty}* {unit_esc}],
    [{vendor_esc}],
    [{unit_price_fmt}],
    [*{total_price_fmt}*],"""
        table_rows.append(row_str)

    items_table_block = "\n".join(table_rows)

    # Replace placeholders in template
    rendered_typst = (
        typst_content
        .replace("{{PR_NUMBER}}", escape_typst(pr.pr_number))
        .replace("{{CREATED_AT}}", escape_typst(pr.created_at))
        .replace("{{STATUS}}", escape_typst(pr.status))
        .replace("{{TOTAL_ITEMS}}", str(len(pr.items)))
        .replace("{{TOTAL_BUDGET}}", format_currency(pr.total_budget))
        .replace("{{AUDITOR_STATUS}}", escape_typst(pr.auditor_status))
        .replace("{{AUDITOR_NOTES}}", escape_typst(pr.auditor_notes))
        .replace("{{ITEMS_TABLE_ROWS}}", items_table_block)
    )

    # Write temporary rendered typst file and compile to PDF
    temp_typ_file = STORAGE_DIR / f"{clean_pr_num}_{pr.status}_rendered.typ"
    with open(temp_typ_file, "w", encoding="utf-8") as f:
        f.write(rendered_typst)

    try:
        output_file_str = str(output_file.resolve().as_posix())
        typst.compile(
            input=str(temp_typ_file.resolve().as_posix()),
            output=output_file_str
        )
        print(f"[DOCGEN] Successfully saved ({pr.status}) PDF to: {output_file_str}")
    finally:
        if temp_typ_file.exists():
            try:
                temp_typ_file.unlink()
            except Exception:
                pass

    return str(output_file.resolve().as_posix())
