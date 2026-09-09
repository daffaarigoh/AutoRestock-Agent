from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    TokenData,
    create_access_token,
    get_current_admin,
    get_current_user,
    verify_password,
)
from database.db import get_db_connection

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    tenant_id: str


@router.post("/login", response_model=Token)
async def login(req: LoginRequest):
    conn = get_db_connection(read_only=True)
    df = conn.execute("SELECT username, password_hash, role, tenant_id FROM users WHERE username = ?", [req.username]).df()
    conn.close()

    if df.empty:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    user = df.iloc[0]
    if not verify_password(req.password, user['password_hash']):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user['username'], "role": user['role'], "tenant_id": user['tenant_id']},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "role": user['role'], "tenant_id": user['tenant_id']}


@router.get("/me")
async def get_me(current_user: TokenData = Depends(get_current_user)):
    return {"username": current_user.username, "role": current_user.role, "tenant_id": current_user.tenant_id}



def _ensure_workflow_tenant_column(conn):
    """Ensure the workflows table has the tenant_id column for user-scoped workflows."""
    try:
        cols = [r[0] for r in conn.execute("DESCRIBE workflows;").fetchall()]
        if "tenant_id" not in cols:
            conn.execute("ALTER TABLE workflows ADD COLUMN tenant_id VARCHAR DEFAULT 'ALL';")
    except Exception as e:
        pass


def _normalize_tenant_id(val: str) -> str:
    v = (val or "").strip().upper()
    mapping = {
        "ALL": "ALL",
        "SCHEMA_ALL": "ALL",
        "SCHEMA ALL": "ALL",
        "USERA": "INVENTORY",
        "TENANT_A": "INVENTORY",
        "SCHEMA_A": "INVENTORY",
        "SCHEMA A": "INVENTORY",
        "INVENTORY": "INVENTORY",
        "USERB": "HR",
        "TENANT_B": "HR",
        "SCHEMA_B": "HR",
        "SCHEMA B": "HR",
        "HR": "HR",
        "USERC": "FINANCE",
        "TENANT_C": "FINANCE",
        "SCHEMA_C": "FINANCE",
        "SCHEMA C": "FINANCE",
        "FINANCE": "FINANCE"
    }
    return mapping.get(v, "ALL")


class CreateWorkflowRequest(BaseModel):
    name: str
    description: str
    business_instruction: str
    tenant_id: str = "ALL"  # ALL, INVENTORY, HR, FINANCE

@router.post("/admin/workflows")
async def create_workflow(req: CreateWorkflowRequest, admin: TokenData = Depends(get_current_admin)):
    from agents.workflow_compiler import WorkflowCompiler
    import json
    import uuid
    
    compiled_json = await WorkflowCompiler.compile_business_instruction(req.name, req.business_instruction)
    
    wf_id = f"WF-{uuid.uuid4().hex[:6].upper()}"
    tenant_val = _normalize_tenant_id(req.tenant_id)
    
    conn = get_db_connection(read_only=False)
    _ensure_workflow_tenant_column(conn)
    conn.execute(
        "INSERT INTO workflows (id, name, description, business_instruction, compiled_json, tenant_id) VALUES (?, ?, ?, ?, ?, ?)", 
        [wf_id, req.name, req.description, req.business_instruction, json.dumps(compiled_json), tenant_val]
    )
    conn.close()
    
    return {"status": "success", "workflow_id": wf_id, "compiled_json": compiled_json, "tenant_id": tenant_val}

@router.get("/admin/workflows")
async def get_workflows(response: Response, admin: TokenData = Depends(get_current_admin)):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    conn = get_db_connection(read_only=True)
    rows = conn.execute("SELECT id, name, description, business_instruction, compiled_json, tenant_id FROM workflows ORDER BY id ASC").fetchall()
    columns = [desc[0] for desc in conn.description]
    conn.close()
    
    workflows = []
    import json
    for r in rows:
        wf = dict(zip(columns, r))
        if not wf.get("tenant_id"):
            wf["tenant_id"] = "ALL"
        try:
            wf["compiled_json"] = json.loads(wf["compiled_json"])
        except:
            pass
        workflows.append(wf)
        
    return workflows

