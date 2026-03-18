
from dataclasses import dataclass, field as dataclass_field
from datetime import date
from enum import Enum
from typing import NamedTuple



PRICING_LAST_UPDATED = date(2024, 3, 17)


class ModelPricing(NamedTuple):
    """Pricing for a single model in USD per 1M tokens."""
    model_id: str
    display_name: str
    provider: str
    input_per_million: float   
    output_per_million: float  


MODELS: dict[str, ModelPricing] = {
    "gpt-4o": ModelPricing(
        model_id="gpt-4o",
        display_name="GPT-4o",
        provider="OpenAI",
        input_per_million=2.50,
        output_per_million=10.00,
    ),
    "gpt-4o-mini": ModelPricing(
        model_id="gpt-4o-mini",
        display_name="GPT-4o mini",
        provider="OpenAI",
        input_per_million=0.15,
        output_per_million=0.60,
    ),
    "gpt-4-turbo": ModelPricing(
        model_id="gpt-4-turbo",
        display_name="GPT-4 Turbo",
        provider="OpenAI",
        input_per_million=10.00,
        output_per_million=30.00,
    ),
    "claude-3-5-sonnet": ModelPricing(
        model_id="claude-3-5-sonnet",
        display_name="Claude 3.5 Sonnet",
        provider="Anthropic",
        input_per_million=3.00,
        output_per_million=15.00,
    ),
    "claude-3-haiku": ModelPricing(
        model_id="claude-3-haiku",
        display_name="Claude 3 Haiku",
        provider="Anthropic",
        input_per_million=0.25,
        output_per_million=1.25,
    ),
    "gemini-1-5-pro": ModelPricing(
        model_id="gemini-1-5-pro",
        display_name="Gemini 1.5 Pro",
        provider="Google",
        input_per_million=1.25,
        output_per_million=5.00,
    ),
}

DEFAULT_MODEL = "gpt-4o"



@dataclass
class RequestCost:
    """Cost breakdown for a single API request."""
    model_id: str
    display_name: str
    provider: str

    input_tokens: int
    input_cost_usd: float          

    output_tokens: int
    output_cost_usd: float         

    total_cost_usd: float           

    @property
    def cost_per_token_usd(self) -> float:
        total_tokens = self.input_tokens + self.output_tokens
        if total_tokens == 0:
            return 0.0
        return self.total_cost_usd / total_tokens


@dataclass
class MonthlyCost:
    """Projected monthly cost given requests per day."""
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
    """Before/after cost comparison after applying optimizations."""
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

    @property
    def daily_savings_usd(self) -> float:
        return self.cost_saved_per_request * self.requests_per_day


class Calculator:
    """
    Translates token counts into dollar costs.

    All cost calculations are pure arithmetic:
        cost = (tokens / 1_000_000) * price_per_million

    Usage:
        calc = Calculator()
        cost = calc.request_cost(input_tokens=1000, model_id="gpt-4o")
        print(cost.input_cost_usd)   # $0.0025
    """

    def request_cost(
        self,
        input_tokens: int,
        model_id: str = DEFAULT_MODEL,
        output_tokens: int = 0,
    ) -> RequestCost:
        """
        Calculate the cost of a single API request.

        Args:
            input_tokens:  Number of input/prompt tokens
            model_id:      Model to price against (see MODELS dict)
            output_tokens: Number of output/completion tokens (default 0)

        Returns:
            RequestCost with full breakdown
        """
        pricing = self._get_pricing(model_id)

        input_cost = self._tokens_to_usd(input_tokens, pricing.input_per_million)
        output_cost = self._tokens_to_usd(output_tokens, pricing.output_per_million)

        return RequestCost(
            model_id=model_id,
            display_name=pricing.display_name,
            provider=pricing.provider,
            input_tokens=input_tokens,
            input_cost_usd=input_cost,
            output_tokens=output_tokens,
            output_cost_usd=output_cost,
            total_cost_usd=input_cost + output_cost,
        )

    def monthly_cost(
        self,
        input_tokens: int,
        requests_per_day: int,
        model_id: str = DEFAULT_MODEL,
        output_tokens: int = 0,
        days: int = 30,
    ) -> MonthlyCost:
        """
        Project monthly cost given a typical request size and volume.

        Args:
            input_tokens:     Tokens in a typical request
            requests_per_day: How many requests per day
            model_id:         Model to price against
            output_tokens:    Tokens in a typical response (default 0)
            days:             Number of days to project (default 30)
        """
        req_cost = self.request_cost(input_tokens, model_id, output_tokens)
        return MonthlyCost(
            request_cost=req_cost,
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
        """
        Compare cost before and after optimization.

        Args:
            original_tokens:  Token count before optimization
            optimized_tokens: Token count after optimization
            requests_per_day: Daily request volume for monthly projection
            model_id:         Model to price against
            days:             Projection window (default 30)
        """
        pricing = self._get_pricing(model_id)

        original_cost = self._tokens_to_usd(original_tokens, pricing.input_per_million)
        optimized_cost = self._tokens_to_usd(optimized_tokens, pricing.input_per_million)

        return CostComparison(
            model_id=model_id,
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            original_cost_usd=original_cost,
            optimized_cost_usd=optimized_cost,
            requests_per_day=requests_per_day,
            days=days,
        )

    def all_models_cost(
        self,
        input_tokens: int,
        output_tokens: int = 0,
    ) -> list[RequestCost]:
        """
        Calculate cost across all supported models for easy comparison.

        Returns list sorted by total cost ascending (cheapest first).
        """
        costs = [
            self.request_cost(input_tokens, model_id, output_tokens)
            for model_id in MODELS
        ]
        return sorted(costs, key=lambda c: c.total_cost_usd)


    @staticmethod
    def _get_pricing(model_id: str) -> ModelPricing:
        if model_id not in MODELS:
            available = ", ".join(MODELS.keys())
            raise ValueError(
                f"Unknown model '{model_id}'. Available: {available}"
            )
        return MODELS[model_id]

    @staticmethod
    def _tokens_to_usd(tokens: int, price_per_million: float) -> float:
        """Convert token count to USD. Pure arithmetic."""
        if tokens == 0:
            return 0.0
        return round((tokens / 1_000_000) * price_per_million, 10)



_default_calculator = Calculator()


def calculate_cost(
    input_tokens: int,
    model_id: str = DEFAULT_MODEL,
    output_tokens: int = 0,
) -> RequestCost:
    """Calculate cost for a single request. Convenience wrapper."""
    return _default_calculator.request_cost(input_tokens, model_id, output_tokens)


def calculate_monthly(
    input_tokens: int,
    requests_per_day: int,
    model_id: str = DEFAULT_MODEL,
    output_tokens: int = 0,
) -> MonthlyCost:
    """Project monthly cost. Convenience wrapper."""
    return _default_calculator.monthly_cost(
        input_tokens, requests_per_day, model_id, output_tokens
    )