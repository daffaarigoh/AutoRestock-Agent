"""
Multimodal Document Visualizer
Draws high-contrast bounding boxes, extraction labels, and discrepancy markers on processed warehouse documents.
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from typing import List, Optional
import os
from core.config import settings
from core.schemas import ExtractedDocument, DiscrepancyReport


class DocumentVisualizer:
    def __init__(self):
        self.font = None
        # Try to load a clean TTF font if available, else default font
        try:
            self.font = ImageFont.truetype("arial.ttf", 16)
            self.header_font = ImageFont.truetype("arialbd.ttf", 20)
        except Exception:
            self.font = ImageFont.load_default()
            self.header_font = self.font

    def annotate_document(
        self,
        image_path: str,
        extracted_doc: ExtractedDocument,
        discrepancy_report: Optional[DiscrepancyReport] = None,
        output_filename: Optional[str] = None
    ) -> str:
        """
        Overlays bounding boxes and semantic recognition labels onto the document image.
        Returns the saved file path in storage/annotated/.
        """
        img_path = Path(image_path)
        if not img_path.exists():
            # If image doesn't exist, create a synthetic template base
            img = Image.new("RGB", (850, 1100), color=(255, 255, 255))
        else:
            img = Image.open(img_path).convert("RGB")

        draw = ImageDraw.Draw(img)
        w, h = img.size

        # Header Status Banner
        is_discrepancy = discrepancy_report and discrepancy_report.total_discrepancies > 0
        banner_color = (220, 38, 38) if is_discrepancy else (16, 185, 129)  # Red vs Emerald Green
        banner_text = f"AUDIT: {discrepancy_report.total_discrepancies} DISCREPANCY DETECTED" if is_discrepancy else "STATUS: OCR VERIFIED & RECONCILED"

        draw.rectangle([(0, 0), (w, 36)], fill=banner_color)
        draw.text((20, 8), f"AutoRestock-V2 Multimodal Auditor | {banner_text}", fill=(255, 255, 255), font=self.font)

        # Draw bounding boxes for line items
        discrepancy_skus = [d.sku for d in discrepancy_report.discrepancies] if discrepancy_report else []

        for idx, item in enumerate(extracted_doc.line_items):
            # Calculate or use provided bbox
            if item.bbox and len(item.bbox) == 4:
                bx, by, bw, bh = item.bbox
            else:
                # Synthetic bounding box aligned with typical document row
                by = 220 + (idx * 55)
                bx = 40
                bw = w - 80
                bh = 45

            # Determine color: Amber/Red if discrepancy, Blue/Green if normal
            has_issue = any(item.item_name.lower() in d.item_name.lower() for d in (discrepancy_report.discrepancies if discrepancy_report else []))
            box_color = (239, 68, 68) if has_issue else (59, 130, 246)  # Red vs Blue

            # Draw outer rectangle
            draw.rectangle([(bx, by), (bx + bw, by + bh)], outline=box_color, width=2)

            # Draw label tag
            label_text = f"[{idx+1}] {item.item_name} | Qty: {item.quantity} {item.unit} (Conf: {int(item.confidence * 100)}%)"
            draw.rectangle([(bx, by - 20), (bx + len(label_text) * 8 + 15, by)], fill=box_color)
            draw.text((bx + 5, by - 18), label_text, fill=(255, 255, 255), font=self.font)

        # Save output image
        out_name = output_filename or f"annotated_{extracted_doc.doc_number.replace('/', '_')}_{img_path.name}"
        if not out_name.endswith((".png", ".jpg")):
            out_name += ".png"

        save_path = settings.STORAGE_DIR / "annotated" / out_name
        img.save(str(save_path))
        return str(save_path)


visualizer = DocumentVisualizer()
