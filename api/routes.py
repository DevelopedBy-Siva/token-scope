from fastapi import APIRouter, HTTPException

from api.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    FieldResponse,
    LeakResponse,
    CostResponse,
    MonthlyResponse,
    OptimizationResponse,
    ModelCostResponse,
    HealthResponse,
)
from tokenscope.core.parser import parse_payload
from tokenscope.core.leak_detector import detect_leaks
from tokenscope.core.payload_optimizer import optimize_payload
from tokenscope.core.calculator import Calculator, MODELS

router = APIRouter()
_calculator = Calculator()

VERSION = "0.2.0"


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", version=VERSION)


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):
    try:
        parsed = parse_payload(request.payload, encoding=request.encoding)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse payload: {e}")

    try:
        leaks = detect_leaks(parsed)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Leak detection failed: {e}")

    try:
        optimization = optimize_payload(request.payload, leaks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Optimization failed: {e}")

    try:
        cost    = _calculator.request_cost(parsed.total_tokens, model_id=request.model_id)
        monthly = _calculator.monthly_cost(parsed.total_tokens, request.requests_per_day, model_id=request.model_id)
        all_models = _calculator.all_models_cost(input_tokens=parsed.total_tokens)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    from tokenscope.core.calculator import _load_prices
    _, pricing_date = _load_prices()

    return AnalyzeResponse(
        total_tokens=parsed.total_tokens,
        top_fields=[
            FieldResponse(
                path=f.path,
                attributed_tokens=f.attributed_tokens,
                pct_of_total=f.pct_of_total,
                field_type=f.field_type.value,
            )
            for f in parsed.sorted_by_cost
            if f.is_leaf
        ][:5],
        leaks=[
            LeakResponse(
                rule_id=l.rule_id.value,
                severity=l.severity.value,
                path=l.path,
                description=l.description,
                estimated_savings=l.estimated_savings,
                affected_paths=l.affected_paths,
            )
            for l in leaks
        ],
        cost=CostResponse(
            model_id=cost.model_id,
            display_name=cost.display_name,
            provider=cost.provider,
            input_tokens=cost.input_tokens,
            input_cost_usd=cost.input_cost_usd,
            output_cost_usd=cost.output_cost_usd,
            total_cost_usd=cost.total_cost_usd,
            is_estimated_pricing=cost.is_estimated_pricing,
        ),
        monthly=MonthlyResponse(
            monthly_cost_usd=monthly.monthly_cost_usd,
            daily_cost_usd=monthly.daily_cost_usd,
            requests_per_day=monthly.requests_per_day,
        ),
        optimization=OptimizationResponse(
            optimized_payload=optimization.optimized_payload,
            original_tokens=optimization.original_tokens,
            optimized_tokens=optimization.optimized_tokens,
            tokens_saved=optimization.tokens_saved,
            pct_saved=optimization.pct_saved,
            applied_rules=[r.value for r in optimization.applied_rules],
        ),
        all_models=[
            ModelCostResponse(
                model_id=m.model_id,
                display_name=m.display_name,
                provider=m.provider,
                total_cost_usd=m.total_cost_usd,
            )
            for m in all_models
        ],
        encoding=request.encoding,
        pricing_updated=pricing_date.isoformat(),
    )