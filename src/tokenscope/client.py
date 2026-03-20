import time
from dataclasses import dataclass, field as dataclass_field
from typing import Any

from tokenscope.core.parser import parse_payload, ParsedPayload
from tokenscope.core.leak_detector import detect_leaks, CostLeak
from tokenscope.core.payload_optimizer import optimize_payload, OptimizationResult
from tokenscope.core.calculator import Calculator, resolve_model_id, DEFAULT_MODEL
from tokenscope.reporter import generate_report


@dataclass
class CapturedCall:
    index: int
    model: str
    input_tokens: int
    output_tokens: int
    analyzed_tokens: int      
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    duration_ms: float
    parsed: ParsedPayload
    leaks: list[CostLeak]
    optimization: OptimizationResult


class TokenScopeSession:
    def __init__(self):
        self.calls: list[CapturedCall] = []
        self._calculator = Calculator()
        self._index = 0

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    @property
    def total_analyzed_tokens(self) -> int:
        return sum(c.analyzed_tokens for c in self.calls)

    @property
    def total_cost_usd(self) -> float:
        return sum(c.total_cost_usd for c in self.calls)

    @property
    def total_tokens_saveable(self) -> int:
        return sum(c.optimization.tokens_saved for c in self.calls)

    def record(
        self,
        *,
        model: str,
        payload: dict,
        input_tokens: int,
        output_tokens: int,
        duration_ms: float,
        extra_data: dict | None = None,
    ) -> CapturedCall:
        analyzed_payload = {**payload, **(extra_data or {})}
        parsed = parse_payload(analyzed_payload)
        leaks = detect_leaks(parsed)
        optimization = optimize_payload(analyzed_payload, leaks)

        model_id = resolve_model_id(model)
        cost = self._calculator.request_cost(
            input_tokens=input_tokens,
            model_id=model_id,
            output_tokens=output_tokens,
        )

        self._index += 1
        call = CapturedCall(
            index=self._index,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            analyzed_tokens=parsed.total_tokens,
            input_cost_usd=cost.input_cost_usd,
            output_cost_usd=cost.output_cost_usd,
            total_cost_usd=cost.total_cost_usd,
            duration_ms=duration_ms,
            parsed=parsed,
            leaks=leaks,
            optimization=optimization,
        )
        self.calls.append(call)
        return call


class TokenScope:

    def __init__(self):
        self.session = TokenScopeSession()

    def report(self) -> str:
        """Generate the HTML report. Returns the output path."""
        return generate_report(self.session)

    @classmethod
    def wrap(cls, client: Any) -> "_WrappedClient":
        """
        Auto-detect client type and return the right wrapper.
        Supports OpenAI-compatible clients and Anthropic SDK.

        Usage:
            with TokenScope.wrap(OpenAI()) as client:
                client.chat.completions.create(...)
        """
        scope = cls()
        return scope._wrap(client)

    def _wrap(self, client: Any) -> "_WrappedClient":
        module = type(client).__module__ or ""
        if module.startswith("anthropic"):
            return _AnthropicWrapper(client, self)
        return _OpenAIWrapper(client, self)

    def wrap_openai(self, client: Any) -> "_OpenAIWrapper":
        return _OpenAIWrapper(client, self)

    def wrap_anthropic(self, client: Any) -> "_AnthropicWrapper":
        return _AnthropicWrapper(client, self)

    @classmethod
    def langchain_handler(cls) -> "_LangChainHandler":
        scope = cls()
        handler = _LangChainHandler(scope)
        return handler

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.session.calls:
            self.report()


class _OpenAIWrapper:
    """
    Wraps an OpenAI-compatible client.

    Usage:
        with TokenScope.wrap(OpenAI()) as client:
            client.chat.completions.create(
                model="gpt-4o",
                messages=[...],
                extra_data={"retrieved_chunks": chunks},  # stripped before API call
            )
    """

    _STRIP_KEYS = {"extra_data"}

    def __init__(self, client: Any, scope: TokenScope):
        self._client = client
        self._scope = scope
        self.chat = _ChatCompletions(client, scope, self._STRIP_KEYS)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self._scope.session.calls:
            self._scope.report()


class _ChatCompletions:
    def __init__(self, client: Any, scope: TokenScope, strip_keys: set[str]):
        self._client = client
        self._scope = scope
        self._strip_keys = strip_keys

    @property
    def completions(self):
        return self

    def create(self, **kwargs) -> Any:
        extra_data = {k: kwargs.pop(k) for k in list(kwargs) if k in self._strip_keys}
        extra = extra_data.get("extra_data")

        t0 = time.perf_counter()
        response = self._client.chat.completions.create(**kwargs)
        duration_ms = (time.perf_counter() - t0) * 1000

        model = kwargs.get("model", DEFAULT_MODEL)
        input_tokens = getattr(getattr(response, "usage", None), "prompt_tokens", 0) or 0
        output_tokens = getattr(getattr(response, "usage", None), "completion_tokens", 0) or 0

        if input_tokens == 0:
            input_tokens = parse_payload(kwargs).total_tokens

        self._scope.session.record(
            model=model,
            payload=kwargs,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            extra_data={"extra_data": extra} if extra else None,
        )

        return response


