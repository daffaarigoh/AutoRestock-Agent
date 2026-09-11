<div align="center">
  <h1>🏢 PT BALI TOWERINDO SENTRA TBK</h1>
  <h3>📦 AutoRestock-Agent — Autonomous Multi-Agent Procurement & Enterprise Intelligence Platform</h3>
  <p>
    <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python Version" />
    <img src="https://img.shields.io/badge/FastAPI-0.100+-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/LangGraph-AI%20Orchestrator-7C3AED?style=for-the-badge&logo=openai&logoColor=white" alt="LangGraph" />
    <img src="https://img.shields.io/badge/DuckDB-Enterprise%20OLAP-FFF000?style=for-the-badge&logo=duckdb&logoColor=black" alt="DuckDB" />
    <img src="https://img.shields.io/badge/Typst-Blazing%20PDF-239DAD?style=for-the-badge&logo=typst&logoColor=white" alt="Typst" />
    <img src="https://img.shields.io/badge/SSE-Realtime%20Stream-FF4500?style=for-the-badge" alt="SSE" />
  </p>
</div>

---

## 📝 Executive Overview

**AutoRestock-Agent** is an enterprise-grade autonomous multi-agent operating system engineered for **PT Bali Towerindo Sentra Tbk** (IDX: `BALI`). Built upon **FastAPI**, **LangGraph**, **DuckDB**, and **Typst Engine**, the platform automates and orchestrates mission-critical operations across three core corporate divisions and enterprise administration:

1. **📦 Schema A — Inventory & Logistics Hubs (`usera`)**:
   Autonomous regional stock monitoring across 7 logistics hubs, algorithmic reorder calculations (*Reorder Point & Safety Stock*), multi-agent Purchase Requisition (PR) compilation, single-consolidated Purchase Order (PO) issuance, and single-click regional Goods Receipt.
2. **👥 Schema B — Human Resources & Field Operations (`userb`)**:
   Field technician/rigger leave request lifecycle, automated corporate PDF generation, pending leave audit workflows (`WF-847DA5`), interactive manager email authorization, and real-time annual leave quota balance mutation.
3. **💼 Schema C — Finance & Commercial Leasing (`userc`)**:
   Master Lease Agreement (MLA) contract onboarding for telecom operators (Telkomsel, Indosat Ooredoo Hutchison, XL Axiata, Smartfren), contractual billing schedules, financial authorization, and automated revenue invoice PDF compilation with 11% Indonesian VAT (*PPN*).
4. **👑 Enterprise Administration & Workflow Orchestration (`admin`)**:
   Natural language-to-JSON dynamic workflow compilation, cross-tenant database governance, real-time audit tracing, and system health monitoring.

---

## 🌐 Master Enterprise Architecture (Macro View)

The following master diagram illustrates how natural language prompts and web interactions flow through the central AI Gateway and Semantic Router, routing dynamically to the appropriate corporate division engine while sharing core OLAP storage, typesetting, and notification services:

