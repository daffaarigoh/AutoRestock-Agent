"""
Database Layer for AutoRestock-V2
SQLite storage backend with full transaction support, schema migrations, and enterprise queries.
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from core.config import settings
from core.schemas import (
    InventoryItem,
    Supplier,
    PurchaseRequisition,
    PurchaseRequisitionItem,
    PRStatus,
    DashboardStats,
    DiscrepancyItem
)

CANONICAL_CATEGORIES = {
    "fmcg": "FMCG",
    "it & electronics": "IT & Electronics",
    "it": "IT & Electronics",
    "food & beverage": "Food & Beverage",
    "office supplies": "Office Supplies",
    "industrial spare parts": "Industrial Spare Parts",
    "kosmetik": "Kosmetik",
    "general": "General",
    "uncategorized": "Uncategorized"
}

def normalize_category_name(name: str) -> str:
    if not name:
        return "General"
    clean = name.strip()
    return CANONICAL_CATEGORIES.get(clean.lower(), clean.title())


class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or settings.DB_PATH)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Initialize database tables."""
        conn = self.get_connection()
        cursor = conn.cursor()

        # 1. Suppliers Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS suppliers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                contact_person TEXT,
                email TEXT,
                phone TEXT,
                address TEXT,
                lead_time_days INTEGER DEFAULT 3,
                rating REAL DEFAULT 4.8
            )
        """)

        # 2. Inventory Items Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                sku TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                current_stock INTEGER NOT NULL,
                min_stock INTEGER NOT NULL,
                max_stock INTEGER NOT NULL,
                safety_stock INTEGER DEFAULT 5,
                unit TEXT DEFAULT 'pcs',
                unit_price REAL DEFAULT 0.0,
                supplier_id TEXT NOT NULL,
                supplier_name TEXT,
                lead_time_days INTEGER DEFAULT 3,
                location_bin TEXT DEFAULT 'A-01-01',
                last_restocked_at TEXT,
                status TEXT DEFAULT 'normal',
                FOREIGN KEY (supplier_id) REFERENCES suppliers (id)
            )
        """)

        # 3. Inventory Logs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity_change INTEGER NOT NULL,
                transaction_type TEXT NOT NULL,
                reference_doc TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku) REFERENCES items (sku)
            )
        """)

        # 4. Purchase Requisitions Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchase_requisitions (
                pr_number TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                supplier_id TEXT NOT NULL,
                supplier_name TEXT NOT NULL,
                subtotal REAL DEFAULT 0.0,
                tax_rate REAL DEFAULT 0.11,
                tax_amount REAL DEFAULT 0.0,
                grand_total REAL DEFAULT 0.0,
                status TEXT DEFAULT 'pending_approval',
                urgency TEXT DEFAULT 'NORMAL',
                notes TEXT,
                pdf_path TEXT,
                approver_name TEXT,
                approved_at TEXT,
                rejection_reason TEXT,
                auto_approved INTEGER DEFAULT 0
            )
        """)

        # 5. Purchase Requisition Items Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pr_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pr_number TEXT NOT NULL,
                sku TEXT NOT NULL,
                item_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit TEXT DEFAULT 'pcs',
                unit_price REAL DEFAULT 0.0,
                total_price REAL DEFAULT 0.0,
                current_stock INTEGER DEFAULT 0,
                min_stock INTEGER DEFAULT 0,
                reason TEXT,
                FOREIGN KEY (pr_number) REFERENCES purchase_requisitions (pr_number) ON DELETE CASCADE
            )
        """)

        # 6. Discrepancy & Audit Records Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS discrepancies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_number TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                sku TEXT NOT NULL,
                item_name TEXT NOT NULL,
                doc_quantity INTEGER NOT NULL,
                recorded_stock INTEGER NOT NULL,
                physical_count INTEGER,
                diff_quantity INTEGER NOT NULL,
                severity TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'open',
                notes TEXT,
                created_at TEXT NOT NULL,
                resolved_at TEXT
            )
        """)

        # 7. Dynamic Categories Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        conn.commit()
        conn.close()

    # --- Supplier Operations ---
    def upsert_supplier(self, supplier: Supplier):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO suppliers (id, name, contact_person, email, phone, address, lead_time_days, rating)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    contact_person=excluded.contact_person,
                    email=excluded.email,
                    phone=excluded.phone,
                    address=excluded.address,
                    lead_time_days=excluded.lead_time_days,
                    rating=excluded.rating
            """, (
                supplier.id, supplier.name, supplier.contact_person,
                supplier.email, supplier.phone, supplier.address,
                supplier.lead_time_days, supplier.rating
            ))
            conn.commit()

    def get_suppliers(self) -> List[Supplier]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM suppliers ORDER BY name ASC")
            rows = cursor.fetchall()
            return [Supplier(**dict(r)) for r in rows]

    def get_supplier_by_id(self, supplier_id: str) -> Optional[Supplier]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
            row = cursor.fetchone()
            return Supplier(**dict(row)) if row else None

    # --- Inventory Item Operations ---
    def upsert_item(self, item: InventoryItem):
        status = "normal"
        if item.current_stock <= 0:
            status = "out_of_stock"
        elif item.current_stock <= item.min_stock:
            status = "low_stock"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO items (
                    sku, name, category, current_stock, min_stock, max_stock,
                    safety_stock, unit, unit_price, supplier_id, supplier_name,
                    lead_time_days, location_bin, last_restocked_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sku) DO UPDATE SET
                    name=excluded.name,
                    category=excluded.category,
                    current_stock=excluded.current_stock,
                    min_stock=excluded.min_stock,
                    max_stock=excluded.max_stock,
                    safety_stock=excluded.safety_stock,
                    unit=excluded.unit,
                    unit_price=excluded.unit_price,
                    supplier_id=excluded.supplier_id,
                    supplier_name=excluded.supplier_name,
                    lead_time_days=excluded.lead_time_days,
                    location_bin=excluded.location_bin,
                    last_restocked_at=excluded.last_restocked_at,
                    status=excluded.status
            """, (
                item.sku, item.name, item.category, item.current_stock,
                item.min_stock, item.max_stock, item.safety_stock,
                item.unit, item.unit_price, item.supplier_id, item.supplier_name,
                item.lead_time_days, item.location_bin, item.last_restocked_at, status
            ))
            conn.commit()

    def get_items(self, category: Optional[str] = None, status: Optional[str] = None, search: Optional[str] = None) -> List[InventoryItem]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM items WHERE 1=1"
            params = []

            if category and category.lower() != "all":
                query += " AND category = ?"
                params.append(category)

            if status and status.lower() != "all":
                query += " AND status = ?"
                params.append(status)

            if search:
                query += " AND (sku LIKE ? OR name LIKE ? OR location_bin LIKE ?)"
                like_str = f"%{search}%"
                params.extend([like_str, like_str, like_str])

            query += " ORDER BY category ASC, name ASC"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [InventoryItem(**dict(r)) for r in rows]

    def get_item_by_sku(self, sku: str) -> Optional[InventoryItem]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM items WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return InventoryItem(**dict(row)) if row else None

    def update_stock(self, sku: str, change: int, transaction_type: str, ref_doc: Optional[str] = None, notes: Optional[str] = None) -> Optional[InventoryItem]:
        item = self.get_item_by_sku(sku)
        if not item:
            return None

        new_stock = max(0, item.current_stock + change)
        item.current_stock = new_stock
        item.last_restocked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if change > 0 else item.last_restocked_at
        self.upsert_item(item)

        # Log transaction
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO inventory_logs (sku, quantity_change, transaction_type, reference_doc, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (sku, change, transaction_type, ref_doc, notes, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()

        return self.get_item_by_sku(sku)

    def update_item_thresholds(self, sku: str, min_stock: Optional[int] = None, max_stock: Optional[int] = None, safety_stock: Optional[int] = None) -> Optional[InventoryItem]:
        item = self.get_item_by_sku(sku)
        if not item:
            return None
        if min_stock is not None:
            item.min_stock = min_stock
        if max_stock is not None:
            item.max_stock = max_stock
        if safety_stock is not None:
            item.safety_stock = safety_stock
        self.upsert_item(item)
        return self.get_item_by_sku(sku)

    def update_item_fields(self, sku: str, **kwargs) -> Optional[InventoryItem]:
        item = self.get_item_by_sku(sku)
        if not item:
            return None
        for field, value in kwargs.items():
            if hasattr(item, field) and value is not None:
                setattr(item, field, value)
        self.upsert_item(item)
        return self.get_item_by_sku(sku)

    def delete_item(self, sku: str) -> bool:
        item = self.get_item_by_sku(sku)
        if not item:
            return False
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM items WHERE sku = ?", (sku,))
            cursor.execute("DELETE FROM inventory_logs WHERE sku = ?", (sku,))
            conn.commit()
        return True

    # --- Purchase Requisition Operations ---
    def save_purchase_requisition(self, pr: PurchaseRequisition):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO purchase_requisitions (
                    pr_number, created_at, supplier_id, supplier_name,
                    subtotal, tax_rate, tax_amount, grand_total, status,
                    urgency, notes, pdf_path, approver_name, approved_at,
                    rejection_reason, auto_approved
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pr_number) DO UPDATE SET
                    supplier_id=excluded.supplier_id,
                    supplier_name=excluded.supplier_name,
                    subtotal=excluded.subtotal,
                    tax_amount=excluded.tax_amount,
                    grand_total=excluded.grand_total,
                    status=excluded.status,
                    urgency=excluded.urgency,
                    notes=excluded.notes,
                    pdf_path=excluded.pdf_path,
                    approver_name=excluded.approver_name,
                    approved_at=excluded.approved_at,
                    rejection_reason=excluded.rejection_reason,
                    auto_approved=excluded.auto_approved
            """, (
                pr.pr_number, pr.created_at, pr.supplier_id, pr.supplier_name,
                pr.subtotal, pr.tax_rate, pr.tax_amount, pr.grand_total,
                pr.status.value if isinstance(pr.status, PRStatus) else pr.status,
                pr.urgency, pr.notes, pr.pdf_path, pr.approver_name,
                pr.approved_at, pr.rejection_reason, 1 if pr.auto_approved else 0
            ))

            # Remove old items and re-insert
            cursor.execute("DELETE FROM pr_items WHERE pr_number = ?", (pr.pr_number,))
            for it in pr.items:
                cursor.execute("""
                    INSERT INTO pr_items (
                        pr_number, sku, item_name, quantity, unit,
                        unit_price, total_price, current_stock, min_stock, reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pr.pr_number, it.sku, it.item_name, it.quantity, it.unit,
                    it.unit_price, it.total_price, it.current_stock, it.min_stock, it.reason
                ))
            conn.commit()

    def get_purchase_requisitions(self, status: Optional[str] = None) -> List[PurchaseRequisition]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM purchase_requisitions"
            params = []
            if status and status.lower() != "all":
                query += " WHERE status = ?"
                params.append(status)
            query += " ORDER BY created_at DESC"
            cursor.execute(query, params)
            rows = cursor.fetchall()

            result = []
            for row in rows:
                pr_dict = dict(row)
                cursor.execute("SELECT * FROM pr_items WHERE pr_number = ?", (pr_dict["pr_number"],))
                item_rows = cursor.fetchall()
                pr_dict["items"] = [PurchaseRequisitionItem(**dict(ir)) for ir in item_rows]
                result.append(PurchaseRequisition(**pr_dict))
            return result

    def get_pr_by_number(self, pr_number: str) -> Optional[PurchaseRequisition]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM purchase_requisitions WHERE pr_number = ?", (pr_number,))
            row = cursor.fetchone()
            if not row:
                return None
            pr_dict = dict(row)
            cursor.execute("SELECT * FROM pr_items WHERE pr_number = ?", (pr_number,))
            item_rows = cursor.fetchall()
            pr_dict["items"] = [PurchaseRequisitionItem(**dict(ir)) for ir in item_rows]
            return PurchaseRequisition(**pr_dict)

    def update_pr_status(self, pr_number: str, status: PRStatus, approver_name: str, notes: Optional[str] = None, rejection_reason: Optional[str] = None) -> Optional[PurchaseRequisition]:
        pr = self.get_pr_by_number(pr_number)
        if not pr:
            return None

        pr.status = status
        pr.approver_name = approver_name
        pr.approved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if notes:
            pr.notes = (pr.notes or "") + f" [Approval Note: {notes}]"
        if rejection_reason:
            pr.rejection_reason = rejection_reason

        self.save_purchase_requisition(pr)
        return pr

    # --- Discrepancies Operations ---
    def record_discrepancy(self, doc_number: str, doc_type: str, item: DiscrepancyItem):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO discrepancies (
                    doc_number, doc_type, sku, item_name, doc_quantity,
                    recorded_stock, physical_count, diff_quantity, severity,
                    reason, suggested_action, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
            """, (
                doc_number, doc_type, item.sku, item.item_name,
                item.doc_quantity, item.recorded_stock, item.physical_count,
                item.diff_quantity, item.severity.value, item.reason,
                item.suggested_action, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()

    def get_discrepancies(self, status: str = "open") -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM discrepancies WHERE status = ? ORDER BY created_at DESC", (status,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    # --- Dashboard Metrics ---
    def get_dashboard_stats(self) -> DashboardStats:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Items metrics
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_items,
                    SUM(CASE WHEN current_stock <= min_stock AND current_stock > 0 THEN 1 ELSE 0 END) as low_stock_items,
                    SUM(CASE WHEN current_stock = 0 THEN 1 ELSE 0 END) as out_of_stock_items,
                    SUM(current_stock * unit_price) as total_inventory_value
                FROM items
            """)
            item_stats = cursor.fetchone()

            # Suppliers count
            cursor.execute("SELECT COUNT(*) FROM suppliers")
            total_suppliers = cursor.fetchone()[0]

            # PR metrics
            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN status = 'pending_approval' THEN 1 ELSE 0 END) as pending_prs,
                    SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved_prs,
                    SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected_prs,
                    SUM(CASE WHEN status = 'pending_approval' THEN grand_total ELSE 0 END) as total_pending_pr_value
                FROM purchase_requisitions
            """)
            pr_stats = cursor.fetchone()

            # Discrepancies
            cursor.execute("SELECT COUNT(*) FROM discrepancies WHERE status = 'open'")
            active_disc = cursor.fetchone()[0]

            return DashboardStats(
                total_items=item_stats["total_items"] or 0,
                low_stock_items=item_stats["low_stock_items"] or 0,
                out_of_stock_items=item_stats["out_of_stock_items"] or 0,
                total_suppliers=total_suppliers or 0,
                pending_prs=pr_stats["pending_prs"] or 0,
                approved_prs=pr_stats["approved_prs"] or 0,
                rejected_prs=pr_stats["rejected_prs"] or 0,
                total_inventory_value_idr=float(item_stats["total_inventory_value"] or 0.0),
                total_pending_pr_value_idr=float(pr_stats["total_pending_pr_value"] or 0.0),
                active_discrepancies=active_disc or 0
            )

    # --- Dynamic Category Management ---
    def get_categories(self) -> List[str]:
        """Returns distinct sorted list of category names, case-insensitively deduplicated and canonically formatted."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM categories
            UNION
            SELECT DISTINCT category as name FROM items WHERE category IS NOT NULL AND category != ''
        """)
        rows = cursor.fetchall()
        conn.close()

        seen = {}
        for r in rows:
            raw = (r["name"] or "").strip()
            if not raw:
                continue
            canonical = normalize_category_name(raw)
            seen[canonical.lower()] = canonical

        return sorted(list(seen.values()))

    def add_category(self, name: str) -> bool:
        """Inserts a new category normalized to canonical format."""
        clean = normalize_category_name(name)
        if not clean:
            return False
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        try:
            cursor.execute("DELETE FROM categories WHERE LOWER(name) = LOWER(?)", (clean,))
            cursor.execute(
                "INSERT INTO categories (name, created_at) VALUES (?, ?)",
                (clean, now)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def delete_category(self, name: str) -> bool:
        """Deletes a category and re-assigns items with that category so it is permanently removed."""
        clean = normalize_category_name(name)
        fallback_cat = "General" if clean.lower() != "general" else "Uncategorized"
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM categories WHERE LOWER(name) = LOWER(?)", (clean,))
            cursor.execute("UPDATE items SET category = ? WHERE LOWER(category) = LOWER(?)", (fallback_cat, clean))
            conn.commit()
            return True
        finally:
            conn.close()

    def standardize_all_categories(self):
        """One-time normalization of all database categories to remove duplicates."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT sku, category FROM items WHERE category IS NOT NULL")
            items = cursor.fetchall()
            for it in items:
                norm = normalize_category_name(it["category"])
                if norm != it["category"]:
                    cursor.execute("UPDATE items SET category = ? WHERE sku = ?", (norm, it["sku"]))

            cursor.execute("SELECT id, name FROM categories")
            cats = cursor.fetchall()
            for c in cats:
                norm = normalize_category_name(c["name"])
                cursor.execute("UPDATE categories SET name = ? WHERE id = ?", (norm, c["id"]))

            conn.commit()
        finally:
            conn.close()


db = Database()