class _AnthropicWrapper:
    """
    Wraps the Anthropic Python SDK.

    Usage:
        import anthropic
        with TokenScope.wrap(anthropic.Anthropic()) as client:
            client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=[{"role": "user", "content": "Hello"}],
            )
    """

    def __init__(self, client: Any, scope: TokenScope):
        self._client = client
        self._scope = scope
        self.messages = _AnthropicMessages(client, scope)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self._scope.session.calls:
            self._scope.report()


class _AnthropicMessages:
    def __init__(self, client: Any, scope: TokenScope):
        self._client = client
        self._scope = scope

    def create(self, **kwargs) -> Any:
        extra_data = kwargs.pop("extra_data", None)

        t0 = time.perf_counter()
        response = self._client.messages.create(**kwargs)
        duration_ms = (time.perf_counter() - t0) * 1000

        model = kwargs.get("model", "unknown")

        # Anthropic returns usage as response.usage.input_tokens / output_tokens
        usage = getattr(response, "usage", None)
        input_tokens  = getattr(usage, "input_tokens",  0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0

        if input_tokens == 0:
            input_tokens = parse_payload(kwargs).total_tokens

        self._scope.session.record(
            model=model,
            payload=kwargs,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            extra_data={"extra_data": extra_data} if extra_data else None,
        )

        return response


try:
    from langchain_core.callbacks import BaseCallbackHandler as _BaseCallbackHandler
    _LANGCHAIN_BASE = _BaseCallbackHandler
except ImportError:
    _LANGCHAIN_BASE = object


class _LangChainHandler(_LANGCHAIN_BASE):
    """
    LangChain callback handler for TokenScope.

    Usage:
        handler = TokenScope.langchain_handler()

        # Attach to a chain
        chain.invoke({"input": "..."}, config={"callbacks": [handler]})

        # Or attach to an LLM directly
        llm = ChatOpenAI(callbacks=[handler])

        # Report at any time
        handler.scope.report()

        # Or use as context manager
        with TokenScope.langchain_handler() as handler:
            chain.invoke(...)
    """

    def __init__(self, scope: TokenScope):
        self.scope = scope
        self._pending: dict[str, dict] = {}  

    def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs) -> None:
        run_id = str(kwargs.get("run_id", id(prompts)))
        self._pending[run_id] = {
            "model": serialized.get("kwargs", {}).get("model_name", "unknown"),
            "prompts": prompts,
            "t0": time.perf_counter(),
        }

    def on_chat_model_start(self, serialized: dict, messages: list, **kwargs) -> None:
        run_id = str(kwargs.get("run_id", id(messages)))
        flat_messages = []
        for batch in messages:
            for m in batch:
                role = getattr(m, "type", "user")
                content = getattr(m, "content", str(m))
                flat_messages.append({"role": role, "content": content})

        self._pending[run_id] = {
            "model": serialized.get("kwargs", {}).get("model_name", "unknown"),
            "payload": {"messages": flat_messages},
            "t0": time.perf_counter(),
        }

    def on_llm_end(self, response: Any, **kwargs) -> None:
        run_id = str(kwargs.get("run_id", ""))
        meta = self._pending.pop(run_id, {})
        t0 = meta.get("t0", time.perf_counter())
        duration_ms = (time.perf_counter() - t0) * 1000

        model = meta.get("model", "unknown")

        input_tokens = output_tokens = 0
        try:
            usage = response.llm_output.get("token_usage", {})
            input_tokens  = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
        except Exception:
            pass

        payload = meta.get("payload", {})
        if not payload and "prompts" in meta:
            payload = {"prompts": meta["prompts"]}

        if input_tokens == 0 and payload:
            input_tokens = parse_payload(payload).total_tokens

        self.scope.session.record(
            model=model,
            payload=payload,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
        )

    def on_llm_error(self, error: Exception, **kwargs) -> None:
        run_id = str(kwargs.get("run_id", ""))
        self._pending.pop(run_id, None)

    def on_chain_start(self, *args, **kwargs): pass
    def on_chain_end(self, *args, **kwargs): pass
    def on_chain_error(self, *args, **kwargs): pass
    def on_tool_start(self, *args, **kwargs): pass
    def on_tool_end(self, *args, **kwargs): pass
    def on_tool_error(self, *args, **kwargs): pass
    def on_agent_action(self, *args, **kwargs): pass
    def on_agent_finish(self, *args, **kwargs): pass
    def on_text(self, *args, **kwargs): pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.scope.session.calls:
            self.scope.report()