```mermaid
flowchart TD
    %% USER & CLIENT INGRESS
    Client([Corporate User / Admin]) -->|Natural Language Prompt / Web Dashboard| Gateway["Enterprise AI Gateway & Semantic Router<br/>(agents/router.py)"]

    %% DISPATCH CHANNELS
    Gateway -->|Tenant: INVENTORY / usera| EngineA["Schema A: Logistics & Procurement Engine<br/>(agents/planner.py & auditor.py)"]
    Gateway -->|Tenant: HR / userb| EngineB["Schema B: Workforce & HR Management Engine<br/>(api/routers/balitower_routes.py)"]
    Gateway -->|Tenant: FINANCE / userc| EngineC["Schema C: Finance & Commercial Leasing Engine<br/>(agents/json_executor.py)"]
    Gateway -->|Role: ADMIN / admin| Orchestrator["Dynamic Workflow Orchestrator<br/>(Natural Language ➔ JSON Execution Graph)"]

    %% WORKFLOW ORCHESTRATOR LINK
    Orchestrator -.->|Dispatches Dynamic Graph| EngineA & EngineB & EngineC

    %% SHARED ENTERPRISE INFRASTRUCTURE
    EngineA & EngineB & EngineC --> SharedDB[("DuckDB Enterprise OLAP Engine<br/>(Row-Level Security & Heterogeneous Schemas)")]
    EngineA & EngineB & EngineC --> DocGen["DocGen Typst Engine<br/>(Vector PDFs: PR, PO, Leave Forms, MLA Invoices)"]
    EngineA & EngineB & EngineC --> Dispatcher["SMTP Notification Engine<br/>(Interactive Email Authorization Buttons)"]

    %% FEEDBACK LOOP
    SharedDB & DocGen & Dispatcher -.->|Real-Time SSE Stream| Client

    %% STYLING
    style Client fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#fff
    style Gateway fill:#1e293b,stroke:#818cf8,stroke-width:2px,color:#fff
    style EngineA fill:#0284c7,stroke:#0369a1,stroke-width:2px,color:#fff
    style EngineB fill:#059669,stroke:#047857,stroke-width:2px,color:#fff
    style EngineC fill:#d97706,stroke:#b45309,stroke-width:2px,color:#fff
    style Orchestrator fill:#7c3aed,stroke:#6d28d9,stroke-width:2px,color:#fff
    style SharedDB fill:#e2e8f0,stroke:#334155,stroke-width:2px,color:#0f172a
    style DocGen fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#0f172a
    style Dispatcher fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#0f172a
```

---

## 🔄 Detailed Division Workflows (Micro Level)

### 📦 Pipeline A: Autonomous Inventory Replenishment & Goods Receipt (`usera`)

This workflow governs physical logistics across 7 regional hubs (`WH-JKT-01`, `WH-BDG-01`, `WH-SBY-01`, `WH-SMG-01`, `WH-MDN-01`, `WH-MKS-01`, `WH-DPS-01`).

```mermaid
flowchart TD
    %% PHASE 1: DETECTION & PLANNING
    subgraph A_Phase1 ["1. Regional Stock Inspection & Multi-Agent Planning"]
        A1[("DuckDB: stock_balances<br/>(7 Regional Logistics Hubs)")] -->|Stock <= Reorder Point| A2("Trigger: Copilot Chat / Auto Scheduler")
        A2 --> A3["Planner Agent (Nemotron-35)<br/>Calculate EOQ & Safety Stock, Match Best Suppliers"]
        A3 --> A4["Auditor Agent (Nemotron-35)<br/>Audit Spending Caps & Budget Compliance"]
        A4 --> A5{"DocGen Typst PR"}
        A5 --> A6["Official PR Document Draft<br/>(Status: PENDING)"]
    end

    %% PHASE 2: MANAGERIAL APPROVAL
    subgraph A_Phase2 ["2. Human-In-The-Loop (HITL) Authorization"]
        A6 --> A7["SMTP Email Dispatcher<br/>(Interactive Email with Quick Approve/Reject Buttons)"]
        A6 -.->|SSE Real-Time Sync| A8["Web Dashboard: PR Tab<br/>(Badge: PENDING)"]
        A7 & A8 --> A9{"Manager Authorization"}
        A9 -->|Reject| A10["PR REJECTED<br/>Budget Allocation Released & Stock Preserved"]
    end

    %% PHASE 3: CONSOLIDATED PO ISSUANCE
    subgraph A_Phase3 ["3. Consolidated Purchase Order (PO) Issuance"]
        A9 -->|Approve| A11["PR APPROVED"]
        A11 --> A12["Consolidated PO Issued<br/>(Status: ORDERED)"]
        A12 --> A13["DocGen Typst PO<br/>(11% VAT + Indonesian Words + Specifications)"]
        A12 --> A14["Web Dashboard: PO Tab<br/>(1 Consolidated PO Row + 'Terima Barang' Button)"]
    end

    %% PHASE 4: GOODS RECEIPT & STOCK UPDATE
    subgraph A_Phase4 ["4. Physical Delivery & Single-Click Goods Receipt"]
        A14 -->|Shipment Arrives at Regional Warehouse| A15["Click 'Terima Barang' / Copilot Prompt"]
        A15 --> A16["PO Status Updated: DELIVERED<br/>(Actual Arrival Date Timestamped)"]
        A16 --> A17[("DuckDB: stock_balances<br/>(Target Warehouse Balance Incremented)")]
        A17 --> A18["Stock Health Restored:<br/>CRITICAL / LOW_STOCK ➔ NORMAL 🟢"]
    end

    style A_Phase1 fill:#f8fafc,stroke:#0284c7,stroke-width:1.5px
    style A_Phase2 fill:#fefce8,stroke:#ca8a04,stroke-width:1.5px
    style A_Phase3 fill:#f0fdf4,stroke:#16a34a,stroke-width:1.5px
    style A_Phase4 fill:#fdf4ff,stroke:#9333ea,stroke-width:1.5px
    style A1 fill:#e0f2fe,stroke:#0284c7
    style A6 fill:#fef08a,stroke:#ca8a04
    style A12 fill:#bbf7d0,stroke:#16a34a
    style A17 fill:#f5d0fe,stroke:#9333ea
```

