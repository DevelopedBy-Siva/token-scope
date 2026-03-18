from fastapi import APIRouter, HTTPException

from api.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    FieldTokensResponse,
    CostLeakResponse,
    RequestCostResponse,
    MonthlyCostResponse,
    OptimizationResponse,
    AllModelsCostResponse,
    HealthResponse,
)
from core.parser import parse_payload
from core.leak_detector import detect_leaks
from core.payload_optimizer import optimize_payload
from core.calculator import Calculator, PRICING_LAST_UPDATED

router = APIRouter()
calculator = Calculator()


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", version="1.0.0")


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
        cost = calculator.request_cost(
            input_tokens=parsed.total_tokens,
            model_id=request.model_id,
        )
        monthly = calculator.monthly_cost(
            input_tokens=parsed.total_tokens,
            requests_per_day=request.requests_per_day,
            model_id=request.model_id,
        )
        all_models = calculator.all_models_cost(input_tokens=parsed.total_tokens)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    fields = [
        FieldTokensResponse(
            path=f.path,
            attributed_tokens=f.attributed_tokens,
            pct_of_total=f.pct_of_total,
            depth=f.depth,
            field_type=f.field_type.value,
            is_leaf=f.is_leaf,
        )
        for f in parsed.fields if f.is_leaf
    ]

    top_contributors = [
        FieldTokensResponse(
            path=f.path,
            attributed_tokens=f.attributed_tokens,
            pct_of_total=f.pct_of_total,
            depth=f.depth,
            field_type=f.field_type.value,
            is_leaf=f.is_leaf,
        )
        for f in parsed.sorted_by_cost if f.is_leaf
    ][:5]

    leak_responses = [
        CostLeakResponse(
            rule_id=l.rule_id.value,
            severity=l.severity.value,
            path=l.path,
            description=l.description,
            estimated_savings=l.estimated_savings,
            affected_paths=l.affected_paths,
        )
        for l in leaks
    ]

    return AnalyzeResponse(
        total_tokens=parsed.total_tokens,
        fields=fields,
        top_contributors=top_contributors,
        leaks=leak_responses,
        cost=RequestCostResponse(
            model_id=cost.model_id,
            display_name=cost.display_name,
            provider=cost.provider,
            input_tokens=cost.input_tokens,
            input_cost_usd=cost.input_cost_usd,
            output_tokens=cost.output_tokens,
            output_cost_usd=cost.output_cost_usd,
            total_cost_usd=cost.total_cost_usd,
        ),
        monthly=MonthlyCostResponse(
            monthly_cost_usd=monthly.monthly_cost_usd,
            daily_cost_usd=monthly.daily_cost_usd,
            requests_per_day=monthly.requests_per_day,
            days=monthly.days,
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
            AllModelsCostResponse(
                model_id=m.model_id,
                display_name=m.display_name,
                provider=m.provider,
                total_cost_usd=m.total_cost_usd,
                input_cost_usd=m.input_cost_usd,
            )
            for m in all_models
        ],
        encoding=request.encoding,
        pricing_last_updated=PRICING_LAST_UPDATED.isoformat(),
    )