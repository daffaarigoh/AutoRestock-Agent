import io
import uuid
from pathlib import Path
from typing import List
from PIL import Image, ImageDraw, ImageFont

from core.config import settings
from core.schemas import DetectedShelfItem, StockStatus


class BoundingBoxVisualizer:
    """
    Renders visual bounding box overlays and status badges on shelf images.
    """

    COLOR_MAP = {
        StockStatus.CRITICAL_EMPTY: {"stroke": "#EF4444", "fill": "#FEE2E2", "text_bg": "#DC2626"},
        StockStatus.LOW: {"stroke": "#F59E0B", "fill": "#FEF3C7", "text_bg": "#D97706"},
        StockStatus.NORMAL: {"stroke": "#10B981", "fill": "#D1FAE5", "text_bg": "#059669"},
        StockStatus.DAMAGED: {"stroke": "#8B5CF6", "fill": "#EDE9FE", "text_bg": "#7C3AED"},
    }

    @classmethod
    def annotate_shelf_image(
        cls,
        image_bytes: bytes,
        detected_items: List[DetectedShelfItem],
        output_filename: str = None,
    ) -> Path:
        """
        Draws bounding boxes and labels onto the image and saves it to storage/annotated/
        """
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        width, height = image.size

        # Create overlay for semi-transparent fills
        overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        draw = ImageDraw.Draw(image)

        # Basic default font
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        for item in detected_items:
            bbox = item.bbox
            x1 = int(bbox.xmin * width)
            y1 = int(bbox.ymin * height)
            x2 = int(bbox.xmax * width)
            y2 = int(bbox.ymax * height)

            colors = cls.COLOR_MAP.get(item.status, cls.COLOR_MAP[StockStatus.NORMAL])

            # Draw outer rectangle
            draw.rectangle([x1, y1, x2, y2], outline=colors["stroke"], width=4)

            # Draw badge header on top
            label_text = f"[{item.status.value}] {item.item_label} ({int(item.confidence * 100)}%)"
            
            # Text bounding box calculation
            text_pad = 6
            text_x = x1 + 4
            text_y = max(4, y1 - 20)
            
            # Badge background
            draw.rectangle(
                [text_x - 2, text_y - 2, text_x + len(label_text) * 7 + text_pad, text_y + 16],
                fill=colors["text_bg"]
            )
            draw.text((text_x, text_y), label_text, fill="#FFFFFF", font=font)

        if not output_filename:
            output_filename = f"annotated_shelf_{uuid.uuid4().hex[:8]}.jpg"

        output_path = settings.ANNOTATED_DIR / output_filename
        image.save(output_path, quality=95)
        return output_path