@router.delete("/admin/workflows/{wf_id}")
async def delete_workflow(wf_id: str, admin: TokenData = Depends(get_current_admin)):
    conn = get_db_connection(read_only=False)
    conn.execute("DELETE FROM workflows WHERE id = ?", [wf_id])
    conn.close()
    return {"status": "success"}

@router.put("/admin/workflows/{wf_id}")
async def edit_workflow(wf_id: str, req: CreateWorkflowRequest, admin: TokenData = Depends(get_current_admin)):
    from agents.workflow_compiler import WorkflowCompiler
    import json
    
    compiled_json = await WorkflowCompiler.compile_business_instruction(req.name, req.business_instruction)
    tenant_val = _normalize_tenant_id(req.tenant_id)
    
    conn = get_db_connection(read_only=False)
    _ensure_workflow_tenant_column(conn)
    conn.execute(
        "UPDATE workflows SET name = ?, description = ?, business_instruction = ?, compiled_json = ?, tenant_id = ? WHERE id = ?", 
        [req.name, req.description, req.business_instruction, json.dumps(compiled_json), tenant_val, wf_id]
    )
    conn.close()
    
    return {"status": "success", "workflow_id": wf_id, "compiled_json": compiled_json, "tenant_id": tenant_val}


@router.get("/admin/users")
async def get_all_users(response: Response, admin: TokenData = Depends(get_current_admin)):
    """Fetch all registered users and their multi-tenant inventory database stats."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    conn = get_db_connection(read_only=True)
    users_rows = conn.execute("SELECT user_id, username, role, tenant_id FROM users ORDER BY user_id ASC").fetchall()

    # Scope 1: Inventory Items (for usera)
    inv_rows = conn.execute("""
        SELECT 
            i.item_id,
            i.item_code,
            i.item_name,
            i.category,
            COALESCE(SUM(sb.quantity_on_hand), 0) AS current_stock,
            i.min_stock AS min_threshold,
            i.min_stock * 3 AS max_threshold,
            i.unit,
            i.unit_price,
            s.supplier_name
        FROM inventory_items i
        LEFT JOIN stock_balances sb ON i.item_id = sb.item_id
        LEFT JOIN suppliers s ON i.supplier_id = s.supplier_id
        GROUP BY i.item_id, i.item_code, i.item_name, i.category, i.min_stock, i.unit, i.unit_price, s.supplier_name
        ORDER BY i.item_id ASC;
    """).fetchall()

    # Scope 2: HR Employees (for userb)
    emp_rows = conn.execute("""
        SELECT employee_id, full_name, department, job_title, employment_status, k3_certification, leave_balance
        FROM employees
        ORDER BY employee_id ASC;
    """).fetchall()

    # Scope 3: Finance Invoices (for userc)
    invc_rows = conn.execute("""
        SELECT r.invoice_number, COALESCE(c.client_name, r.client_id) AS client_name, r.period_covered, r.due_date, r.total_billed, r.payment_status
        FROM revenue_invoices r
        LEFT JOIN telecom_clients c ON r.client_id = c.client_id
        ORDER BY r.invoice_number ASC;
    """).fetchall()
    conn.close()

    # Build items_list for multi-tenant table view
    items_list = []
    
    # 1. usera - Material Inventory (14 items)
    usera_total_stock = 0
    usera_low_stock = 0
    for r in inv_rows:
        item_id, item_code, name, cat, stock, min_thresh, max_thresh, unit, price, supp_name = r
        stock_val = int(stock)
        min_val = int(min_thresh)
        usera_total_stock += stock_val
        if stock_val <= min_val:
            usera_low_stock += 1
        items_list.append({
            "domain": "INVENTORY",
            "tenant_id": "usera",
            "sku": item_code or item_id,
            "item_id": item_id,
            "name": name,
            "category": cat,
            "supplier_name": supp_name or "-",
            "current_stock": stock_val,
            "unit": unit or "pcs",
            "min_threshold": min_val,
            "max_threshold": int(max_thresh),
            "unit_price": float(price or 0.0),
            "status": "Menipis" if stock_val <= min_val else "Normal"
        })

    # 2. userb - HR Workforce (12 employees)
    userb_riggers = 0
    for r in emp_rows:
        emp_id, full_name, dept, job, emp_status, k3_cert, leave_bal = r
        if "rigger" in (job or "").lower() or "teknisi" in (job or "").lower():
            userb_riggers += 1
        items_list.append({
            "domain": "HR",
            "tenant_id": "userb",
            "item_id": emp_id,
            "employee_id": emp_id,
            "name": full_name,
            "full_name": full_name,
            "department": dept,
            "category": dept,
            "job_title": job,
            "employment_status": emp_status or "PERMANENT",
            "k3_certification": k3_cert or "NON_CERTIFIED",
            "leave_balance": int(leave_bal or 0),
            "status": "Aktif",
            "unit": "orang",
            "current_stock": 1,
            "unit_price": 0.0
        })

    # 3. userc - Finance Invoices (8 invoices)
    userc_unpaid = 0
    userc_revenue = 0.0
    for r in invc_rows:
        inv_no, client, period, due_date, amount, pay_status = r
        amt = float(amount or 0.0)
        userc_revenue += amt
        if (pay_status or "").upper() in ["UNPAID", "OVERDUE"]:
            userc_unpaid += 1
        items_list.append({
            "domain": "FINANCE",
            "tenant_id": "userc",
            "item_id": inv_no,
            "invoice_number": inv_no,
            "name": f"{client} ({period})",
            "client_name": client,
            "category": "Tagihan Operator",
            "period_covered": period,
            "due_date": due_date or "-",
            "total_billed": amt,
            "unit_price": amt,
            "payment_status": pay_status or "PAID",
            "status": pay_status or "PAID",
            "unit": "invoice",
            "current_stock": 1
        })

    # Map stats for each registered user
    tenant_stats = {
        "INVENTORY": {"total_items": len(inv_rows), "total_stock": usera_total_stock, "low_stock_count": usera_low_stock},
        "TENANT_A": {"total_items": len(inv_rows), "total_stock": usera_total_stock, "low_stock_count": usera_low_stock},
        "usera": {"total_items": len(inv_rows), "total_stock": usera_total_stock, "low_stock_count": usera_low_stock},
        "HR": {"total_items": len(emp_rows), "total_stock": userb_riggers, "low_stock_count": 0},
        "TENANT_B": {"total_items": len(emp_rows), "total_stock": userb_riggers, "low_stock_count": 0},
        "userb": {"total_items": len(emp_rows), "total_stock": userb_riggers, "low_stock_count": 0},
        "FINANCE": {"total_items": len(invc_rows), "total_stock": int(userc_revenue // 1_000_000_000), "low_stock_count": userc_unpaid},
        "TENANT_C": {"total_items": len(invc_rows), "total_stock": int(userc_revenue // 1_000_000_000), "low_stock_count": userc_unpaid},
        "userc": {"total_items": len(invc_rows), "total_stock": int(userc_revenue // 1_000_000_000), "low_stock_count": userc_unpaid},
        "ALL": {"total_items": len(items_list), "total_stock": usera_total_stock, "low_stock_count": usera_low_stock}
    }

    users_list = []
    for u in users_rows:
        u_id, username, role, t_id = u
        st = tenant_stats.get(t_id, tenant_stats.get(username, {"total_items": 0, "total_stock": 0, "low_stock_count": 0}))
        users_list.append({
            "user_id": u_id,
            "username": username,
            "role": role,
            "tenant_id": t_id,
            "stats": st
        })
        
    return {
        "total_users": len(users_list),
        "users": users_list,
        "items": items_list
    }
