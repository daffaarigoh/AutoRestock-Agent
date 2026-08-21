# AutoRestock-V2: Enterprise Autonomous Restocking & Multimodal Audit Agent System

AutoRestock-V2 is a production-grade, autonomous inventory replenishment and multimodal auditing system built for Indonesian enterprise supply chain and retail warehousing.

## Core Capabilities
- **Intelligent Natural Language Prompt Restock**: Understands Indonesian and English procurement instructions (e.g., *"Restock semua minyak goreng dan beras yang menipis sebanyak 40 unit ke Alfaria segera URGENT"*).
- **Multimodal OCR & Vision Auditor**: Ingests Surat Jalan, Kartu Stok, and Faktur Pembelian, detecting discrepancies with bounding box visual overlays.
- **Enterprise Typst PDF Compiler**: Automatically compiles official, print-ready Purchase Requisitions (PR) with company headers, line items, PPN 11%, grand totals, and approval signatures.
- **Autonomous Multi-Agent State Machine**: Evaluates stock levels, EOQ, safety stock buffers, groups orders by supplier, and applies automated policy approval thresholds (< 5M IDR auto-approved).
- **Real-Time Web Console & Streaming**: Sleek business dashboard with WebSocket log broadcasting, drag-and-drop document inspector, and approval workflows.
- **Telegram Bot Integration**: Remote notifications and inline approval buttons for warehouse and procurement managers.

---

## Architecture Overview

```
AutoRestock-V2/
├── agents/                  # Multi-agent state machine and workflow
│   ├── state.py             # LangGraph state schemas
│   └── workflow.py          # Multi-agent graph orchestrator
├── api/                     # FastAPI backend & WebSocket stream
│   ├── main.py              # Application entrypoint & static mount
│   └── routers/             # Modular REST routers (Inventory, Ingest, Agent, Approvals, Stream)
├── bot/                     # Telegram Bot interactive approval integration
│   └── telegram_bot.py
├── core/                    # Core configuration, LLM client, schemas, observability
│   ├── config.py            # Pydantic Settings & storage directory initialization
│   ├── llm_client.py        # LLM client & NLP prompt comprehension engine
│   ├── observability.py     # Structured logger & WebSocket event broadcaster
│   └── schemas.py           # Enterprise Pydantic v2 schemas
├── database/                # SQLite persistence layer
│   ├── db.py                # CRUD queries, transactions, and analytics
│   └── seed_data.py         # Realistic Indonesian enterprise catalog dataset
├── docgen/                  # Document compiler engine
│   └── pdf_generator.py     # Typst-powered Purchase Requisition PDF compiler
├── mcp_server/              # Model Context Protocol (MCP) tool bindings
│   └── tools.py
├── multimodal/              # Computer vision and OCR subsystem
│   ├── ocr_engine.py        # Structured OCR extractor for Surat Jalan & Kartu Stok
│   ├── vision_auditor.py    # Discrepancy detector & reconciliation
│   └── visualizer.py        # Bounding box & annotation generator
├── scripts/                 # Utility scripts & asset generators
│   ├── generate_sample_assets.py
│   └── demo_full_cycle.py
├── storage/                 # Persistent storage (DB, PDFs, annotated images, uploads)
├── tests/                   # Comprehensive automated test suite
│   ├── run_tests.py
│   └── test_api_and_pipeline.py
├── web/                     # Enterprise Business UI Dashboard
│   ├── static/css/dashboard.css
│   ├── static/js/dashboard.js
│   └── templates/index.html
├── seed_demo.py             # Complete system seed and initial restock run
└── .env                     # Environment configuration
```

---

## Quick Start Guide

### 1. Initialize & Seed Database
```powershell
python seed_demo.py
```

### 2. Launch the Web Dashboard
```powershell
python -m uvicorn api.main:app --host 0.0.0.0 --port 8050 --reload
```
Open your browser at `http://localhost:8050`.

### 3. Run the Full Test Suite
```powershell
python tests/run_tests.py
```

### 4. Run CLI Demo Cycle
```powershell
python scripts/demo_full_cycle.py
```

---

## Key Features & User Interface

1. **Dashboard Overview**: Key metrics (Active SKUs, Low Stock, Out-of-Stock, Pending PRs, Inventory Value, Pending PR Value).
2. **AI Restock Copilot**: Conversational prompt input with instant intent explanation and generated PR preview.
3. **Katalog Inventaris**: Live inventory table with category/status filters, instant search, and stock adjustment modal.
4. **OCR & Ingest Hub**: Dual-column viewer displaying extracted line items table alongside annotated document bounding boxes.
5. **Persetujuan PR / PO**: Approval manager with one-click approve/reject actions and PDF download.
6. **Audit Selisih Stok**: Discrepancy log tracking physical recount variance, risk severity, and proposed actions.
7. **Live Terminal Agent**: Real-time WebSocket console streaming agent thoughts and decisions.