---

### 👥 Pipeline B: Field Workforce Leave Management & Quota Deduction (`userb`)

This workflow governs field technicians and tower riggers, ensuring leave requests undergo managerial verification before annual balances are deducted.

```mermaid
flowchart TD
    subgraph B_Workflow ["Field Workforce Leave Authorization Lifecycle"]
        B1([Technician / Rigger]) -->|Submit Leave Request| B2["AI Leave Form / Copilot Prompt<br/>(Start Date, End Date, Reason, Substitute)"]
        B2 --> B3["Record in DuckDB: leave_requests<br/>(Status: PENDING_APPROVAL)"]
        B3 --> B4["DocGen Typst Engine<br/>(Compile Official Corporate Leave Form PDF)"]
        B4 --> B5["Interactive HR Email Dispatcher<br/>(Sends Email to HR Lead with Approve/Reject Actions)"]
        
        %% AUDIT ROUTE
        B3 -.->|HR Audit Query / WF-847DA5| B6["hr.query_pending_leaves Tool<br/>(Displays Pending Summary in Chat & Emails Recap)"]

        %% DECISION
        B5 & B6 --> B7{"HR Lead Decision"}
        B7 -->|Reject| B8["Leave Status: REJECTED<br/>(Quota Intact, Reason Logged)"]
        B7 -->|Approve| B9["Leave Status: APPROVED<br/>(Digital Stamp Applied)"]
        B9 --> B10[("DuckDB: employees<br/>(Deduct Days from leave_balance)")]
        B10 --> B11["Final Confirmation Delivered to Employee & HR Records"]
    end

    style B_Workflow fill:#f0fdf4,stroke:#059669,stroke-width:1.5px
    style B3 fill:#fef08a,stroke:#ca8a04
    style B10 fill:#bbf7d0,stroke:#059669
```

---

### 💼 Pipeline C: Telecom Operator Onboarding & Tower Lease Invoicing (`userc`)

This workflow governs commercial leasing for telecommunication operators (Telkomsel, Indosat Ooredoo Hutchison, XL Axiata, Smartfren) utilizing PT Bali Towerindo Sentra Tbk infrastructure.

```mermaid
flowchart TD
    subgraph C_Workflow ["Tower Infrastructure Leasing & Billing Lifecycle"]
        C1([Account Manager / User C]) -->|Register Client & Site Lease| C2["Copilot / Admin Form<br/>(Operator Name, Site ID, Antenna Height, Period)"]
        C2 --> C3["Draft Master Lease Agreement (MLA)<br/>(Status: PENDING_APPROVAL)"]
        C3 --> C4["Calculate Lease Rates & Initial Invoice Estimation<br/>(Base Lease Rate + 11% Indonesian VAT)"]
        C4 --> C5["Finance Email Dispatcher<br/>(Sends Contract Preview & One-Click Approval to Finance Lead)"]
        
        C5 --> C6{"Finance Lead Decision"}
        C6 -->|Reject| C7["Contract REJECTED<br/>(Site Reservation Cancelled)"]
        C6 -->|Approve| C8["Contract APPROVED & ACTIVATED<br/>(Registered in mla_contracts)"]
        C8 --> C9[("DuckDB: revenue_invoices<br/>(Official Invoice Generated)")]
        C9 --> C10["DocGen Typst Engine<br/>(Compiles Formal Tax Invoice PDF with Letterhead)"]
    end

    style C_Workflow fill:#fffbeb,stroke:#d97706,stroke-width:1.5px
    style C3 fill:#fef08a,stroke:#ca8a04
    style C8 fill:#bbf7d0,stroke:#16a34a
    style C10 fill:#fef3c7,stroke:#d97706
```

