import os
import re
from pathlib import Path

import typst

from agents.state import PurchaseRequisition

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = WORKSPACE_DIR / "docgen" / "templates" / "purchase_requisition.typ"
PO_TEMPLATE_PATH = WORKSPACE_DIR / "docgen" / "templates" / "purchase_order.typ"
STORAGE_DIR = WORKSPACE_DIR / "storage"

# Structured sub-folders for documents
PENDING_DIR = STORAGE_DIR / "pending"
APPROVED_DIR = STORAGE_DIR / "approved"
REJECTED_DIR = STORAGE_DIR / "rejected"
PO_STORAGE_DIR = STORAGE_DIR / "purchase_orders"


def ensure_storage_directories():
    """Ensure structured storage directories exist."""
    os.makedirs(STORAGE_DIR, exist_ok=True)
    os.makedirs(PENDING_DIR, exist_ok=True)
    os.makedirs(APPROVED_DIR, exist_ok=True)
    os.makedirs(REJECTED_DIR, exist_ok=True)
    os.makedirs(PO_STORAGE_DIR, exist_ok=True)


def format_currency(amount: float) -> str:
    """Format float to Indonesian Rupiah currency string (e.g., Rp 1.250.000)."""
    return f"Rp {amount:,.0f}".replace(",", ".")


def escape_typst(text: str) -> str:
    """Escape special characters for Typst text blocks to prevent unclosed delimiter syntax errors."""
    if text is None:
        return ""
    s = str(text).replace("\\", "\\\\")
    for char in ["[", "]", "_", "*", "@", "$", "#"]:
        s = s.replace(char, "\\" + char)
    return s


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


