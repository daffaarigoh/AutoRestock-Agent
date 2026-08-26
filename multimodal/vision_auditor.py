import logging
import uuid

from core.llm_client import gateway
from core.schemas import BoundingBox, DetectedShelfItem, StockStatus, VisionAuditResult
from multimodal.visualizer import BoundingBoxVisualizer

logger = logging.getLogger(__name__)


class VisionAuditor:
    """
    Analyzes warehouse shelf and rack photos using 'qwen-35b-vision',
    detects depleted stock slots, extracts bounding box coordinates,
    and produces visual audit overlays.
    """

    @classmethod
    async def audit_shelf_image(
        cls,
        image_bytes: bytes,
        original_filename: str | None = "shelf.jpg"
    ) -> VisionAuditResult:
        """
        Executes end-to-end visual shelf audit with bounding box annotation.
        """
        raw_audit = await gateway.vision_shelf_audit(image_bytes)

        detected_items = []
        for raw_item in raw_audit.get("detected_items", []):
            raw_bbox = raw_item.get("bbox", {})
            bbox = BoundingBox(
                ymin=float(raw_bbox.get("ymin", 0.0)),
                xmin=float(raw_bbox.get("xmin", 0.0)),
                ymax=float(raw_bbox.get("ymax", 1.0)),
                xmax=float(raw_bbox.get("xmax", 1.0)),
            )

            status_str = raw_item.get("status", "NORMAL").upper()
            try:
                status_enum = StockStatus(status_str)
            except ValueError:
                status_enum = StockStatus.NORMAL

            detected_items.append(
                DetectedShelfItem(
                    slot_id=raw_item.get("slot_id", "SLOT-UNKNOWN"),
                    item_label=raw_item.get("item_label", "Unknown Product"),
                    status=status_enum,
                    confidence=float(raw_item.get("confidence", 0.9)),
                    bbox=bbox,
                    notes=raw_item.get("notes"),
                )
            )

        # Generate visual overlay image
        annotated_filename = f"annotated_{uuid.uuid4().hex[:8]}.jpg"
        output_path = BoundingBoxVisualizer.annotate_shelf_image(
            image_bytes=image_bytes,
            detected_items=detected_items,
            output_filename=annotated_filename,
        )

        relative_url = f"/api/annotated/{output_path.name}"

        return VisionAuditResult(
            image_filename=original_filename or "shelf.jpg",
            total_slots_scanned=raw_audit.get("total_slots_scanned", len(detected_items)),
            empty_slots_count=raw_audit.get("empty_slots_count", sum(1 for i in detected_items if i.status == StockStatus.CRITICAL_EMPTY)),
            low_stock_count=raw_audit.get("low_stock_count", sum(1 for i in detected_items if i.status == StockStatus.LOW)),
            detected_items=detected_items,
            annotated_image_url=relative_url,
            audit_summary=raw_audit.get("audit_summary", "Visual shelf scan completed."),
        )
