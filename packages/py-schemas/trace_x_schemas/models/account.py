from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

class Account(BaseModel):
    account_id: str
    entity_id: str
    account_type: str
    kyc_tier: int
    status: str
    opened_on: date
    risk_category: str
    declared_annual_income: Optional[float] = None
    txn_count_7d: int = 0
    txn_count_30d: int = 0
    volume_7d: float = 0.0
    volume_30d: float = 0.0
    avg_monthly_volume: float = 0.0
    avg_monthly_count: float = 0.0
    unique_counterparties_30d: int = 0
    last_active_ts: Optional[datetime] = None
