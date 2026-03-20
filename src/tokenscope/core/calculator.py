import json
import warnings
from datetime import date, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple


_PRICES_FILE = Path(__file__).parent.parent / "prices.json"
_STALE_DAYS  = 60


def _load_prices() -> tuple[dict, date]:
    with open(_PRICES_FILE) as f:
        data = json.load(f)
    updated = datetime.strptime(data["_updated"], "%Y-%m-%d").date()
    if (date.today() - updated).days > _STALE_DAYS:
        warnings.warn(
            f"TokenScope pricing data is over {_STALE_DAYS} days old "
            f"(last updated {updated}). Costs may be inaccurate. "
            f"Update src/tokenscope/prices.json or check "
            f"https://github.com/DevelopedBy-Siva/token-scope.",
            UserWarning,
            stacklevel=3,
        )
    return data["models"], updated


class ModelPricing(NamedTuple):
    model_id: str
    display_name: str
    provider: str
    input_per_million: float
    output_per_million: float


def _build_models() -> dict[str, ModelPricing]:
    raw, _ = _load_prices()
    return {
        k: ModelPricing(
            model_id=k,
            display_name=v["display_name"],
            provider=v["provider"],
            input_per_million=v["input_per_million"],
            output_per_million=v["output_per_million"],
        )
        for k, v in raw.items()
    }


MODELS: dict[str, ModelPricing] = _build_models()
DEFAULT_MODEL = "gpt-4o"

LOCAL_MODEL_REFERENCE = "gpt-4o"

_MODEL_PREFIXES: list[tuple[str, str]] = [
    ("claude-3-7-sonnet",  "claude-3-7-sonnet"),
    ("claude-3-5-sonnet",  "claude-3-5-sonnet"),
    ("claude-3-5-haiku",   "claude-3-5-haiku"),
    ("claude-3-haiku",     "claude-3-haiku"),
    ("gpt-4o-mini",        "gpt-4o-mini"),
    ("gpt-4o",             "gpt-4o"),
    ("gpt-4-turbo",        "gpt-4-turbo"),
    ("gpt-4",              "gpt-4-turbo"),
    ("o3-mini",            "o3-mini"),
    ("o3",                 "o3"),
    ("gemini-2.0-flash",   "gemini-2-0-flash"),
    ("gemini-1.5-pro",     "gemini-1-5-pro"),
    ("gemini-1.5-flash",   "gemini-1-5-flash"),
]


def resolve_model_id(model: str) -> str:
    """Map a raw API model string to a pricing key."""
    for prefix, key in _MODEL_PREFIXES:
        if model.startswith(prefix):
            return key
    return model  


@dataclass
class RequestCost:
    model_id: str
    display_name: str
    provider: str
    input_tokens: int
    input_cost_usd: float
    output_tokens: int
    output_cost_usd: float
    total_cost_usd: float
    is_estimated_pricing: bool  


@dataclass
class MonthlyCost:
    request_cost: RequestCost
    requests_per_day: int
    days: int = 30

    @property
    def monthly_cost_usd(self) -> float:
        return self.request_cost.total_cost_usd * self.requests_per_day * self.days

    @property
    def daily_cost_usd(self) -> float:
        return self.request_cost.total_cost_usd * self.requests_per_day


@dataclass
class CostComparison:
    model_id: str
    original_tokens: int
    optimized_tokens: int
    original_cost_usd: float
    optimized_cost_usd: float
    requests_per_day: int
    days: int = 30

    @property
    def tokens_saved(self) -> int:
        return self.original_tokens - self.optimized_tokens

    @property
    def pct_tokens_saved(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return round((self.tokens_saved / self.original_tokens) * 100, 2)

    @property
    def cost_saved_per_request(self) -> float:
        return self.original_cost_usd - self.optimized_cost_usd

    @property
    def monthly_savings_usd(self) -> float:
        return self.cost_saved_per_request * self.requests_per_day * self.days


class Calculator:
    def request_cost(
        self,
        input_tokens: int,
        model_id: str = DEFAULT_MODEL,
        output_tokens: int = 0,
    ) -> RequestCost:
        pricing = self._get_pricing(model_id)
        known   = model_id in MODELS

        input_cost  = self._to_usd(input_tokens,  pricing.input_per_million)
        output_cost = self._to_usd(output_tokens, pricing.output_per_million)

        return RequestCost(
            model_id=model_id,
            display_name=pricing.display_name,
            provider=pricing.provider,
            input_tokens=input_tokens,
            input_cost_usd=input_cost,
            output_tokens=output_tokens,
            output_cost_usd=output_cost,
            total_cost_usd=input_cost + output_cost,
            is_estimated_pricing=not known,
        )

    def monthly_cost(
        self,
        input_tokens: int,
        requests_per_day: int,
        model_id: str = DEFAULT_MODEL,
        output_tokens: int = 0,
        days: int = 30,
    ) -> MonthlyCost:
        return MonthlyCost(
            request_cost=self.request_cost(input_tokens, model_id, output_tokens),
            requests_per_day=requests_per_day,
            days=days,
        )

    def compare(
        self,
        original_tokens: int,
        optimized_tokens: int,
        requests_per_day: int,
        model_id: str = DEFAULT_MODEL,
        days: int = 30,
    ) -> CostComparison:
        pricing = self._get_pricing(model_id)
        return CostComparison(
            model_id=model_id,
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            original_cost_usd=self._to_usd(original_tokens, pricing.input_per_million),
            optimized_cost_usd=self._to_usd(optimized_tokens, pricing.input_per_million),
            requests_per_day=requests_per_day,
            days=days,
        )

    def all_models_cost(self, input_tokens: int, output_tokens: int = 0) -> list[RequestCost]:
        return sorted(
            [self.request_cost(input_tokens, mid, output_tokens) for mid in MODELS],
            key=lambda c: c.total_cost_usd,
        )

    @staticmethod
    def _get_pricing(model_id: str) -> ModelPricing:
        if model_id in MODELS:
            return MODELS[model_id]
        ref = MODELS[LOCAL_MODEL_REFERENCE]
        return ModelPricing(
            model_id=model_id,
            display_name=f"{model_id} (≈gpt-4o pricing)",
            provider=ref.provider,
            input_per_million=ref.input_per_million,
            output_per_million=ref.output_per_million,
        )

    @staticmethod
    def _to_usd(tokens: int, price_per_million: float) -> float:
        if tokens == 0:
            return 0.0
        return round((tokens / 1_000_000) * price_per_million, 10)