---

### 👑 Admin Pipeline: Natural Language Dynamic Workflow Orchestrator (`admin`)

Administrators can design, update, and deploy automated multi-step workflows using plain natural language without writing code.

```mermaid
flowchart LR
    Admin([Enterprise Admin]) -->|Writes Natural Language Instruction| LLM["LLM Graph Compiler<br/>(Gemini / Nemotron-35)"]
    LLM -->|Compiles to Structured JSON| Graph["Execution Graph JSON<br/>(Tool Steps, Tasks, Conditions)"]
    Graph -->|Stored in DuckDB| DB[("workflows Table")]
    DB -->|Triggered by User Intent| Engine["JSONExecutionEngine<br/>(agents/json_executor.py)"]
    Engine -->|Dynamic Sequential Execution| Tools["Tool Registry<br/>(Inventory, HR, Finance, DocGen, Dispatch)"]
    Tools -->|Real-time SSE Stream| Dashboard["Live Corporate Dashboard"]

    style LLM fill:#e0e7ff,stroke:#6366f1,stroke-width:1.5px
    style Graph fill:#fef3c7,stroke:#d97706,stroke-width:1.5px
    style Engine fill:#dcfce7,stroke:#16a34a,stroke-width:1.5px
```

---

## 🏛️ Multi-Tenant RBAC & Domain Governance Matrix

| Persona | Role | Division / Tenant | Database Scope | Key Operational Capabilities |
| :--- | :---: | :---: | :--- | :--- |
| **`usera`** | `USER` | `INVENTORY` (Tenant A) | `stock_balances`, `inventory_items`, `purchase_orders`, `purchase_requests`, `warehouses` | • Audit stock across 7 regional hubs<br/>• Generate PRs for low/critical items<br/>• One-click Goods Receipt (`[✓ Terima Barang]`)<br/>• Register new material SKUs |
| **`userb`** | `USER` | `HR` (Tenant B) | `employees`, `leave_requests` | • Submit rigger/technician leave requests<br/>• Execute pending leave audit (`WF-847DA5`)<br/>• Trigger HR authorization emails<br/>• Deduct approved days from annual quota |
| **`userc`** | `USER` | `FINANCE` (Tenant C) | `telecom_clients`, `mla_contracts`, `revenue_invoices`, `power_utility_expenses` | • Register telecom clients (Telkomsel, XL, IOH)<br/>• Draft tower lease contracts (MLA)<br/>• Dispatch finance authorization emails<br/>• Generate official billing invoices (11% VAT) |
| **`admin`** | `ADMIN` | `ALL` (Super Admin) | Unrestricted access across all master and tenant tables | • Natural Language Workflow Orchestrator<br/>• Cross-division AI Copilot governance<br/>• Database schema migrations & seeding<br/>• System audit logs & security monitoring |

---

## 💻 Technology Stack

| Architectural Layer | Technology Stack | Technical Specifications & Role |
| :--- | :--- | :--- |
| **Core API & Gateway** | **Python 3.10+**, **FastAPI**, **Pydantic v2** | High-performance asynchronous REST API, JWT authentication, and dependency-injected RBAC security. |
| **Multi-Agent Orchestrator** | **LangGraph**, **NVIDIA Nemotron-35**, **Gemini 2.5** | Multi-agent state machine coordinating mathematical planners, compliance auditors, and semantic routers. |
| **Analytical OLAP Engine** | **DuckDB Embedded** | High-speed in-process columnar SQL database with automatic transactional CSV persistence. |
| **Document Typesetting** | **Typst Compiler (Python Typst 0.11+)** | High-fidelity vector PDF typesetting engine (<50ms compilation) supporting multi-page layouts and corporate typography. |
| **Notification Engine** | **Python smtplib** / **aiosmtplib** | Corporate HTML email dispatcher with cryptographic action URLs for one-click manager authorization. |
| **User Interface** | **Semantic HTML5**, **Vanilla CSS**, **JavaScript**, **SSE** | Responsive dark/light corporate operations dashboard with zero external CSS framework bloat and live event streaming. |

