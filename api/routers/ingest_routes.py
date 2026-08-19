from fastapi import APIRouter, File, HTTPException, UploadFile
from core.schemas import OCRDocumentResult
from multimodal.ocr_engine import OCREngine

router = APIRouter(prefix="/api/ingest", tags=["Document OCR Ingestion"])


@router.post("/delivery-note", response_model=OCRDocumentResult)
async def ingest_delivery_note(file: UploadFile = File(...)):
    """
    Ingests a scanned Surat Jalan / Delivery Note using LightOn OCR
    to record incoming restocked inventory items.
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
    return result


@router.post("/stock-opname", response_model=OCRDocumentResult)
async def ingest_stock_opname_card(file: UploadFile = File(...)):
    """
    Ingests a scanned physical Kartu Stok / Stock Opname Sheet using LightOn OCR.
    Enables automatic sync of manual physical stock counting with the database.
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
