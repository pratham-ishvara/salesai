# backend/models/schemas.py
from pydantic import BaseModel, Field
from typing import Optional

# --- Request Schema ---
class GenerateSqlRequest(BaseModel):
    # db_name is still required to know which DB context to use
    db_name: str = Field(..., description="Name of the target MSSQL database for schema context")
    prompt: str = Field(..., description="Natural language prompt for SQL generation")

# --- Response Schemas ---
class GeneratedSqlResponse(BaseModel):
    generated_sql: str

class ErrorResponse(BaseModel):
    detail: str