def angka_ke_terbilang(bilangan: int | float) -> str:
    """Mengubah nominal angka ke bentuk kata terbilang dalam Bahasa Indonesia formal."""
    angka = ["", "Satu", "Dua", "Tiga", "Empat", "Lima", "Enam", "Tujuh", "Delapan", "Sembilan", "Sepuluh", "Sebelas"]
    def _terbilang(n: int) -> str:
        if n < 12:
            return angka[n]
        elif n < 20:
            return _terbilang(n - 10) + " Belas"
        elif n < 100:
            return _terbilang(n // 10) + " Puluh " + _terbilang(n % 10)
        elif n < 200:
            return "Seratus " + _terbilang(n - 100)
        elif n < 1000:
            return _terbilang(n // 100) + " Ratus " + _terbilang(n % 100)
        elif n < 2000:
            return "Seribu " + _terbilang(n - 1000)
        elif n < 1000000:
            return _terbilang(n // 1000) + " Ribu " + _terbilang(n % 1000)
        elif n < 1000000000:
            return _terbilang(n // 1000000) + " Juta " + _terbilang(n % 1000000)
        elif n < 1000000000000:
            return _terbilang(n // 1000000000) + " Miliar " + _terbilang(n % 1000000000)
        else:
            return str(n)
    res = " ".join(_terbilang(int(bilangan)).split()).strip()
    return f"{res} Rupiah" if res else "Nol Rupiah"


def generate_po_pdf(po_input: str | dict, output_path: str | Path | None = None) -> str:
    """
    Renders an official Purchase Order (PO) into a Typst document and compiles it to PDF.
    Can accept either a po_id (e.g. 'PO-2026-006' or 'PO/BLT/2026/03/008') or a full dict.
    Returns the absolute string path of the generated PDF.
    """
    ensure_storage_directories()
    from database.db import get_db_connection

    po_dict = {}
    if isinstance(po_input, str):
        conn = get_db_connection(read_only=True)
        try:
            # Exact match first
            row = conn.execute("""
                SELECT po.po_id, po.po_number, po.supplier_id, COALESCE(s.supplier_name, po.supplier_id) AS supplier_name, COALESCE(s.category, 'General') AS sup_cat,
                       COALESCE(s.phone, '-') AS phone, COALESCE(s.email, '-') AS email, COALESCE(s.payment_terms, 'Net 30') AS payment_terms, po.item_id, COALESCE(i.item_name, po.item_id) AS item_name, COALESCE(i.item_code, po.item_id) AS item_code,
                       COALESCE(i.category, 'Logistics') AS item_cat, COALESCE(i.unit, 'pcs') AS unit, po.order_quantity, po.unit_price, po.total_amount,
                       po.status, po.order_date, po.expected_delivery, po.actual_delivery,
                       po.warehouse_id, COALESCE(w.warehouse_name, po.warehouse_id) AS warehouse_name, COALESCE(w.region, 'DKI Jakarta') AS region, COALESCE(w.address, 'Jl. Logistics Hub') AS address, COALESCE(w.supervisor, 'Manager Logistik') AS supervisor
                FROM purchase_orders po
                LEFT JOIN suppliers s ON po.supplier_id = s.supplier_id
                LEFT JOIN inventory_items i ON po.item_id = i.item_id
                LEFT JOIN warehouses w ON po.warehouse_id = w.warehouse_id
                WHERE UPPER(po.po_id) = ? OR UPPER(po.po_number) = ?;
            """, [po_input.upper(), po_input.upper()]).fetchone()
            
            # Fallback to trailing digits or partial lookup (e.g. PO-2026-032 -> 032)
            if not row:
                digits = re.findall(r'\d+', po_input)
                last_num = digits[-1].zfill(3) if digits else po_input
                row = conn.execute("""
                    SELECT po.po_id, po.po_number, po.supplier_id, COALESCE(s.supplier_name, po.supplier_id) AS supplier_name, COALESCE(s.category, 'General') AS sup_cat,
                           COALESCE(s.phone, '-') AS phone, COALESCE(s.email, '-') AS email, COALESCE(s.payment_terms, 'Net 30') AS payment_terms, po.item_id, COALESCE(i.item_name, po.item_id) AS item_name, COALESCE(i.item_code, po.item_id) AS item_code,
                           COALESCE(i.category, 'Logistics') AS item_cat, COALESCE(i.unit, 'pcs') AS unit, po.order_quantity, po.unit_price, po.total_amount,
                           po.status, po.order_date, po.expected_delivery, po.actual_delivery,
                           po.warehouse_id, COALESCE(w.warehouse_name, po.warehouse_id) AS warehouse_name, COALESCE(w.region, 'DKI Jakarta') AS region, COALESCE(w.address, 'Jl. Logistics Hub') AS address, COALESCE(w.supervisor, 'Manager Logistik') AS supervisor
                    FROM purchase_orders po
                    LEFT JOIN suppliers s ON po.supplier_id = s.supplier_id
                    LEFT JOIN inventory_items i ON po.item_id = i.item_id
                    LEFT JOIN warehouses w ON po.warehouse_id = w.warehouse_id
                    WHERE po.po_number LIKE ? OR po.po_id LIKE ?;
                """, [f"%{last_num}%", f"%{last_num}%"]).fetchone()

            if not row:
                raise ValueError(f"Purchase Order '{po_input}' tidak ditemukan di database.")
            cols = [
                "po_id", "po_number", "supplier_id", "supplier_name", "sup_cat",
                "phone", "email", "payment_terms", "item_id", "item_name", "item_code",
                "item_cat", "unit", "order_quantity", "unit_price", "total_amount",
                "status", "order_date", "expected_delivery", "actual_delivery",
                "warehouse_id", "warehouse_name", "region", "address", "supervisor"
            ]
            po_dict = dict(zip(cols, row))
        finally:
            conn.close()
    elif isinstance(po_input, dict):
        po_dict = po_input
    else:
        raise ValueError("po_input must be a string (po_id) or dict.")

    po_id = po_dict.get("po_id", "PO-UNKNOWN")
    clean_po_id = po_id.replace("/", "_").replace("\\", "_")
    if output_path is None:
        output_file = PO_STORAGE_DIR / f"{clean_po_id}.pdf"
    else:
        output_file = Path(output_path)

    # Read base Typst template
    with open(PO_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template_str = f.read()

    # Financial calculations
    subtotal = float(po_dict.get("total_amount", 0))
    ppn = round(subtotal * 0.11)
    grand_total = subtotal + ppn
    terbilang = angka_ke_terbilang(grand_total)

    # Build items table row
    item_code_esc = escape_typst(po_dict.get("item_code", ""))
    item_name_esc = escape_typst(po_dict.get("item_name", ""))
    category_esc = escape_typst(po_dict.get("item_cat") or po_dict.get("category", ""))
    unit_esc = escape_typst(po_dict.get("unit", "pcs"))
    qty = int(po_dict.get("order_quantity", 1))
    unit_price = float(po_dict.get("unit_price", 0))

    items_row = f"""    [1],
    [{item_code_esc}],
    [*{item_name_esc}*],
    [{category_esc}],
    [*{qty:,}* {unit_esc}],
    [{format_currency(unit_price)}],
    [*{format_currency(subtotal)}*],"""

    actual_deliv = po_dict.get("actual_delivery")
    actual_deliv_str = str(actual_deliv) if actual_deliv else "-"

    rendered_typst = (
        template_str
        .replace("{{PO_NUMBER}}", escape_typst(po_dict.get("po_number", "-")))
        .replace("{{PO_ID}}", escape_typst(po_dict.get("po_id", "-")))
        .replace("{{ORDER_DATE}}", escape_typst(po_dict.get("order_date", "-")))
        .replace("{{STATUS}}", escape_typst(po_dict.get("status", "ORDERED")))
        .replace("{{SUPPLIER_NAME}}", escape_typst(po_dict.get("supplier_name", "-")))
        .replace("{{SUPPLIER_ID}}", escape_typst(po_dict.get("supplier_id", "-")))
        .replace("{{SUPPLIER_CATEGORY}}", escape_typst(po_dict.get("sup_cat") or po_dict.get("category", "-")))
        .replace("{{SUPPLIER_PHONE}}", escape_typst(po_dict.get("phone", "-")))
        .replace("{{SUPPLIER_EMAIL}}", escape_typst(po_dict.get("email", "-")))
        .replace("{{PAYMENT_TERMS}}", escape_typst(po_dict.get("payment_terms", "Net 30")))
        .replace("{{WAREHOUSE_NAME}}", escape_typst(po_dict.get("warehouse_name", "-")))
        .replace("{{WAREHOUSE_ID}}", escape_typst(po_dict.get("warehouse_id", "-")))
        .replace("{{WAREHOUSE_REGION}}", escape_typst(po_dict.get("region", "-")))
        .replace("{{WAREHOUSE_ADDRESS}}", escape_typst(po_dict.get("address", "-")))
        .replace("{{WAREHOUSE_SUPERVISOR}}", escape_typst(po_dict.get("supervisor", "Logistics Lead")))
        .replace("{{EXPECTED_DELIVERY}}", escape_typst(po_dict.get("expected_delivery", "-")))
        .replace("{{ACTUAL_DELIVERY}}", escape_typst(actual_deliv_str))
        .replace("{{ITEMS_TABLE_ROWS}}", items_row)
        .replace("{{SUBTOTAL_FMT}}", format_currency(subtotal))
        .replace("{{PPN_FMT}}", format_currency(ppn))
        .replace("{{GRAND_TOTAL_FMT}}", format_currency(grand_total))
        .replace("{{TERBILANG_WORDS}}", escape_typst(terbilang))
    )

    temp_typ_file = STORAGE_DIR / f"temp_{clean_po_id}.typ"
    with open(temp_typ_file, "w", encoding="utf-8") as f:
        f.write(rendered_typst)

    try:
        output_file_str = str(output_file.resolve().as_posix())
        typst.compile(
            input=str(temp_typ_file.resolve().as_posix()),
            output=output_file_str
        )
        print(f"[DOCGEN] Successfully generated PO PDF to: {output_file_str}")
    finally:
        if temp_typ_file.exists():
            try:
                temp_typ_file.unlink()
            except Exception:
                pass

    return str(output_file.resolve().as_posix())
