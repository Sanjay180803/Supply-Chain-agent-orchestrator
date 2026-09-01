from pydantic import BaseModel
from typing import Optional, List


class LogisticsRequest(BaseModel):
    origin_region: Optional[str] = None
    destination_region: str
    weight_kg: float
    max_transit_days: Optional[float] = None


class CarrierOption(BaseModel):
    carrier_id: int
    carrier_name: str
    region: str
    cost_per_kg: float
    avg_transit_days: float
    total_cost: float = 0.0
    score: float = 0.0


class LogisticsDecision(BaseModel):
    origin_region: Optional[str] = None
    destination_region: str
    weight_kg: float
    chosen_carrier: str
    total_cost: float
    estimated_transit_days: float
    rationale: str