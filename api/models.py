from typing import Any
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    payload: dict | list = Field(..., description="The LLM API payload to analyze")
    model_id: str = Field(default="gpt-4o")
    requests_per_day: int = Field(default=100, ge=1)
    encoding: str = Field(default="cl100k_base")


class FieldResponse(BaseModel):
    path: str
    attributed_tokens: int
    pct_of_total: float
    field_type: str


class LeakResponse(BaseModel):
    rule_id: str
    severity: str
    path: str
    description: str
    estimated_savings: int
    affected_paths: list[str]


class CostResponse(BaseModel):
    model_id: str
    display_name: str
    provider: str
    input_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    is_estimated_pricing: bool


class MonthlyResponse(BaseModel):
    monthly_cost_usd: float
    daily_cost_usd: float
    requests_per_day: int


class OptimizationResponse(BaseModel):
    optimized_payload: dict | list
    original_tokens: int
    optimized_tokens: int
    tokens_saved: int
    pct_saved: float
    applied_rules: list[str]


class ModelCostResponse(BaseModel):
    model_id: str
    display_name: str
    provider: str
    total_cost_usd: float


class AnalyzeResponse(BaseModel):
    total_tokens: int
    top_fields: list[FieldResponse]
    leaks: list[LeakResponse]
    cost: CostResponse
    monthly: MonthlyResponse
    optimization: OptimizationResponse
    all_models: list[ModelCostResponse]
    encoding: str
    pricing_updated: str


class HealthResponse(BaseModel):
    status: str
    version: str