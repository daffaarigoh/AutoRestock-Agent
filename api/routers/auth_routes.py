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



class CreateWorkflowRequest(BaseModel):
    name: str
    description: str
    business_instruction: str

@router.post("/admin/workflows")
async def create_workflow(req: CreateWorkflowRequest, admin: TokenData = Depends(get_current_admin)):
    from agents.workflow_compiler import WorkflowCompiler
    import json
    import uuid
    
    compiled_json = await WorkflowCompiler.compile_business_instruction(req.name, req.business_instruction)
    
    wf_id = f"WF-{uuid.uuid4().hex[:6].upper()}"
    
    conn = get_db_connection(read_only=False)
    conn.execute("INSERT INTO workflows (id, name, description, business_instruction, compiled_json) VALUES (?, ?, ?, ?, ?)", 
                 [wf_id, req.name, req.description, req.business_instruction, json.dumps(compiled_json)])
    conn.close()
    
    return {"status": "success", "workflow_id": wf_id, "compiled_json": compiled_json}

@router.get("/admin/workflows")
async def get_workflows(response: Response, admin: TokenData = Depends(get_current_admin)):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    conn = get_db_connection(read_only=True)
    rows = conn.execute("SELECT id, name, description, business_instruction, compiled_json FROM workflows ORDER BY id ASC").fetchall()
    columns = [desc[0] for desc in conn.description]
    conn.close()
    
    workflows = []
    import json
    for r in rows:
        wf = dict(zip(columns, r))
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
    
    conn = get_db_connection(read_only=False)
    conn.execute("UPDATE workflows SET name = ?, description = ?, business_instruction = ?, compiled_json = ? WHERE id = ?", 
                 [req.name, req.description, req.business_instruction, json.dumps(compiled_json), wf_id])
    conn.close()
    
    return {"status": "success", "workflow_id": wf_id, "compiled_json": compiled_json}


@router.get("/admin/users")
async def get_all_users(response: Response, admin: TokenData = Depends(get_current_admin)):
    """Fetch all registered users and their multi-tenant inventory database stats."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    conn = get_db_connection(read_only=True)
    users = conn.execute("SELECT user_id, username, role, tenant_id FROM users ORDER BY user_id ASC").fetchall()
    
    # Per-tenant item statistics
    stats = conn.execute("""
        SELECT tenant_id, 
               COUNT(*) as total_items, 
               COALESCE(SUM(current_stock), 0) as total_stock, 
               COALESCE(SUM(CASE WHEN current_stock < min_threshold THEN 1 ELSE 0 END), 0) as low_stock_count
        FROM items
        GROUP BY tenant_id
    """).fetchall()
    
    items_rows = conn.execute("""
        SELECT i.item_id, i.name, i.category, i.current_stock, i.min_threshold, 
               i.avg_daily_usage, i.lead_time_days, i.unit, i.tenant_id,
               COALESCE(v.unit_price, 0) as unit_price
        FROM items i
        LEFT JOIN (
            SELECT item_id, MIN(unit_price) as unit_price 
            FROM vendors 
            GROUP BY item_id
        ) v ON i.item_id = v.item_id
        ORDER BY i.tenant_id ASC, i.item_id ASC
    """).fetchall()
    
    conn.close()
    
    tenant_stats = {r[0]: {"total_items": int(r[1]), "total_stock": int(r[2]), "low_stock_count": int(r[3])} for r in stats}
    
    users_list = []
    for u in users:
        u_id, username, role, t_id = u
        st = tenant_stats.get(t_id, {"total_items": 0, "total_stock": 0, "low_stock_count": 0})
        if t_id == "ALL":
            all_items = sum(s["total_items"] for s in tenant_stats.values())
            all_stock = sum(s["total_stock"] for s in tenant_stats.values())
            all_low = sum(s["low_stock_count"] for s in tenant_stats.values())
            st = {"total_items": all_items, "total_stock": all_stock, "low_stock_count": all_low}
            
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
        "items": [
            {
                "item_id": r[0],
                "name": r[1],
                "category": r[2],
                "current_stock": r[3],
                "min_threshold": r[4],
                "avg_daily_usage": r[5],
                "lead_time_days": r[6],
                "unit": r[7],
                "tenant_id": r[8],
                "unit_price": r[9]
            } for r in items_rows
        ]
    }
