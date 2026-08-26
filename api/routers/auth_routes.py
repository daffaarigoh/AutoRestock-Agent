from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
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
async def get_workflows(admin: TokenData = Depends(get_current_admin)):
    conn = get_db_connection(read_only=True)
    rows = conn.execute("SELECT id, name, description, business_instruction, compiled_json FROM workflows").fetchall()
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
