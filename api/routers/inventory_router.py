"""
Inventory API Router
Endpoints for inventory items, stock levels, suppliers, and analytics.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional
from core.schemas import InventoryItem, Supplier, DashboardStats, InventoryUpdate
from database.db import db

router = APIRouter(prefix="/api/inventory", tags=["Inventory"])


@router.get("/items", response_model=List[InventoryItem])
async def get_items(
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    return db.get_items(category=category, status=status, search=search)


@router.get("/items/{sku}", response_model=InventoryItem)
async def get_item_by_sku(sku: str):
    item = db.get_item_by_sku(sku)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.post("/stock-adjust")
async def adjust_stock(update: InventoryUpdate):
    updated = db.update_stock(
        sku=update.sku,
        change=update.quantity_change,
        transaction_type=update.transaction_type,
        ref_doc=update.reference_doc,
        notes=update.notes
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"status": "success", "item": updated}


@router.get("/suppliers", response_model=List[Supplier])
async def get_suppliers():
    return db.get_suppliers()


@router.get("/stats", response_model=DashboardStats)
async def get_stats():
    return db.get_dashboard_stats()


@router.get("/categories", response_model=List[str])
async def get_categories():
    """Returns all distinct inventory categories."""
    return db.get_categories()


@router.post("/categories")
async def create_category(payload: dict):
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name cannot be empty")
    db.add_category(name)
    return {"status": "success", "category": name, "categories": db.get_categories()}


@router.get("/export/csv")
async def export_catalog_csv():
    """Exports entire inventory catalog to standard CSV."""
    import io
    import csv
    from fastapi.responses import Response

    items = db.get_items()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["SKU", "Nama Produk", "Kategori", "Stok Terkini", "Satuan", "Min Stock", "Max Stock", "Harga Satuan (IDR)", "Supplier", "Status"])

    for it in items:
        writer.writerow([
            it.sku,
            it.name,
            it.category,
            it.current_stock,
            it.unit,
            it.min_stock,
            it.max_stock,
            it.unit_price,
            it.supplier_name or it.supplier_id,
            it.status
        ])

    csv_data = output.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=katalog_inventaris.csv"}
    )