---

## 🚀 Getting Started & Operational Guide

### 1. Prerequisites
- Python 3.10 or higher
- Git
- Local workstation (Windows, macOS) or Linux Server (Ubuntu 22.04+)

### 2. Installation
```bash
# 1. Clone the repository
git clone https://github.com/daffaarigoh/AutoRestock-Agent.git
cd AutoRestock-Agent

# 2. Set up virtual environment
python -m venv .venv
# On Linux / macOS:
source .venv/bin/activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt
```

### 3. Database Initialization & Seeding
Initialize the DuckDB master tables and seed realistic operational data for PT Bali Towerindo Sentra Tbk:
```bash
python database/seed_data.py
```

### 4. Running the Application Server
Start the FastAPI server on port `8050`:
```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8050 --reload
```

- **Operations Dashboard**: [http://localhost:8050](http://localhost:8050)
- **Interactive Swagger Docs**: [http://localhost:8050/docs](http://localhost:8050/docs)
- **Admin Workflow Studio**: [http://localhost:8050/admin](http://localhost:8050/admin)

### 5. Default Corporate Credentials
| Username | Password | Role | Division / Access Scope |
| :--- | :--- | :--- | :--- |
| `admin` | `admin123` | `ADMIN` | Super Admin (Cross-Tenant Access & Workflow Orchestrator) |
| `usera` | `user123` | `USER` | Logistics & Inventory Hubs (Schema A) |
| `userb` | `user123` | `USER` | Human Resources & Field Operations (Schema B) |
| `userc` | `user123` | `USER` | Finance & Commercial Leasing (Schema C) |

---

## 🧪 Automated Testing Suite

The repository includes a comprehensive test suite validating all multi-agent workflows, PDF document compilers, and API endpoints:

```bash
# Run all unit and integration tests
python -m unittest discover -s tests -p "test_*.py"

# Run Typst Purchase Order (PO) compiler tests
python tests/test_po_pdf_generation.py

# Run end-to-end API pipeline integration test
python tests/test_api_and_pipeline.py
```

---

## 📂 Repository Directory Structure

```text
AutoRestock-Agent/
├── agents/                  # Multi-agent LangGraph logic (Planner, Auditor, Router, JSON Executor)
├── api/                     # FastAPI endpoint routers (Balitower, Approvals, Agents, Auth, Documents)
├── core/                    # System configuration, environment loader, Pydantic schemas, JWT security
├── data/                    # Persistent Bali Tower CSV datasets (Inventory, HR, Finance)
├── database/                # DuckDB initialization, master schemas, migration & seeding scripts
├── docgen/                  # Typst compilation engine & official corporate document templates
│   └── templates/           # Typst source templates (purchase_requisition, purchase_order, leave, invoice)
├── storage/                 # Generated PDF documents, local database files, and file archives
├── tests/                   # Automated unit, integration, and E2E test suite
└── web/                     # Frontend dashboard web assets
    ├── static/              # Visual assets, dashboard JavaScript modules, and CSS design system
    │   ├── css/             # Dashboard and admin stylesheets
    │   └── js/              # Client-side state managers, chat controller, and table renderers
    └── templates/           # Jinja2 / HTML index page templates
```

---

<div align="center">
  <p><strong>PT Bali Towerindo Sentra Tbk</strong> &bull; Telecommunication Infrastructure & Fiber Optic Solutions</p>
  <p><em>Wisma Kodel Lantai 6, Jl. H.R. Rasuna Said Kav. B-4, Setiabudi, Jakarta Selatan 12920, Indonesia</em></p>
</div>
