import asyncio
import sys
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from core.security import TokenData
from agents.autonomous_agent import AutonomousAgent


def test_format_table_markdown():
    """Verify format_table_markdown correctly translates headers and formats status badges."""
    cols = ["balance_id", "item_code", "item_name", "category", "unit", "quantity_on_hand", "reorder_point", "stock_status", "warehouse_name"]
    data = [
        {
            "balance_id": "STK-001",
            "item_code": "GEN-PORT-5KV",
            "item_name": "Genset Silent Portable Diesel 5kVA Single Phase",
            "category": "Power & Battery",
            "unit": "unit",
            "quantity_on_hand": 1,
            "reorder_point": 6,
            "stock_status": "CRITICAL",
            "warehouse_name": "Regional Logistics Hub Medan"
        },
        {
            "balance_id": "STK-002",
            "item_code": "RECT-MOD-48V",
            "item_name": "Rectifier System Module 48V 50A Hot-Swappable",
            "category": "Power & Battery",
            "unit": "unit",
            "quantity_on_hand": 2,
            "reorder_point": 12,
            "stock_status": "CRITICAL",
            "warehouse_name": "Regional Logistics Hub Bandung"
        },
        {
            "balance_id": "STK-003",
            "item_code": "ODC-144-MOD",
            "item_name": "Optical Distribution Cabinet 144 Port Outdoor",
            "category": "Fiber Optic & Cable",
            "unit": "unit",
            "quantity_on_hand": 6,
            "reorder_point": 10,
            "stock_status": "LOW_STOCK",
            "warehouse_name": "Regional Logistics Hub Bandung"
        }
    ]
    md = AutonomousAgent.format_table_markdown(cols, data)
    assert "| No |" in md
    assert "Kode Item" in md
    assert "Nama Material" in md
    assert "CRITICAL" in md
    assert "LOW STOCK" in md
    # Surrogate ID should be filtered out
    assert "ID Saldo" not in md


def test_format_tool_result_as_markdown_db_query():
    """Verify tool_query_database result is formatted with header, table, and recommendations."""
    tool_result = {
        "columns": ["item_code", "item_name", "stock_status", "quantity_on_hand", "reorder_point", "warehouse_name"],
        "rows_count": 2,
        "data": [
            {"item_code": "GEN-01", "item_name": "Genset", "stock_status": "CRITICAL", "quantity_on_hand": 1, "reorder_point": 5, "warehouse_name": "Medan"},
            {"item_code": "BAT-01", "item_name": "Baterai", "stock_status": "LOW_STOCK", "quantity_on_hand": 3, "reorder_point": 10, "warehouse_name": "Bandung"}
        ]
    }
    md = AutonomousAgent.format_tool_result_as_markdown(
        "tool_query_database",
        tool_result,
        prompt="apa aja stok yang kurang?"
    )
    assert "### Laporan Status Persediaan Material Menara" in md
    assert "CRITICAL" in md
    assert "LOW STOCK" in md
    assert "| No |" in md
    assert "```json" not in md
    assert "Tindakan berhasil dijalankan" not in md


def test_format_tool_result_as_markdown_po_view():
    """Verify tool_view_po result is formatted as clean Markdown card without raw JSON."""
    tool_result = {
        "po_id": "PO-2026-001",
        "po_number": "PO/BLT/2026/01/012",
        "supplier_name": "PT Fiber Optik Nusantara",
        "item_name": "Kabel Fiber Optic ADSS 48 Core Single Mode",
        "order_quantity": 5000,
        "unit": "meter",
        "total_amount": 140000000.0,
        "status": "ORDERED",
        "pdf_download_url": "/api/download/po/PO-2026-001.pdf"
    }
    md = AutonomousAgent.format_tool_result_as_markdown(
        "tool_view_po",
        tool_result,
        prompt="Tampilkan dokumen PDF untuk PO-2026-001"
    )
    assert "### Dokumen Purchase Order: PO/BLT/2026/01/012" in md
    assert "PT Fiber Optik Nusantara" in md
    assert "Rp 140.000.000" in md
    assert "```json" not in md
    assert "Tindakan berhasil dijalankan" not in md


def test_format_tool_result_as_markdown_procurement_cycle():
    """Verify tool_procurement_cycle result is formatted as clean Markdown card."""
    tool_result = {
        "status": "SUCCESS",
        "pr_number": "PR-20260922-001",
        "supplier_name": "PT Solusi Menara Unggul",
        "total_budget": 85000000.0,
        "items": [{"item_code": "GEN-01", "quantity": 2}]
    }
    md = AutonomousAgent.format_tool_result_as_markdown(
        "tool_procurement_cycle",
        tool_result,
        prompt="Jalankan restock pengadaan"
    )
    assert "### Siklus Pengadaan Material (Purchase Requisition) Berhasil Dijalankan" in md
    assert "PR-20260922-001" in md
    assert "Rp 85.000.000" in md
    assert "```json" not in md


def test_format_tool_result_empty_data():
    """Verify empty database result produces polite explanation."""
    tool_result = {"columns": ["item_code"], "rows_count": 0, "data": []}
    md = AutonomousAgent.format_tool_result_as_markdown(
        "tool_query_database",
        tool_result,
        prompt="Cari material XYZ yang langka"
    )
    assert "Tidak ditemukan catatan data yang sesuai" in md
    assert "```json" not in md


if __name__ == "__main__":
    test_format_table_markdown()
    print("✓ test_format_table_markdown passed")
    test_format_tool_result_as_markdown_db_query()
    print("✓ test_format_tool_result_as_markdown_db_query passed")
    test_format_tool_result_as_markdown_po_view()
    print("✓ test_format_tool_result_as_markdown_po_view passed")
    test_format_tool_result_as_markdown_procurement_cycle()
    print("✓ test_format_tool_result_as_markdown_procurement_cycle passed")
    test_format_tool_result_empty_data()
    print("✓ test_format_tool_result_empty_data passed")
    print("\nALL UNIT TESTS PASSED!")
