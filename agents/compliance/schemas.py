from pydantic import BaseModel
from typing import Optional, List


class ComplianceRequest(BaseModel):
    supplier_name: str
    trust_score: float
    terms: str
    unit_price: float
    max_approved_price: Optional[float] = None


class ComplianceViolation(BaseModel):
    rule: str
    detail: str


class ComplianceDecision(BaseModel):
    supplier_name: str
    approved: bool
    violations: List[ComplianceViolation] = []
    rationale: str