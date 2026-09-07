from typing import Any
from database.db import get_db_connection


class TenantSchemaAdapter:
    """
    Adapter Layer that dynamically abstracts and translates 3 heterogeneous database schemas
    (Manufacturing Electronics, Pharma WMS, Fleet Parts) into a Canonical Procurement Entity.
    """

    @classmethod
    def get_low_stock_items(cls, tenant_id: str = "ALL") -> list[dict[str, Any]]:
        """Retrieve items whose physical stock has fallen below threshold for a given tenant."""
        conn = get_db_connection(read_only=True)
        try:
            results = []

            # -------------------------------------------------------------
            # TENANT A: Electronics Manufacturing (mfg_electronics_inventory)
            # -------------------------------------------------------------
            if tenant_id in ["TENANT_A", "ALL"]:
                query_a = """
                    SELECT 
                        Part_Number,
                        Component_Name,
                        Manufacturer,
                        Package_Footprint,
                        Stock_Quantity,
                        Min_Safety_Stock,
                        Lead_Time_Days,
                        Unit_Price_USD
                    FROM mfg_electronics_inventory
                    WHERE Stock_Quantity <= Min_Safety_Stock
                    ORDER BY (Min_Safety_Stock - Stock_Quantity) DESC;
                """
                for row in conn.execute(query_a).fetchall():
                    part_num, comp_name, mfg, pkg, stock, min_sec, lead_days, price_usd = row
                    stock_val = int(stock)
                    min_val = int(min_sec)
                    price_idr = float(price_usd) * 16000.0
                    reorder_qty = max(min_val * 2 - stock_val, 1)

                    results.append({
                        "item_id": part_num,
                        "name": f"{comp_name} ({part_num})",
                        "category": "Electronics Manufacturing",
                        "current_stock": stock_val,
                        "min_threshold": min_val,
                        "max_threshold": min_val * 3,
                        "avg_daily_usage": 15.0,
                        "lead_time_days": int(lead_days),
                        "unit": pkg or "pcs",
                        "unit_price": price_idr,
                        "safety_stock": min_val,
                        "reorder_qty": reorder_qty,
                        "tenant_id": "TENANT_A",
                        "raw_source_table": "mfg_electronics_inventory"
                    })

            # -------------------------------------------------------------
            # TENANT B: Pharmaceutical & FMCG WMS (pharma_fmcg_inventory)
            # -------------------------------------------------------------
            if tenant_id in ["TENANT_B", "ALL"]:
                query_b = """
                    SELECT 
                        Drug_Name,
                        Brand_Name,
                        Strength,
                        Closing_Stock,
                        Shortage_Flag,
                        Issued_Qty,
                        Lead_Time_Days,
                        Unit_Price_USD
                    FROM pharma_fmcg_inventory
                    WHERE Shortage_Flag = 1 OR Closing_Stock <= 150
                    ORDER BY Closing_Stock ASC;
                """
                for row in conn.execute(query_b).fetchall():
                    drug, brand, strength, stock, shortage, issued, lead_days, price_usd = row
                    stock_val = int(stock)
                    min_val = 150
                    price_idr = float(price_usd) * 16000.0
                    avg_burn = round(float(issued) / 30.0, 1) if issued else 10.0
                    reorder_qty = max(400 - stock_val, 20)

                    results.append({
                        "item_id": drug.replace(" ", "_").upper()[:12],
                        "name": f"{brand} - {drug} ({strength})",
                        "category": "Pharmaceuticals & Healthcare",
                        "current_stock": stock_val,
                        "min_threshold": min_val,
                        "max_threshold": 500,
                        "avg_daily_usage": avg_burn,
                        "lead_time_days": int(lead_days),
                        "unit": strength or "pack",
                        "unit_price": price_idr,
                        "safety_stock": min_val,
                        "reorder_qty": reorder_qty,
                        "tenant_id": "TENANT_B",
                        "raw_source_table": "pharma_fmcg_inventory"
                    })

            # -------------------------------------------------------------
            # TENANT C: Fleet & Workshop Spare Parts (fleet_maintenance_parts)
            # -------------------------------------------------------------
            if tenant_id in ["TENANT_C", "ALL"]:
                query_c = """
                    SELECT 
                        Vehicle_Model,
                        Invoice_Line_Text,
                        Category,
                        Stock_On_Shelf,
                        Critical_Threshold,
                        Lead_Time_Days,
                        Unit_Cost_IDR
                    FROM fleet_maintenance_parts
                    WHERE Stock_On_Shelf <= Critical_Threshold
                    ORDER BY (Critical_Threshold - Stock_On_Shelf) DESC;
                """
                for row in conn.execute(query_c).fetchall():
                    v_model, line_text, category, stock, crit_thresh, lead_days, cost_idr = row
                    stock_val = int(stock)
                    crit_val = int(crit_thresh)
                    reorder_qty = max(crit_val * 2 - stock_val, 1)

                    results.append({
                        "item_id": f"FLT-{line_text.replace(' ', '_').upper()[:10]}",
                        "name": f"{line_text} [{v_model}]",
                        "category": category or "Fleet Maintenance",
                        "current_stock": stock_val,
                        "min_threshold": crit_val,
                        "max_threshold": crit_val * 3,
                        "avg_daily_usage": 1.5,
                        "lead_time_days": int(lead_days),
                        "unit": "set",
                        "unit_price": float(cost_idr),
                        "safety_stock": crit_val,
                        "reorder_qty": reorder_qty,
                        "tenant_id": "TENANT_C",
                        "raw_source_table": "fleet_maintenance_parts"
                    })

            return results
        finally:
            conn.close()

    @classmethod
    def get_all_inventory_items(cls, tenant_id: str = "ALL") -> list[dict[str, Any]]:
        """Retrieve all items across the active tenant's real table."""
        conn = get_db_connection(read_only=True)
        try:
            items = []

            # TENANT A
            if tenant_id in ["TENANT_A", "ALL"]:
                rows = conn.execute("""
                    SELECT Part_Number, Component_Name, Package_Footprint, Stock_Quantity, Min_Safety_Stock, Lead_Time_Days, Unit_Price_USD
                    FROM mfg_electronics_inventory
                    ORDER BY Part_Number ASC;
                """).fetchall()
                for r in rows:
                    items.append({
                        "item_id": r[0],
                        "name": f"{r[1]} ({r[0]})",
                        "category": "Electronics Manufacturing",
                        "current_stock": int(r[3]),
                        "min_threshold": int(r[4]),
                        "max_threshold": int(r[4]) * 3,
                        "avg_daily_usage": 15.0,
                        "lead_time_days": int(r[5]),
                        "unit": r[2] or "pcs",
                        "unit_price": float(r[6]) * 16000.0,
                        "tenant_id": "TENANT_A"
                    })

            # TENANT B
            if tenant_id in ["TENANT_B", "ALL"]:
                rows = conn.execute("""
                    SELECT Drug_Name, Brand_Name, Strength, Closing_Stock, Issued_Qty, Lead_Time_Days, Unit_Price_USD
                    FROM pharma_fmcg_inventory
                    ORDER BY Drug_Name ASC;
                """).fetchall()
                for r in rows:
                    items.append({
                        "item_id": r[0].replace(" ", "_").upper()[:12],
                        "name": f"{r[1]} - {r[0]} ({r[2]})",
                        "category": "Pharmaceuticals & Healthcare",
                        "current_stock": int(r[3]),
                        "min_threshold": 150,
                        "max_threshold": 500,
                        "avg_daily_usage": round(float(r[4]) / 30.0, 1) if r[4] else 10.0,
                        "lead_time_days": int(r[5]),
                        "unit": r[2] or "pack",
                        "unit_price": float(r[6]) * 16000.0,
                        "tenant_id": "TENANT_B"
                    })

            # TENANT C
            if tenant_id in ["TENANT_C", "ALL"]:
                rows = conn.execute("""
                    SELECT Vehicle_Model, Invoice_Line_Text, Category, Stock_On_Shelf, Critical_Threshold, Lead_Time_Days, Unit_Cost_IDR
                    FROM fleet_maintenance_parts
                    ORDER BY Invoice_Line_Text ASC;
                """).fetchall()
                for r in rows:
                    items.append({
                        "item_id": f"FLT-{r[1].replace(' ', '_').upper()[:10]}",
                        "name": f"{r[1]} [{r[0]}]",
                        "category": r[2] or "Fleet Maintenance",
                        "current_stock": int(r[3]),
                        "min_threshold": int(r[4]),
                        "max_threshold": int(r[4]) * 3,
                        "avg_daily_usage": 1.5,
                        "lead_time_days": int(r[5]),
                        "unit": "set",
                        "unit_price": float(r[6]),
                        "tenant_id": "TENANT_C"
                    })

            return items
        finally:
            conn.close()

    @classmethod
    def get_specific_item_stock(cls, item_name: str, tenant_id: str = "ALL") -> list[dict[str, Any]]:
        """Search and retrieve items matching item_name in the tenant's real table."""
        all_items = cls.get_all_inventory_items(tenant_id)
        query_lower = item_name.strip().lower()
        return [it for it in all_items if query_lower in it["name"].lower() or query_lower in it["item_id"].lower()]

    @classmethod
    def update_item_stock(cls, item_id: str, qty_to_add: int, item_name: str | None = None, tenant_id: str = "ALL") -> bool:
        """
        Increments physical inventory stock in the tenant's real heterogeneous table,
        with fallback to legacy items table.
        """
        conn = get_db_connection()
        updated = False
        try:
            name_param = (item_name or item_id).strip().lower()
            id_param = item_id.strip()

            # TENANT A: Electronics Manufacturing
            if tenant_id in ["TENANT_A", "ALL"]:
                res = conn.execute("""
                    UPDATE mfg_electronics_inventory
                    SET Stock_Quantity = GREATEST(Stock_Quantity + ?, Min_Safety_Stock + 5)
                    WHERE Part_Number = ? OR lower(Component_Name) LIKE ?;
                """, [qty_to_add, id_param, f"%{name_param}%"])
                if res.rowcount > 0:
                    updated = True

            # TENANT B: Pharma & FMCG
            if tenant_id in ["TENANT_B", "ALL"]:
                res = conn.execute("""
                    UPDATE pharma_fmcg_inventory
                    SET Closing_Stock = Closing_Stock + ?, Shortage_Flag = 0
                    WHERE upper(replace(Drug_Name, ' ', '_')) LIKE ? OR lower(Drug_Name) LIKE ? OR lower(Brand_Name) LIKE ?;
                """, [qty_to_add, f"%{id_param.upper()}%", f"%{name_param}%", f"%{name_param}%"])
                if res.rowcount > 0:
                    updated = True

            # TENANT C: Fleet Parts
            if tenant_id in ["TENANT_C", "ALL"]:
                res = conn.execute("""
                    UPDATE fleet_maintenance_parts
                    SET Stock_On_Shelf = GREATEST(Stock_On_Shelf + ?, Critical_Threshold + 2)
                    WHERE upper(replace(Invoice_Line_Text, ' ', '_')) LIKE ? OR lower(Invoice_Line_Text) LIKE ? OR lower(Vehicle_Model) LIKE ?;
                """, [qty_to_add, f"%{id_param.upper().replace('FLT-', '')}%", f"%{name_param}%", f"%{name_param}%"])
                if res.rowcount > 0:
                    updated = True

            # Also update legacy/shared items table if matching item exists
            conn.execute("""
                UPDATE items
                SET current_stock = GREATEST(current_stock + ?, min_threshold + 5)
                WHERE item_id = ? OR lower(name) LIKE ?;
            """, [qty_to_add, id_param, f"%{name_param}%"])

            conn.commit()
            return updated
        finally:
            conn.close()

    @classmethod
    def update_item_threshold(cls, item_id_or_name: str, new_threshold: int, tenant_id: str = "ALL") -> bool:
        """
        Updates safety stock threshold in the tenant's real heterogeneous table and legacy items table.
        """
        conn = get_db_connection()
        updated = False
        try:
            target = item_id_or_name.strip()
            target_lower = target.lower()

            # TENANT A: Min_Safety_Stock
            if tenant_id in ["TENANT_A", "ALL"]:
                res = conn.execute("""
                    UPDATE mfg_electronics_inventory
                    SET Min_Safety_Stock = ?
                    WHERE Part_Number = ? OR lower(Component_Name) LIKE ?;
                """, [new_threshold, target, f"%{target_lower}%"])
                if res.rowcount > 0:
                    updated = True

            # TENANT C: Critical_Threshold
            if tenant_id in ["TENANT_C", "ALL"]:
                res = conn.execute("""
                    UPDATE fleet_maintenance_parts
                    SET Critical_Threshold = ?
                    WHERE upper(replace(Invoice_Line_Text, ' ', '_')) LIKE ? OR lower(Invoice_Line_Text) LIKE ?;
                """, [new_threshold, f"%{target.upper().replace('FLT-', '')}%", f"%{target_lower}%"])
                if res.rowcount > 0:
                    updated = True

            # Fallback items table
            conn.execute("""
                UPDATE items
                SET min_threshold = ?
                WHERE item_id = ? OR lower(name) LIKE ?;
            """, [new_threshold, target, f"%{target_lower}%"])

            conn.commit()
            return updated
        finally:
            conn.close()

    @classmethod
    def register_new_product(cls, item_data: dict, tenant_id: str = "TENANT_A") -> dict:
        """
        Registers a new inventory item directly into the active tenant's real table and shared registry.
        """
        import uuid
        conn = get_db_connection()
        effective_tenant = tenant_id if tenant_id and tenant_id != "ALL" else "TENANT_A"
        name = item_data.get("name", "New Item")
        category = item_data.get("category", "General")
        stock = int(item_data.get("current_stock", 0))
        min_thresh = int(item_data.get("min_threshold", 10))
        lead_time = int(item_data.get("lead_time_days", 3))
        unit = item_data.get("unit", "pcs")
        unit_price = float(item_data.get("unit_price", 50000.0))
        unit_price_usd = round(unit_price / 16000.0, 2)

        try:
            if effective_tenant == "TENANT_A":
                part_no = item_data.get("part_number") or f"PART-{uuid.uuid4().hex[:6].upper()}"
                conn.execute("""
                    INSERT INTO mfg_electronics_inventory (Part_Number, Component_Name, Manufacturer, Package_Footprint, Stock_Quantity, Min_Safety_Stock, Lead_Time_Days, Unit_Price_USD)
                    VALUES (?, ?, 'Local Manufacturer', ?, ?, ?, ?, ?);
                """, [part_no, name, unit, stock, min_thresh, lead_time, unit_price_usd])
                registered_id = part_no

            elif effective_tenant == "TENANT_B":
                drug_name = name
                brand_name = item_data.get("brand_name") or "PharmaGeneric"
                conn.execute("""
                    INSERT INTO pharma_fmcg_inventory (Drug_Name, Brand_Name, Strength, Opening_Stock, Issued_Qty, Closing_Stock, Shortage_Flag, Lead_Time_Days, Unit_Price_USD)
                    VALUES (?, ?, ?, ?, 0, ?, 0, ?, ?);
                """, [drug_name, brand_name, unit, stock, stock, lead_time, unit_price_usd])
                registered_id = drug_name.replace(" ", "_").upper()[:12]

            else: # TENANT_C
                line_text = name
                model = item_data.get("vehicle_model") or "Fleet General"
                conn.execute("""
                    INSERT INTO fleet_maintenance_parts (Vehicle_Model, Invoice_Line_Text, Category, Stock_On_Shelf, Critical_Threshold, Lead_Time_Days, Unit_Cost_IDR)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                """, [model, line_text, category, stock, min_thresh, lead_time, int(unit_price)])
                registered_id = f"FLT-{line_text.replace(' ', '_').upper()[:10]}"

            # Also register to legacy items & vendors for backward compatibility
            conn.execute("""
                INSERT INTO items (item_id, name, category, current_stock, min_threshold, max_threshold, avg_daily_usage, lead_time_days, unit, tenant_id)
                VALUES (?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?);
            """, [registered_id, name, category, stock, min_thresh, min_thresh * 3, lead_time, unit, effective_tenant])

            conn.execute("""
                INSERT INTO vendors (vendor_id, name, item_id, unit_price, lead_time_days, rating, tenant_id)
                VALUES (?, 'Standard Verified Supplier', ?, ?, ?, 4.8, ?);
            """, [f"VND-{registered_id[-4:]}", registered_id, unit_price, lead_time, effective_tenant])

            conn.commit()
            return {
                "item_id": registered_id,
                "name": name,
                "tenant_id": effective_tenant
            }
        finally:
            conn.close()

