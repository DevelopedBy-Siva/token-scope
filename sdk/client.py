import sys
import os
import time
from dataclasses import dataclass, field as dataclass_field
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.parser import parse_payload, ParsedPayload
from core.leak_detector import detect_leaks, CostLeak
from core.payload_optimizer import optimize_payload, OptimizationResult
from core.calculator import Calculator, DEFAULT_MODEL


@dataclass
class CapturedCall:
    index: int
    model: str
    payload: dict           
    actual_payload: dict    
    response_text: str
    input_tokens: int      
    output_tokens: int      
    analyzed_tokens: int    
    parsed: ParsedPayload
    leaks: list[CostLeak]
    optimization: OptimizationResult
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    duration_ms: float
    timestamp: float


class TokenScopeSession:
    def __init__(self):
        self.calls: list[CapturedCall] = []
        self._calculator = Calculator()
        self._call_index = 0

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    @property
    def total_cost_usd(self) -> float:
        return sum(c.total_cost_usd for c in self.calls)

    @property
    def total_tokens_saved(self) -> int:
        return sum(c.optimization.tokens_saved for c in self.calls)

    @property
    def total_analyzed_tokens(self) -> int:
        return sum(c.analyzed_tokens for c in self.calls)

    def _record(
        self,
        payload: dict,
        actual_payload: dict,
        response_text: str,
        input_tokens: int,
        output_tokens: int,
        model_id: str,
        duration_ms: float,
    ) -> CapturedCall:
        parsed = parse_payload(payload)
        leaks = detect_leaks(parsed)
        optimization = optimize_payload(payload, leaks)

        cost = self._calculator.request_cost(
            input_tokens=input_tokens,
            model_id=model_id,
            output_tokens=output_tokens,
        )

        self._call_index += 1
        call = CapturedCall(
            index=self._call_index,
            model=model_id,
            payload=payload,
            actual_payload=actual_payload,
            response_text=response_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            analyzed_tokens=parsed.total_tokens,
            parsed=parsed,
            leaks=leaks,
            optimization=optimization,
            input_cost_usd=cost.input_cost_usd,
            output_cost_usd=cost.output_cost_usd,
            total_cost_usd=cost.total_cost_usd,
            duration_ms=duration_ms,
            timestamp=time.time(),
        )
        self.calls.append(call)
        return call


class TokenScope:
    def __init__(self, openai_client: Any, model_id: str = DEFAULT_MODEL, auto_report: bool = True):
        self._client = openai_client
        self._model_id = model_id
        self._auto_report = auto_report
        self.session = TokenScopeSession()
        self.chat = _ChatCompletionsWrapper(self)

    def report(self) -> str:
        from sdk.reporter import generate_report
        return generate_report(self.session)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self._auto_report and self.session.calls:
            self.report()


class _ChatCompletionsWrapper:
    def __init__(self, scope: TokenScope):
        self._scope = scope

    TOKENSCOPE_KEYS = {"extra_metadata", "extra_data"}

    def create(self, **kwargs) -> Any:
        tokenscope_meta = {k: kwargs.pop(k) for k in list(kwargs) if k in self.TOKENSCOPE_KEYS}
        start = time.perf_counter()
        response = self._scope._client.chat.completions.create(**kwargs)
        duration_ms = (time.perf_counter() - start) * 1000

        model_id = kwargs.get("model", self._scope._model_id)


        actual_payload = {**kwargs}
        analyzed_payload = {**kwargs}
        for meta_val in tokenscope_meta.values():
            if isinstance(meta_val, dict):
                analyzed_payload.update(meta_val)

        from tokenscope.core.parser import parse_payload as _parse
        input_tokens = _parse(actual_payload).total_tokens

        output_tokens = 0
        response_text = ""

        if hasattr(response, "usage") and response.usage:
            output_tokens = response.usage.completion_tokens or 0

        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                response_text = choice.message.content or ""

        model_pricing_id = self._resolve_model_id(model_id)

        self._scope.session._record(
            payload=analyzed_payload,
            actual_payload=actual_payload,
            response_text=response_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_id=model_pricing_id,
            duration_ms=duration_ms,
        )

        return response

    @staticmethod
    def _resolve_model_id(model: str) -> str:
        mapping = {
            "gpt-4o-mini": "gpt-4o-mini",
            "gpt-4o": "gpt-4o",
            "gpt-4-turbo-preview": "gpt-4-turbo",
            "gpt-4-turbo": "gpt-4-turbo",
            "gpt-4": "gpt-4-turbo",
            "claude-3-5-sonnet": "claude-3-5-sonnet",
            "claude-3-haiku": "claude-3-haiku",
            "gemini-1-5-pro": "gemini-1-5-pro",
        }
        for key, val in mapping.items():
            if model.startswith(key):
                return val
        return model