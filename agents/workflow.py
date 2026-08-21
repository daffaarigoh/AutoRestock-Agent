"""
Autonomous Multi-Agent Workflow Engine
Coordinates document ingestion, OCR parsing, inventory reconciliation, demand calculation, PR document generation, and human approval gates.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import math
import re
import json

from core.config import settings
from core.schemas import (
    InventoryItem,
    ExtractedDocument,
    DiscrepancyReport,
    PurchaseRequisition,
    PurchaseRequisitionItem,
    PRStatus,
    ParsedPromptIntent,
    DocumentType
)
from core.observability import log_agent_step
from core.llm_client import llm_client
from database.db import db
from multimodal.ocr_engine import ocr_engine
from multimodal.vision_auditor import vision_auditor
from multimodal.visualizer import visualizer
from docgen.pdf_generator import pdf_generator
from agents.state import RestockAgentState


class AutoRestockWorkflow:
    def __init__(self):
        pass

    async def execute_document_ingest(self, file_path: str) -> RestockAgentState:
        """
        Executes full pipeline for an incoming warehouse document (Surat Jalan / Kartu Stok).
        """
        state: RestockAgentState = {
            "file_path": file_path,
            "trigger_source": "document_upload",
            "logs": [],
            "generated_prs": [],
            "requires_approval": False,
            "status": "processing"
        }

        # Step 1: Multimodal OCR Extraction
        try:
            extracted_doc = await ocr_engine.process_document(file_path)
            state["extracted_doc"] = extracted_doc
        except Exception as e:
            state["status"] = "error"
            state["error"] = f"OCR failed: {str(e)}"
            return state

        # Step 2: Audit & Discrepancy Reconciliation
        disc_report = vision_auditor.audit_document(extracted_doc)
        state["discrepancy_report"] = disc_report

        # Step 3: Draw Annotations with Bounding Boxes
        annotated_path = visualizer.annotate_document(
            image_path=file_path,
            extracted_doc=extracted_doc,
            discrepancy_report=disc_report
        )
        state["annotated_image_path"] = annotated_path
        extracted_doc.annotated_file = annotated_path

        # Step 4: If Document is Surat Jalan (Inbound Delivery), update inventory stock!
        if extracted_doc.doc_type == DocumentType.SURAT_JALAN:
            log_agent_step(
                step_name="Inventory Inbound Update",
                agent_name="InventoryManagerAgent",
                status="running",
                message=f"Applying inbound delivery to stock inventory for {len(extracted_doc.line_items)} items..."
            )
            for it in extracted_doc.line_items:
                if it.sku_guess:
                    db.update_stock(
                        sku=it.sku_guess,
                        change=it.quantity,
                        transaction_type="inbound_delivery",
                        ref_doc=extracted_doc.doc_number,
                        notes=f"Processed from {extracted_doc.doc_number}"
                    )
            log_agent_step(
                step_name="Inventory Inbound Update",
                agent_name="InventoryManagerAgent",
                status="success",
                message="Stock records updated from delivery note."
            )

        # Step 5: Check if any catalog items now require restocking
        state = await self._evaluate_and_generate_prs(state)
        state["status"] = "completed"
        return state

    async def execute_prompt_restock(self, user_prompt: str, auto_execute: bool = True) -> RestockAgentState:
        """
        Executes intelligent restock pipeline triggered by user natural language instructions.
        """
        state: RestockAgentState = {
            "user_prompt": user_prompt,
            "auto_execute": auto_execute,
            "trigger_source": "prompt_command",
            "logs": [],
            "generated_prs": [],
            "requires_approval": False,
            "status": "processing"
        }

        all_items = [it.model_dump() for it in db.get_items()]

        # Step 1: Intelligent Prompt Parsing
        parsed_intent = await llm_client.parse_restock_prompt(user_prompt, all_items)
        state["parsed_intent"] = parsed_intent

        # Step 1.1: Dynamic Add Item Handler
        if parsed_intent.intent_type == "add_item" and parsed_intent.new_item_data:
            from core.schemas import InventoryItem
            item_dict = parsed_intent.new_item_data
            new_item = InventoryItem(
                sku=item_dict["sku"],
                name=item_dict["name"],
                category=item_dict["category"],
                current_stock=item_dict["current_stock"],
                min_stock=item_dict["min_stock"],
                max_stock=item_dict["max_stock"],
                safety_stock=item_dict.get("safety_stock", 5),
                unit=item_dict.get("unit", "pcs"),
                unit_price=item_dict.get("unit_price", 0.0),
                supplier_id=item_dict.get("supplier_id", "SUP-001"),
                supplier_name=item_dict.get("supplier_name", "Supplier Rekanan"),
                lead_time_days=item_dict.get("lead_time_days", 3),
                location_bin=item_dict.get("location_bin", "RAK-A-01")
            )
            db.upsert_item(new_item)
            log_agent_step(
                step_name="Catalog Creation",
                agent_name="InventoryManagerAgent",
                status="success",
                message=f"Registered new item: {new_item.name} ({new_item.sku})"
            )
            state["status"] = "completed"
            state["action_type"] = "add_item"
            state["message"] = f"Barang baru '{new_item.name}' ({new_item.sku}) berhasil ditambahkan ke database dengan harga Rp {new_item.unit_price:,.0f} dan stok awal {new_item.current_stock} {new_item.unit}."
            state["affected_items"] = [new_item.model_dump()]
            return state

        # Step 1.01: Dynamic Category Handler
        if parsed_intent.intent_type == "add_category" and parsed_intent.category_data:
            cat_names = parsed_intent.category_data.get("category_names") or [parsed_intent.category_data.get("category_name", "General")]
            added = []
            for cn in cat_names:
                db.add_category(cn)
                added.append(cn)
            all_cats = db.get_categories()
            label = ", ".join(f"'{c}'" for c in added)
            log_agent_step(
                step_name="Category Registration",
                agent_name="InventoryManagerAgent",
                status="success",
                message=f"Registered {len(added)} category(ies): {label}"
            )
            state["status"] = "completed"
            state["action_type"] = "add_category"
            state["message"] = f"Kategori {label} berhasil ditambahkan ke database dan filter katalog inventaris."
            state["affected_items"] = [{"categories": added, "all_categories": all_cats}]
            return state

        if parsed_intent.intent_type == "delete_category" and parsed_intent.category_data:
            cat_names = parsed_intent.category_data.get("category_names") or [parsed_intent.category_data.get("category_name", "")]
            deleted = []
            for cn in cat_names:
                if cn:
                    db.delete_category(cn)
                    deleted.append(cn)
            all_cats = db.get_categories()
            label = ", ".join(f"'{c}'" for c in deleted)
            state["status"] = "completed"
            state["action_type"] = "delete_category"
            state["message"] = f"Kategori {label} berhasil dihapus dari database."
            state["affected_items"] = [{"categories": deleted, "all_categories": all_cats}]
            return state

        if parsed_intent.intent_type == "export_data":
            state["status"] = "completed"
            state["action_type"] = "export_data"
            state["message"] = "Data katalog inventaris siap diunduh dalam format CSV."
            return state

        # Step 1.05: Dynamic UI Customization Handler
        if parsed_intent.intent_type == "ui_action" and parsed_intent.ui_action_data:
            u_data = parsed_intent.ui_action_data
            log_agent_step(
                step_name="UI Customization",
                agent_name="InventoryManagerAgent",
                status="success",
                message=f"Applied UI customization: {u_data.get('action')} on {u_data.get('target')}"
            )
            state["status"] = "completed"
            state["action_type"] = "ui_action"
            state["message"] = f"Tampilan berhasil diubah: Kolom tabel 'MIN/MAX' telah diubah menjadi 'THRESHOLD'."
            return state

        # Step 1.1: Dynamic Item Creation Handler
        if parsed_intent.intent_type == "delete_item" and parsed_intent.delete_item_data:
            d_data = parsed_intent.delete_item_data
            target_sku = d_data["sku"]
            existing = db.get_item_by_sku(target_sku)
            item_name = existing.name if existing else d_data.get("item_name", target_sku)
            
            success = db.delete_item(target_sku)
            if success:
                log_agent_step(
                    step_name="Product Catalog Deletion",
                    agent_name="InventoryManagerAgent",
                    status="success",
                    message=f"Deleted item from catalog: {item_name} ({target_sku})"
                )
                state["status"] = "completed"
                state["action_type"] = "delete_item"
                state["message"] = f"Produk '{item_name}' ({target_sku}) berhasil dihapus secara permanen dari katalog inventaris."
                state["affected_items"] = [{"sku": target_sku, "name": item_name, "deleted": True}]
                return state

        # Step 1.2: Dynamic Stock Update / Correction Handler
        if parsed_intent.intent_type == "update_stock" and parsed_intent.stock_adjustment_data:
            adj = parsed_intent.stock_adjustment_data
            target_sku = adj["sku"]
            target_stock = adj["target_stock"]
            existing = db.get_item_by_sku(target_sku)
            if existing:
                diff = target_stock - existing.current_stock
                updated = db.update_stock(
                    sku=target_sku,
                    change=diff,
                    transaction_type="prompt_adjustment",
                    notes="Direct prompt correction by user"
                )
                log_agent_step(
                    step_name="Stock Correction",
                    agent_name="InventoryManagerAgent",
                    status="success",
                    message=f"Adjusted stock for {existing.name} to {target_stock} {existing.unit}"
                )
                state["status"] = "completed"
                state["action_type"] = "update_stock"
                state["message"] = f"Saldo stok untuk '{existing.name}' ({target_sku}) berhasil diperbarui dari {existing.current_stock} menjadi {target_stock} {existing.unit}."
                state["affected_items"] = [updated.model_dump()] if updated else []
                return state

        # Step 1.25: Dynamic Product Metadata Editing Handler
        if parsed_intent.intent_type == "edit_item" and parsed_intent.edit_item_data:
            e_data = parsed_intent.edit_item_data
            target_skus = e_data.get("skus") or parsed_intent.target_skus or ([e_data["sku"]] if e_data.get("sku") else [])
            kwargs = {}
            changes = []

            if e_data.get("category"):
                kwargs["category"] = e_data["category"]
                db.add_category(e_data["category"])
                changes.append(f"Kategori = '{e_data['category']}'")
            if e_data.get("name"):
                kwargs["name"] = e_data["name"]
                changes.append(f"Nama = '{e_data['name']}'")
            if e_data.get("unit_price") is not None:
                kwargs["unit_price"] = e_data["unit_price"]
                changes.append(f"Harga = Rp {e_data['unit_price']:,.0f}")
            if e_data.get("current_stock") is not None:
                kwargs["current_stock"] = e_data["current_stock"]
                changes.append(f"Stok = {e_data['current_stock']}")
            if e_data.get("max_stock") is not None:
                kwargs["max_stock"] = e_data["max_stock"]
                changes.append(f"Max Stock = {e_data['max_stock']}")
            if e_data.get("min_stock") is not None:
                kwargs["min_stock"] = e_data["min_stock"]
                changes.append(f"Min Stock = {e_data['min_stock']}")

            updated_items = []
            for sku in target_skus:
                existing = db.get_item_by_sku(sku)
                if existing:
                    updated = db.update_item_fields(sku, **kwargs)
                    if updated:
                        updated_items.append(updated.model_dump())

            log_agent_step(
                step_name="Product Catalog Editing",
                agent_name="InventoryManagerAgent",
                status="success",
                message=f"Updated {len(updated_items)} item(s): {', '.join(changes)}"
            )
            state["status"] = "completed"
            state["action_type"] = "edit_item"
            state["message"] = f"Berhasil memperbarui data untuk {len(updated_items)} produk ({', '.join(changes)})."
            state["affected_items"] = updated_items
            return state

        # Step 1.3: Dynamic Threshold Configuration Handler
        if parsed_intent.intent_type == "update_threshold" and parsed_intent.threshold_data:
            t_data = parsed_intent.threshold_data
            sku = t_data.get("sku")
            min_s = t_data.get("min_stock")
            max_s = t_data.get("max_stock")
            safety_s = t_data.get("safety_stock")

            affected = []
            if sku and sku != "ALL":
                updated = db.update_item_thresholds(sku=sku, min_stock=min_s, max_stock=max_s, safety_stock=safety_s)
                if updated:
                    affected.append(updated.model_dump())
            else:
                all_catalog = db.get_items()
                for it in all_catalog:
                    up = db.update_item_thresholds(sku=it.sku, min_stock=min_s, max_stock=max_s, safety_stock=safety_s)
                    if up: affected.append(up.model_dump())

            threshold_desc = []
            if min_s is not None: threshold_desc.append(f"Min Stock = {min_s}")
            if max_s is not None: threshold_desc.append(f"Max Stock = {max_s}")
            if safety_s is not None: threshold_desc.append(f"Safety Buffer = {safety_s}")

            log_agent_step(
                step_name="Threshold Configuration",
                agent_name="InventoryManagerAgent",
                status="success",
                message=f"Updated thresholds for {sku}: {', '.join(threshold_desc)}"
            )
            state["status"] = "completed"
            state["action_type"] = "update_threshold"
            state["message"] = f"Batas stok (Threshold) untuk {t_data.get('item_name', sku)} berhasil diperbarui ({', '.join(threshold_desc)})."
            state["affected_items"] = affected
            return state

        # Step 1.4: Dynamic PR Review / Inquiries Handler
        if parsed_intent.intent_type == "review_prs":
            p_prompt = user_prompt.lower()
            pending_prs = db.get_purchase_requisitions(status="pending_approval")
            target_list = pending_prs if pending_prs else db.get_purchase_requisitions()

            if any(w in p_prompt for w in ["paling besar", "terbesar", "tertinggi", "nominal tertinggi", "terbanyak", "maksimal"]):
                target_list.sort(key=lambda p: p.grand_total, reverse=True)
                top_prs = target_list[:1] if target_list else []
                state["status"] = "completed"
                state["action_type"] = "review_prs"
                state["generated_prs"] = [p.model_dump() for p in top_prs]
                if top_prs:
                    state["message"] = f"Purchase Requisition pending dengan total nominal TERBESAR adalah {top_prs[0].pr_number} (Supplier: {top_prs[0].supplier_name}) senilai Rp {top_prs[0].grand_total:,.0f}."
                else:
                    state["message"] = "Tidak ditemukan data Purchase Requisition pending di sistem."
                return state

            elif any(w in p_prompt for w in ["paling kecil", "terkecil", "terendah", "minimal"]):
                target_list.sort(key=lambda p: p.grand_total)
                top_prs = target_list[:1] if target_list else []
                state["status"] = "completed"
                state["action_type"] = "review_prs"
                state["generated_prs"] = [p.model_dump() for p in top_prs]
                if top_prs:
                    state["message"] = f"Purchase Requisition pending dengan total nominal TERKECIL adalah {top_prs[0].pr_number} (Supplier: {top_prs[0].supplier_name}) senilai Rp {top_prs[0].grand_total:,.0f}."
                else:
                    state["message"] = "Tidak ditemukan data Purchase Requisition pending di sistem."
                return state

            state["status"] = "completed"
            state["action_type"] = "review_prs"
            state["generated_prs"] = [p.model_dump() for p in target_list]
            state["message"] = f"Terdapat {len(target_list)} Purchase Requisition pending yang memerlukan tinjauan/persetujuan manajer."
            return state

        # Step 1.5: Dynamic Summary & Analysis Handler
        if parsed_intent.intent_type in ["summary", "check_stock"]:
            # If user asked about a specific item
            if parsed_intent.target_skus:
                matched_items = [it for it in all_items if it["sku"] in parsed_intent.target_skus]
                if matched_items:
                    target_it = matched_items[0]
                    state["status"] = "completed"
                    state["action_type"] = "summary"
                    state["message"] = (
                        f"Informasi Produk '{target_it['name']}' ({target_it['sku']}): "
                        f"Stok saat ini: {target_it['current_stock']} {target_it.get('unit', 'unit')}, "
                        f"Batas Min: {target_it['min_stock']}, Max: {target_it['max_stock']}, "
                        f"Harga: Rp {target_it['unit_price']:,.0f}, Supplier: {target_it.get('supplier_name', '-')}. "
                        f"Status: {'MENIPIS' if target_it['current_stock'] <= target_it['min_stock'] else 'NORMAL'}."
                    )
                    state["affected_items"] = matched_items
                    return state

            p_prompt = user_prompt.lower()
            stats = db.get_dashboard_stats()
            low_items = [it for it in db.get_items() if 0 < it.current_stock <= it.min_stock]
            out_items = [it for it in db.get_items() if it.current_stock <= 0]

            # Case A: User explicitly asked about "menipis" (low stock only, strictly exclude 0 stock)
            if any(w in p_prompt for w in ["menipis", "low stock", "hampir habis", "kurang"]) and not any(w in p_prompt for w in ["habis", "kosong"]):
                state["status"] = "completed"
                state["action_type"] = "summary"
                if not low_items:
                    state["message"] = "Kondisi Aman: Tidak ada produk yang menipis. Semua stok di atas batas minimum."
                else:
                    items_str = ", ".join([f"{it.name} ({it.current_stock} {it.unit})" for it in low_items[:8]])
                    state["message"] = f"Daftar Produk Menipis (Low Stock): Terdapat {len(low_items)} barang dengan stok di bawah batas minimum: {items_str}."
                state["affected_items"] = [it.model_dump() for it in low_items]
                return state

            # Case B: User explicitly asked about "habis" (out of stock only, strictly 0 stock)
            elif any(w in p_prompt for w in ["habis", "kosong", "out of stock", "nol"]) and not any(w in p_prompt for w in ["menipis"]):
                state["status"] = "completed"
                state["action_type"] = "summary"
                if not out_items:
                    state["message"] = "Kondisi Aman: Tidak ada produk yang habis (0 unit). Semua produk memiliki saldo stok."
                else:
                    items_str = ", ".join([f"{it.name} (0 {it.unit})" for it in out_items[:8]])
                    state["message"] = f"Daftar Produk Habis (0 Unit): Terdapat {len(out_items)} barang yang stoknya benar-benar habis di gudang: {items_str}."
                state["affected_items"] = [it.model_dump() for it in out_items]
                return state

            # Case C: General overview / Rekap
            else:
                depleted_names = [f"{it.name} ({it.current_stock} {it.unit})" for it in (out_items + low_items)]
                depleted_summary = ", ".join(depleted_names[:6]) if depleted_names else "Semua stok dalam batas aman."

                summary_text = (
                    f"Laporan Inventaris: Total {stats.total_items} SKU terdaftar. "
                    f"Ditemukan {len(low_items)} barang menipis dan {len(out_items)} barang habis (0 unit): {depleted_summary}."
                )
                state["status"] = "completed"
                state["action_type"] = "summary"
                state["message"] = summary_text
                state["affected_items"] = [it.model_dump() for it in (out_items + low_items)]
                return state

        # Step 1.6: If intent is an external notification command
        if parsed_intent.intent_type in ["notify_email", "notify_telegram"]:
            from core.n8n_client import n8n_client
            stats = db.get_dashboard_stats()
            low_items = [it.name for it in db.get_items(status="low_stock")]
            
            n8n_res = await n8n_client.dispatch_notification(
                channel=parsed_intent.notification_channel or "email",
                recipient=parsed_intent.notification_recipient or "management@retail-nusantara.co.id",
                message=parsed_intent.notification_message or user_prompt,
                priority=parsed_intent.urgency,
                metadata={
                    "total_items": stats.total_items,
                    "low_stock_items": low_items,
                    "pending_prs": stats.pending_prs
                }
            )
            state["status"] = "completed"
            state["action_type"] = "n8n_notify"
            state["message"] = f"Instruksi pengiriman {parsed_intent.notification_channel.upper()} telah didelegasikan ke n8n untuk penerima: {parsed_intent.notification_recipient}."
            return state

        # Step 1.7: If intent is an external export/sync command
        if parsed_intent.intent_type == "sync_export":
            from core.n8n_client import n8n_client
            prs_data = [p.model_dump() for p in db.get_purchase_requisitions()]
            items_data = [i.model_dump() for i in db.get_items()]
            
            await n8n_client.dispatch_sync_event(
                event_type="sync_inventory_to_sheets",
                data={"items": items_data, "purchase_requisitions": prs_data}
            )
            state["status"] = "completed"
            state["action_type"] = "n8n_sync"
            state["message"] = "Data katalog dan PR telah dikirimkan ke n8n untuk sinkronisasi Google Sheets / ERP."
            return state

        # Step 2: Identify candidate items matching the prompt criteria
        candidates = []
        p_lower = user_prompt.lower()

        for it in all_items:
            sku = it["sku"]
            cat = it["category"]
            curr = it["current_stock"]
            min_s = it["min_stock"]
            max_s = it["max_stock"]

            # Filter by targeted SKUs if explicitly mentioned
            if parsed_intent.target_skus and sku not in parsed_intent.target_skus:
                continue

            # Filter by category if specified
            if parsed_intent.target_categories and cat not in parsed_intent.target_categories:
                continue

            # Filter by supplier if specified
            if parsed_intent.target_supplier and parsed_intent.target_supplier.lower() not in (it.get("supplier_name", "").lower()):
                continue

            # If no explicit SKU/category was given, standard rule: current_stock <= min_stock
            if not parsed_intent.target_skus and not parsed_intent.target_categories and not parsed_intent.target_supplier:
                if curr > min_s:
                    continue

            # Check if specific quantity was mentioned near this item's name in prompt
            item_specific_qty = None
            it_name_first = (it["name"].split()[0] if it["name"] else "").lower()
            if it_name_first:
                qty_near_match = re.search(rf'{it_name_first}[^0-9\n]{{1,40}}?(\d+)\s*(?:pouch|karton|dus|box|unit|pcs|roll|pack|rim|kg|sak|btl)?', p_lower)
                if qty_near_match:
                    try:
                        item_specific_qty = int(qty_near_match.group(1))
                    except Exception:
                        pass

            # Calculate order quantity
            if item_specific_qty:
                order_qty = item_specific_qty
            elif parsed_intent.quantity_specified:
                order_qty = parsed_intent.quantity_specified
            elif parsed_intent.quantity_strategy == "safety_buffer":
                order_qty = max(1, (max_s - curr) + int(it.get("safety_stock", 5) * 1.5))
            else:
                order_qty = max(1, max_s - curr)

            candidates.append({
                "item": it,
                "order_qty": order_qty,
                "reason": f"Prompt Restock: {parsed_intent.reasoning or 'Permintaan pengadaan user'}"
            })

        state["restock_candidates"] = candidates

        if not candidates:
            log_agent_step(
                step_name="Restock Evaluation",
                agent_name="RestockDecisionAgent",
                status="info",
                message="No inventory items matched the restocking criteria or all stocks are at optimal levels."
            )
            state["status"] = "completed"
            state["message"] = "No restock required. All targeted inventory levels are healthy."
            return state

        # Step 3: Generate 1 Consolidated Purchase Requisition for the request
        state = await self._compile_single_unified_pr(state, urgency=parsed_intent.urgency)
        state["status"] = "completed"
        return state

    async def _compile_single_unified_pr(self, state: RestockAgentState, urgency: str = "NORMAL") -> RestockAgentState:
        """Consolidates all requested candidate items into 1 official Purchase Requisition (PR)."""
        candidates = state.get("restock_candidates", [])
        if not candidates:
            return state

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H%M%S")
        pr_number = f"PR-{now.strftime('%Y%m%d')}-{time_str}"

        # Determine supplier summary
        supplier_names = list(dict.fromkeys([c["item"].get("supplier_name", "Supplier Rekanan") for c in candidates]))
        sup_name = supplier_names[0] if len(supplier_names) == 1 else f"Multi-Supplier ({len(supplier_names)} Rekanan)"
        sup_id = candidates[0]["item"].get("supplier_id", "SUP-MULTI")

        pr_items: List[PurchaseRequisitionItem] = []
        subtotal = 0.0

        for it_entry in candidates:
            item_data = it_entry["item"]
            qty = it_entry["order_qty"]
            uprice = float(item_data.get("unit_price", 0.0))
            tprice = qty * uprice
            subtotal += tprice

            pr_items.append(PurchaseRequisitionItem(
                sku=item_data["sku"],
                item_name=item_data["name"],
                quantity=qty,
                unit=item_data.get("unit", "pcs"),
                unit_price=uprice,
                total_price=tprice,
                current_stock=item_data.get("current_stock", 0),
                min_stock=item_data.get("min_stock", 0),
                reason=it_entry.get("reason", "Permintaan Pengadaan User")
            ))

        tax_amount = subtotal * 0.11
        grand_total = subtotal + tax_amount

        # All PRs start in PENDING_APPROVAL so the manager can review and click approve manually
        initial_status = PRStatus.PENDING_APPROVAL
        notes = f"Purchase Requisition berisi {len(pr_items)} item barang. Menunggu persetujuan manajer."

        pr = PurchaseRequisition(
            pr_number=pr_number,
            created_at=date_str,
            supplier_id=sup_id,
            supplier_name=sup_name,
            items=pr_items,
            subtotal=subtotal,
            tax_rate=0.11,
            tax_amount=tax_amount,
            grand_total=grand_total,
            status=initial_status,
            urgency=urgency,
            notes=notes,
            auto_approved=False,
            approver_name=None,
            approved_at=None
        )

        # Compile official PDF
        try:
            pdf_path = pdf_generator.generate_pr_pdf(pr)
            pr.pdf_path = pdf_path
        except Exception as e:
            pr.pdf_path = None

        # Persist to database
        db.save_purchase_requisition(pr)
        state["generated_prs"] = [pr.model_dump()]
        state["requires_approval"] = True
        state["action_type"] = "review_prs"
        state["message"] = f"Dokumen Purchase Requisition {pr.pr_number} ({len(pr_items)} item, Total: Rp {pr.grand_total:,.0f}) berhasil dibuat dan menunggu persetujuan Anda."

        log_agent_step(
            step_name="PR Generation",
            agent_name="ProcurementAgent",
            status="success",
            message=f"Created consolidated PR {pr.pr_number} with {len(pr_items)} item(s). Total: Rp {pr.grand_total:,.0f}"
        )

        return state

    async def execute_inventory_scan(self) -> RestockAgentState:
        """
        Scans entire catalog for low-stock and out-of-stock items and compiles PRs.
        """
        state: RestockAgentState = {
            "trigger_source": "manual_trigger",
            "logs": [],
            "generated_prs": [],
            "requires_approval": False,
            "status": "processing"
        }

        all_items = db.get_items()
        candidates = []
        for it in all_items:
            if it.current_stock <= it.min_stock:
                order_qty = max(1, (it.max_stock - it.current_stock) + it.safety_stock)
                candidates.append({
                    "item": it.model_dump(),
                    "order_qty": order_qty,
                    "reason": f"Stock ({it.current_stock} {it.unit}) <= Min Threshold ({it.min_stock} {it.unit})"
                })

        state["restock_candidates"] = candidates
        if candidates:
            state = await self._compile_prs_from_candidates(state)
        else:
            state["message"] = "All inventory items are currently above minimum safety thresholds."

        state["status"] = "completed"
        return state

    async def _evaluate_and_generate_prs(self, state: RestockAgentState) -> RestockAgentState:
        """Helper to check catalog and trigger PRs if items are depleted."""
        all_items = db.get_items()
        candidates = []
        for it in all_items:
            if it.current_stock <= it.min_stock:
                order_qty = max(1, (it.max_stock - it.current_stock) + it.safety_stock)
                candidates.append({
                    "item": it.model_dump(),
                    "order_qty": order_qty,
                    "reason": f"Inventory low ({it.current_stock}/{it.min_stock})"
                })
        state["restock_candidates"] = candidates
        if candidates:
            state = await self._compile_prs_from_candidates(state)
        return state

    async def _compile_prs_from_candidates(self, state: RestockAgentState, urgency: str = "NORMAL") -> RestockAgentState:
        """Groups candidate items by supplier and generates official PR documents."""
        candidates = state.get("restock_candidates", [])
        if not candidates:
            return state

        # Group by supplier_id
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for c in candidates:
            sup_id = c["item"].get("supplier_id", "SUP-UNKNOWN")
            if sup_id not in grouped:
                grouped[sup_id] = []
            grouped[sup_id].append(c)

        created_prs: List[PurchaseRequisition] = []
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H%M%S")

        for idx, (sup_id, items_list) in enumerate(grouped.items()):
            pr_number = f"PR-{now.strftime('%Y%m%d')}-{time_str}-{idx+1:02d}"
            sup_name = items_list[0]["item"].get("supplier_name", "Supplier Rekanan")

            pr_items: List[PurchaseRequisitionItem] = []
            subtotal = 0.0

            for it_entry in items_list:
                item_data = it_entry["item"]
                qty = it_entry["order_qty"]
                uprice = float(item_data.get("unit_price", 0.0))
                tprice = qty * uprice
                subtotal += tprice

                pr_items.append(PurchaseRequisitionItem(
                    sku=item_data["sku"],
                    item_name=item_data["name"],
                    quantity=qty,
                    unit=item_data.get("unit", "pcs"),
                    unit_price=uprice,
                    total_price=tprice,
                    current_stock=item_data.get("current_stock", 0),
                    min_stock=item_data.get("min_stock", 0),
                    reason=it_entry.get("reason", "Automated reorder point threshold")
                ))

            tax_amount = subtotal * 0.11
            grand_total = subtotal + tax_amount

            # Check Policy Threshold
            auto_approved = grand_total <= settings.AUTO_APPROVE_THRESHOLD_IDR and urgency != "URGENT"
            initial_status = PRStatus.APPROVED if auto_approved else PRStatus.PENDING_APPROVAL

            notes = f"Generated by Autonomous Agent. {'Auto-approved below 5M IDR threshold.' if auto_approved else 'Awaiting Manager review.'}"

            pr = PurchaseRequisition(
                pr_number=pr_number,
                created_at=date_str,
                supplier_id=sup_id,
                supplier_name=sup_name,
                items=pr_items,
                subtotal=subtotal,
                tax_rate=0.11,
                tax_amount=tax_amount,
                grand_total=grand_total,
                status=initial_status,
                urgency=urgency,
                notes=notes,
                auto_approved=auto_approved,
                approver_name="Auto-Approved (AI Policy Engine)" if auto_approved else None,
                approved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S") if auto_approved else None
            )

            # Compile official Typst PDF
            try:
                pdf_path = pdf_generator.generate_pr_pdf(pr)
                pr.pdf_path = pdf_path
            except Exception as e:
                pr.pdf_path = None

            # Persist to database
            db.save_purchase_requisition(pr)
            created_prs.append(pr)

            # If auto-approved, replenish on-hand stock and dispatch PO to n8n immediately
            updated_items = []
            if auto_approved:
                for pit in pr_items:
                    up_item = db.update_stock(
                        sku=pit.sku,
                        change=pit.quantity,
                        transaction_type="auto_restock_replenishment",
                        ref_doc=pr.pr_number,
                        notes=f"Auto-approved restock: {pit.quantity} {pit.unit} via {pr.pr_number}"
                    )
                    if up_item:
                        updated_items.append(up_item.model_dump())

                from core.n8n_client import n8n_client
                import asyncio
                try:
                    asyncio.create_task(n8n_client.dispatch_approved_po(pr))
                except Exception:
                    pass

            status_msg = f"Created Purchase Requisition {pr.pr_number} for {sup_name} (Total: Rp {grand_total:,.0f}). Status: {pr.status.value}"
            log_agent_step(
                step_name="PR Generation",
                agent_name="DocCompilerAgent",
                status="success",
                message=status_msg,
                details=pr.model_dump()
            )

        state["generated_prs"] = created_prs
        state["affected_items"] = updated_items if 'updated_items' in locals() else []
        has_pending = any(pr.status == PRStatus.PENDING_APPROVAL for pr in created_prs)
        state["requires_approval"] = has_pending
        
        if has_pending:
            state["action_type"] = "review_prs"
            state["message"] = f"Diterbitkan {len(created_prs)} Purchase Requisition (PR). Menunggu persetujuan manajer untuk otomatis menambah stok katalog."
        else:
            state["action_type"] = "restock"
            state["message"] = f"Restock berhasil dijalankan. Diterbitkan {len(created_prs)} PR dan stok katalog diperbarui otomatis."

        return state

    async def execute_document_ingest(self, file_path: str, prompt: str = "", auto_execute: bool = True) -> Dict[str, Any]:
        """
        Multimodal agent that ingests uploaded receipts/invoices/documents and executes user instructions.
        """
        path = Path(file_path)
        doc = await ocr_engine.process_document(str(path))
        
        affected = []
        p_lower = prompt.lower() if prompt else ""

        for it in doc.line_items:
            existing = db.get_item_by_sku(it.sku_guess)
            if existing:
                # Update existing catalog stock
                diff = it.quantity
                updated = db.update_stock(
                    sku=it.sku_guess,
                    change=diff,
                    transaction_type="media_doc_ingest",
                    ref_doc=doc.doc_number,
                    notes=f"Ingested from {doc.doc_type.value}: {path.name}"
                )
                if updated:
                    affected.append(updated.model_dump())
            else:
                # Auto-register new item found in receipt / document
                cat = "General"
                if any(w in it.item_name.lower() for w in ["beras", "minyak", "gula", "indomie", "susu", "makanan"]):
                    cat = "FMCG"
                elif any(w in it.item_name.lower() for w in ["kopi", "teh", "aqua", "air"]):
                    cat = "Food & Beverage"
                elif any(w in it.item_name.lower() for w in ["kertas", "pen", "buku", "map"]):
                    cat = "Office Supplies"
                elif any(w in it.item_name.lower() for w in ["laptop", "kabel", "toner", "mouse"]):
                    cat = "IT & Electronics"

                prefix = cat[:3].upper() if cat else "GEN"
                new_sku = it.sku_guess if it.sku_guess and not it.sku_guess.startswith("SKU-") else f"{prefix}-{abs(hash(it.item_name)) % 9000 + 1000}"

                new_item = InventoryItem(
                    sku=new_sku,
                    name=it.item_name,
                    category=cat,
                    current_stock=it.quantity,
                    min_stock=max(5, int(it.quantity * 0.4)),
                    max_stock=max(20, int(it.quantity * 2.5)),
                    safety_stock=2,
                    unit=it.unit,
                    unit_price=it.unit_price,
                    supplier_id="SUP-002",
                    supplier_name=doc.sender_supplier or "Supplier Eksternal",
                    lead_time_days=3,
                    location_bin=f"RAK-{prefix}-01"
                )
                db.upsert_item(new_item)
                affected.append(new_item.model_dump())

        log_agent_step(
            step_name="Media Document Batch Processing",
            agent_name="MultimodalIngestAgent",
            status="success",
            message=f"Processed document {doc.doc_number}: {len(doc.line_items)} line items synchronized into database."
        )

        return {
            "status": "completed",
            "action_type": "doc_ingest",
            "doc_number": doc.doc_number,
            "doc_type": doc.doc_type.value,
            "sender_supplier": doc.sender_supplier,
            "total_items_count": len(doc.line_items),
            "line_items": [li.model_dump() for li in doc.line_items],
            "affected_items": affected,
            "message": f"Dokumen '{path.name}' ({doc.doc_number}) berhasil diproses! Sebanyak {len(doc.line_items)} produk dalam struk/nota telah disinkronkan ke katalog stok database."
        }


workflow = AutoRestockWorkflow()
