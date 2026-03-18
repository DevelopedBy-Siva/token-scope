from typing import Any
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    payload: dict | list = Field(..., description="The LLM API payload to analyze")
    model_id: str = Field(default="gpt-4o", description="Model to use for cost calculation")
    requests_per_day: int = Field(default=100, ge=1, description="Daily request volume for monthly projection")
    encoding: str = Field(default="cl100k_base", description="tiktoken encoding to use")


class FieldTokensResponse(BaseModel):
    path: str
    attributed_tokens: int
    pct_of_total: float
    depth: int
    field_type: str
    is_leaf: bool


class CostLeakResponse(BaseModel):
    rule_id: str
    severity: str
    path: str
    description: str
    estimated_savings: int
    affected_paths: list[str]


class RequestCostResponse(BaseModel):
    model_id: str
    display_name: str
    provider: str
    input_tokens: int
    input_cost_usd: float
    output_tokens: int
    output_cost_usd: float
    total_cost_usd: float


class MonthlyCostResponse(BaseModel):
    monthly_cost_usd: float
    daily_cost_usd: float
    requests_per_day: int
    days: int


class OptimizationResponse(BaseModel):
    optimized_payload: dict | list
    original_tokens: int
    optimized_tokens: int
    tokens_saved: int
    pct_saved: float
    applied_rules: list[str]


class AllModelsCostResponse(BaseModel):
    model_id: str
    display_name: str
    provider: str
    total_cost_usd: float
    input_cost_usd: float


class AnalyzeResponse(BaseModel):
    total_tokens: int
    fields: list[FieldTokensResponse]
    top_contributors: list[FieldTokensResponse]
    leaks: list[CostLeakResponse]
    cost: RequestCostResponse
    monthly: MonthlyCostResponse
    optimization: OptimizationResponse
    all_models: list[AllModelsCostResponse]
    encoding: str
    pricing_last_updated: str


class HealthResponse(BaseModel):
    status: str
    version: str


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None