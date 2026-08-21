"""
Multimodal Vision Auditor and Discrepancy Reconciliation Engine
Cross-references OCR document findings against current database stock levels and detects warehouse discrepancies.
"""

from typing import List, Optional
from core.schemas import (
    ExtractedDocument,
    DiscrepancyReport,
    DiscrepancyItem,
    DiscrepancySeverity,
    DocumentType
)
from core.observability import log_agent_step
from database.db import db


class VisionAuditor:
    def __init__(self):
        pass

    def audit_document(self, doc: ExtractedDocument) -> DiscrepancyReport:
        """
        Performs deep verification of document data vs database inventory records.
        """
        log_agent_step(
            step_name="Audit & Reconciliation",
            agent_name="VisionAuditor",
            status="running",
            message=f"Reconciling document {doc.doc_number} ({doc.doc_type.value}) with warehouse database..."
        )

        discrepancies: List[DiscrepancyItem] = []

        for item in doc.line_items:
            db_item = db.get_item_by_sku(item.sku_guess) if item.sku_guess else None
            
            if not db_item:
                continue

            # Scenario A: For Stock Card (Kartu Stok) or Physical Audit
            if doc.doc_type in [DocumentType.KARTU_STOK, DocumentType.PHYSICAL_AUDIT]:
                # In stock card, doc_quantity is the recorded balance on paper/card.
                diff = item.quantity - db_item.current_stock
                if diff != 0:
                    severity = DiscrepancySeverity.HIGH if abs(diff) > 5 else DiscrepancySeverity.MEDIUM
                    reason = f"Paper card balance shows {item.quantity} {item.unit}, but system database records {db_item.current_stock} {item.unit}."
                    suggested_action = f"Conduct physical shelf recount in {db_item.location_bin} and adjust system balance by {diff:+d} {item.unit}."
                    
                    disc_item = DiscrepancyItem(
                        sku=db_item.sku,
                        item_name=db_item.name,
                        doc_quantity=item.quantity,
                        recorded_stock=db_item.current_stock,
                        physical_count=item.quantity,
                        diff_quantity=diff,
                        severity=severity,
                        reason=reason,
                        suggested_action=suggested_action
                    )
                    discrepancies.append(disc_item)
                    db.record_discrepancy(doc.doc_number, doc.doc_type.value, disc_item)

            # Scenario B: For Surat Jalan / Delivery Orders
            elif doc.doc_type == DocumentType.SURAT_JALAN:
                # If incoming delivery exceeds maximum warehouse capacity
                if (db_item.current_stock + item.quantity) > db_item.max_stock:
                    overage = (db_item.current_stock + item.quantity) - db_item.max_stock
                    disc_item = DiscrepancyItem(
                        sku=db_item.sku,
                        item_name=db_item.name,
                        doc_quantity=item.quantity,
                        recorded_stock=db_item.current_stock,
                        physical_count=None,
                        diff_quantity=overage,
                        severity=DiscrepancySeverity.LOW,
                        reason=f"Incoming delivery exceeds maximum storage capacity by {overage} {item.unit}.",
                        suggested_action=f"Assign overflow storage bin adjacent to {db_item.location_bin}."
                    )
                    discrepancies.append(disc_item)
                    db.record_discrepancy(doc.doc_number, doc.doc_type.value, disc_item)

        requires_review = any(d.severity in [DiscrepancySeverity.HIGH, DiscrepancySeverity.CRITICAL] for d in discrepancies)
        
        summary = (
            f"Audit finished: {len(discrepancies)} discrepancy item(s) detected."
            if discrepancies
            else "Audit finished: All line items match database inventory specifications perfectly."
        )

        status_flag = "warning" if discrepancies else "success"
        log_agent_step(
            step_name="Audit & Reconciliation",
            agent_name="VisionAuditor",
            status=status_flag,
            message=summary,
            details={"discrepancies_count": len(discrepancies), "requires_review": requires_review}
        )

        return DiscrepancyReport(
            doc_number=doc.doc_number,
            doc_type=doc.doc_type,
            discrepancies=discrepancies,
            total_discrepancies=len(discrepancies),
            requires_manager_review=requires_review,
            summary=summary
        )


vision_auditor = VisionAuditor()
