from pydantic import BaseModel, Field
from typing import Optional, List


class ProcurementRequest(BaseModel):
    product_name: str
    quantity: int
    max_unit_price: Optional[float] = None
    max_lead_time_days: Optional[int] = None


class SupplierCandidate(BaseModel):
    supplier_id: int
    supplier_name: str
    price: float
    lead_time_days: int
    trust_score: float
    terms: str
    score: float = 0.0


class NegotiationRound(BaseModel):
    round_number: int
    proposed_price: float
    counter_price: Optional[float] = None
    accepted: bool = False


class ProcurementDecision(BaseModel):
    product_name: str
    quantity: int
    chosen_supplier: str
    final_price: float
    lead_time_days: int
    terms: str
    rationale: str
    negotiation_rounds: List[NegotiationRound] = Field(default_factory=list)