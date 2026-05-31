from datetime import datetime

from pydantic import BaseModel

class Alert(BaseModel):
    alert_id: str
    alert_ts: datetime
    model: str
    pattern: str
    fraud_prob: float
    tier: str
    total_amount: float
    hop_depth: int
    time_window_hrs: int
    status: str
