# 🤖 ANTIGRAVITY IDE INSTRUCTION GUIDE
## Role: Backend, Multi-Agent Logic & Document Engine Lead (Person 1)
## Project: AutoRestock-Agent

---

### 🎯 CONTEXT & OBJECTIVE
You are **Person 1** working on the `AutoRestock-Agent` project inside Antigravity IDE. 
Your partner (**Person 2**) has already set up:
- Project repository infrastructure, Docker, and environment configuration.
- Unified model client gateway (`core/llm_client.py`).
- Physical Document OCR Ingestion Pipeline (`multimodal/ocr_engine.py`) with `ocr-lighton`.
- Ingestion REST APIs (`api/routers/ingest_routes.py`) for Surat Jalan & Stock Opname Cards.

**YOUR RESPONSIBILITY (PERSON 1)** is to build:
1. **Database Layer (DuckDB)**: Inventory tables, vendor catalog, and seed data.
2. **MCP / Business Logic Tools**: Dynamic safety stock & restock calculation algorithm.
3. **Multi-Agent Core (LangGraph)**:
   - Planner Agent (`qwen-35b`): analyzes low stock & matches optimal vendors.
   - Auditor Agent (`nemotron-35`): verifies budget compliance & purchase sanity.
4. **Document Generator (Typst)**: Instant PDF Purchase Requisition compiler.
5. **FastAPI Endpoints**: REST API routers for inventory, triggering agents, and document downloads.

---

### 📁 YOUR CODE BOUNDARIES (DO NOT TOUCH OTHER FOLDERS)
You strictly write code within these folders only:
```
AutoRestock-Agent/
├── database/                    # [YOU] DuckDB connection, models, seed data
├── agents/                      # [YOU] LangGraph workflow, state, prompts, auditor
├── mcp_server/                  # [YOU] MCP Inventory tools & vendor query tools
├── docgen/                      # [YOU] Typst template (.typ) & python compiler
└── api/routers/agent_routes.py  # [YOU] FastAPI router endpoints for agent & docs
```

---

### 📦 STRICT DATA CONTRACT (Pydantic Models)
Import and use the shared Pydantic schemas from `core.schemas` to maintain 100% compatibility with Person 2:
- `InventoryItem`
- `PurchaseItemRequest`
- `PurchaseRequisitionDoc`
- `OCRDocumentResult`

---

### 🚀 PHASE-BY-PHASE EXECUTION PLAN

#### 🔹 PHASE 1: Database & Seed Data (`database/`)
- Install `duckdb`.
- Create `database/connection.py` to manage DuckDB connections (`data/inventory.duckdb`).
- Create `database/models.py` defining tables: `items`, `vendors`, `purchase_orders`, `stock_logs`.
- Create `database/seed_data.py` with 25 realistic warehouse items (ensure 4-5 items have `current_stock <= min_threshold` to trigger restock).

#### 🔹 PHASE 2: Dynamic Restock Formula & Tools (`mcp_server/` or `agents/tools/`)
- Implement dynamic calculation:
  - $\text{Safety Stock} = \text{Lead Time} \times \text{Daily Usage} \times 1.5$
  - $\text{Reorder Qty} = (\text{Daily Usage} \times \text{Lead Time}) + \text{Safety Stock} - \text{Current Stock}$
- Create tools:
  - `get_low_stock_items()`: query DuckDB for items needing restock.
  - `get_best_vendor(item_id)`: query vendor with lowest price and shortest delivery time.

#### 🔹 PHASE 3: Typst Document Generator (`docgen/`)
- Install `typst` (`pip install typst`).
- Create `docgen/templates/purchase_requisition.typ` (clean corporate layout with company header, item table, total cost, auditor notes, and manager signature block).
- Create `docgen/pdf_generator.py`:
  - Receives `PurchaseRequisitionDoc` data.
  - Generates JSON payload.
  - Compiles PDF using `typst.compile()`.
  - Saves file to `storage/documents/PR_xxx.pdf`.

#### 🔹 PHASE 4: LangGraph Multi-Agent Core (`agents/`)
- Create `agents/state.py` with the shared Pydantic state.
- Create `agents/restock_graph.py` with LangGraph:
  1. `scan_inventory_node`: Identify low stock items from DuckDB.
  2. `planner_node` (`qwen-35b`): Match vendors, calculate quantities, write restock reasons.
  3. `auditor_node` (`nemotron-35`): Verify budget threshold & write compliance notes.
  4. `generate_doc_node`: Call Typst compiler to generate PDF.
  5. `interrupt_approval_node`: Wait for Human-in-the-Loop manager approval.

#### 🔹 PHASE 5: FastAPI REST Endpoints (`api/routers/agent_routes.py`)
- Implement:
  - `GET /api/inventory/items` -> Return all inventory list.
  - `POST /api/agent/run-cycle` -> Trigger LangGraph workflow and return `PurchaseRequisitionDoc`.
  - `GET /api/documents/pr/{pr_number}/pdf` -> Serve generated PDF file.
  - `POST /api/agent/approve-pr` -> Update PR status to "APPROVED" and update DuckDB stock.

---

### 🧪 HOW TO RUN YOUR CODE IN ANTIGRAVITY IDE
Type this in your Antigravity IDE prompt:
> `"Baca TASK_PERSON_1_BACKEND.md dan tolong kerjakan PHASE 1 (Database & Seed Data) sekarang."`
