"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

# Budgeting app schemas

class Category(BaseModel):
    """
    Categories collection schema
    Collection name: "category"
    """
    name: str = Field(..., description="Category name, e.g., Groceries, Rent")
    color: Optional[str] = Field("#60a5fa", description="Hex color for UI tags")

class Transaction(BaseModel):
    """
    Transactions collection schema
    Collection name: "transaction"
    """
    amount: float = Field(..., gt=0, description="Amount of the transaction")
    type: Literal["income", "expense"] = Field(..., description="Transaction type")
    category_id: Optional[str] = Field(None, description="Related category id (string)")
    note: Optional[str] = Field(None, description="Short note or description")
    date: Optional[datetime] = Field(None, description="When the transaction occurred")

class Budget(BaseModel):
    """
    Budgets collection schema
    Defines a monthly budget limit for a category
    Collection name: "budget"
    """
    month: str = Field(..., description="Month in YYYY-MM format")
    category_id: Optional[str] = Field(None, description="Category this budget applies to (None means overall)")
    limit: float = Field(..., gt=0, description="Spending limit for the month")
