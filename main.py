import os
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import create_document, get_documents, db
from schemas import Category as CategorySchema, Transaction as TransactionSchema, Budget as BudgetSchema

app = FastAPI(title="Budgeting API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Utilities ----------

def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    d = dict(doc)
    if d.get("_id") is not None:
        d["id"] = str(d.pop("_id"))
    # Convert datetimes to isoformat
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


# ---------- Root & Health ----------

@app.get("/")
def read_root():
    return {"message": "Budgeting API is running"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# ---------- Schemas endpoint ----------

@app.get("/schema")
def get_schema():
    return {
        "Category": CategorySchema.model_json_schema(),
        "Transaction": TransactionSchema.model_json_schema(),
        "Budget": BudgetSchema.model_json_schema(),
    }


# ---------- Categories ----------

class CreateCategory(BaseModel):
    name: str
    color: Optional[str] = "#60a5fa"


@app.get("/api/categories")
def list_categories(limit: Optional[int] = Query(default=None, ge=1, le=200)):
    docs = get_documents("category", {}, limit)
    return [serialize_doc(d) for d in docs]


@app.post("/api/categories")
def create_category(payload: CreateCategory):
    cat = CategorySchema(name=payload.name, color=payload.color)
    new_id = create_document("category", cat)
    return {"id": new_id}


# ---------- Transactions ----------

class CreateTransaction(BaseModel):
    amount: float
    type: str  # "income" | "expense"
    category_id: Optional[str] = None
    note: Optional[str] = None
    date: Optional[str] = None  # ISO string


@app.get("/api/transactions")
def list_transactions(month: Optional[str] = Query(default=None, description="YYYY-MM"), limit: Optional[int] = Query(default=100, ge=1, le=1000)):
    filter_dict: Dict[str, Any] = {}
    if month:
        # Range match for the month
        try:
            start = datetime.fromisoformat(month + "-01")
            if start.month == 12:
                end = datetime(start.year + 1, 1, 1)
            else:
                end = datetime(start.year, start.month + 1, 1)
            filter_dict["date"] = {"$gte": start, "$lt": end}
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")
    docs = get_documents("transaction", filter_dict, limit)
    return [serialize_doc(d) for d in docs]


@app.post("/api/transactions")
def create_transaction(payload: CreateTransaction):
    # Normalize date
    tx_date: Optional[datetime] = None
    if payload.date:
        try:
            tx_date = datetime.fromisoformat(payload.date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601")
    else:
        tx_date = datetime.utcnow()

    tx = TransactionSchema(
        amount=payload.amount,
        type=payload.type,
        category_id=payload.category_id,
        note=payload.note,
        date=tx_date,
    )
    new_id = create_document("transaction", tx)
    return {"id": new_id}


# ---------- Budgets ----------

class CreateBudget(BaseModel):
    month: str  # YYYY-MM
    category_id: Optional[str] = None
    limit: float


@app.get("/api/budgets")
def list_budgets(month: Optional[str] = Query(default=None), limit: Optional[int] = Query(default=200, ge=1, le=1000)):
    filter_dict: Dict[str, Any] = {}
    if month:
        filter_dict["month"] = month
    docs = get_documents("budget", filter_dict, limit)
    return [serialize_doc(d) for d in docs]


@app.post("/api/budgets")
def create_budget(payload: CreateBudget):
    # Basic validation of month
    try:
        datetime.fromisoformat(payload.month + "-01")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")

    b = BudgetSchema(month=payload.month, category_id=payload.category_id, limit=payload.limit)
    new_id = create_document("budget", b)
    return {"id": new_id}


# ---------- Summary ----------

@app.get("/api/summary")
def get_summary(month: Optional[str] = Query(default=None)):
    # Build month filter
    filter_dict: Dict[str, Any] = {}
    if month:
        try:
            start = datetime.fromisoformat(month + "-01")
            if start.month == 12:
                end = datetime(start.year + 1, 1, 1)
            else:
                end = datetime(start.year, start.month + 1, 1)
            filter_dict["date"] = {"$gte": start, "$lt": end}
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")

    txs = get_documents("transaction", filter_dict, None)

    income = sum(t.get("amount", 0) for t in txs if t.get("type") == "income")
    expenses = sum(t.get("amount", 0) for t in txs if t.get("type") == "expense")
    balance = income - expenses

    # Per-category spending
    spending_by_category: Dict[str, float] = {}
    for t in txs:
        if t.get("type") == "expense":
            cid = str(t.get("category_id")) if t.get("category_id") else "uncategorized"
            spending_by_category[cid] = spending_by_category.get(cid, 0.0) + float(t.get("amount", 0))

    # Attach budgets for the month
    budget_filter = {"month": month} if month else {}
    budgets = [serialize_doc(b) for b in get_documents("budget", budget_filter, None)]

    return {
        "income": income,
        "expenses": expenses,
        "balance": balance,
        "spending_by_category": spending_by_category,
        "budgets": budgets,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
