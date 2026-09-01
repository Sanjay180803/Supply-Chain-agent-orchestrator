from pydantic import BaseModel
from typing import Optional


class AnalyticsRequest(BaseModel):
    metric: str  # e.g. "avg_cost_per_category", "supplier_count_by_country", "top_suppliers_by_trust"
    filter_category: Optional[str] = None
    filter_country: Optional[str] = None


class AnalyticsDecision(BaseModel):
    metric: str
    result: dict
    summary: str