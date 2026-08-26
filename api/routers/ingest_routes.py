from fastapi import APIRouter, File, HTTPException, UploadFile

from core.schemas import OCRDocumentResult
from multimodal.ocr_engine import OCREngine

router = APIRouter(prefix="/api/ingest", tags=["Document OCR Ingestion"])


@router.post("/delivery-note", response_model=OCRDocumentResult)
async def ingest_delivery_note(file: UploadFile = File(...)):
    """
    Ingests a scanned Surat Jalan / Delivery Note using LightOn OCR
    and increments incoming restocked inventory items directly in DuckDB.
    """
    if not file.content_type.startswith(("image/", "application/pdf")):
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload an image or PDF.")

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    result = await OCREngine.process_document(
        contents,
        doc_type_hint="SURAT_JALAN",
        filename=file.filename
    )

    # Persist incoming goods into DuckDB items stock
    try:
        from database.db import get_db_connection
        conn = get_db_connection()
        for item in result.items:
            conn.execute("""
                UPDATE items 
                SET current_stock = current_stock + ? 
                WHERE item_id = ? OR name = ?;
            """, [item.qty_recorded, item.sku, item.item_name])
        conn.close()
    except Exception as e:
        print(f"[INGEST] Warning syncing delivery note to DuckDB: {e}")

    return result


@router.post("/stock-opname", response_model=OCRDocumentResult)
async def ingest_stock_opname_card(file: UploadFile = File(...)):
    """
    Ingests a scanned physical Kartu Stok / Stock Opname Sheet using LightOn OCR.
    Updates DuckDB current_stock with physical counted quantities to trigger accurate replenishment.
    """
    if not file.content_type.startswith(("image/", "application/pdf")):
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload an image or PDF.")

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    result = await OCREngine.process_document(
        contents,
        doc_type_hint="KARTU_STOK_OPNAME",
        filename=file.filename
    )

    # Update physical stock in DuckDB
    try:
        from database.db import get_db_connection
        conn = get_db_connection()
        for item in result.items:
            conn.execute("""
                UPDATE items 
                SET current_stock = ? 
                WHERE item_id = ? OR name = ?;
            """, [item.qty_recorded, item.sku, item.item_name])
        conn.close()
    except Exception as e:
        print(f"[INGEST] Warning syncing stock opname to DuckDB: {e}")

    return result


@router.post("/invoice", response_model=OCRDocumentResult)
async def ingest_supplier_invoice(file: UploadFile = File(...)):
    """
    Ingests a scanned Supplier Invoice using LightOn OCR to record purchasing receipts.
    """
    if not file.content_type.startswith(("image/", "application/pdf")):
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload an image or PDF.")

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    result = await OCREngine.process_document(
        contents,
        doc_type_hint="INVOICE",
        filename=file.filename
    )
    return result



@router.post("/shelf-photo")
async def ingest_shelf_photo(file: UploadFile = File(...)):
    """
    Ingests warehouse shelf/rack photo using qwen-35b-vision to detect empty slots and bounding boxes.
    """
    from multimodal.vision_auditor import VisionAuditor

    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload an image.")

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    result = await VisionAuditor.audit_shelf_image(
        contents,
        original_filename=file.filename
    )
    return result

