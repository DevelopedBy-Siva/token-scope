import json
import tiktoken
from typing import Any
from dataclasses import dataclass, field as dataclass_field



@dataclass
class FieldTokens:
    """Token attribution for a single field in the JSON tree."""
    path: str               
    raw_tokens: int          
    attributed_tokens: int   
    pct_of_total: float      
    
    @property
    def display_path(self) -> str:
        return self.path or "<root>"

    @property
    def total_tokens(self) -> int:
        """Alias for attributed_tokens — used by downstream consumers."""
        return self.attributed_tokens


@dataclass
class TokenAttribution:
    """Full token breakdown for an entire payload."""
    total_tokens: int
    fields: list[FieldTokens] = dataclass_field(default_factory=list)

    @property
    def sorted_by_cost(self) -> list[FieldTokens]:
        """Fields ranked most expensive first."""
        return sorted(self.fields, key=lambda f: f.attributed_tokens, reverse=True)

    @property
    def top_contributors(self) -> list[FieldTokens]:
        """Top 5 most expensive fields."""
        return self.sorted_by_cost[:5]

    @property
    def field_sum(self) -> int:
        """Sum of all attributed token counts. Always equals total_tokens."""
        return sum(f.attributed_tokens for f in self.fields)



class Tokenizer:
    """
    Wraps tiktoken and provides per-field token attribution.

    Encoding choices:
        "cl100k_base"  → GPT-4, GPT-3.5-turbo, Claude (~95%), Gemini (~90%)
        "o200k_base"   → GPT-4o
        "p50k_base"    → GPT-3 legacy

    Default: cl100k_base — best general-purpose approximation.
    """

    def __init__(self, encoding_name: str = "cl100k_base"):
        self.encoding_name = encoding_name
        self._enc = tiktoken.get_encoding(encoding_name)


    def count(self, text: str) -> int:
        """Count tokens in a plain string."""
        if not text:
            return 0
        return len(self._enc.encode(text))

    def count_json(self, payload: dict | list) -> int:
        """Count tokens in a fully serialized JSON payload."""
        return self.count(json.dumps(payload))

    def attribute(self, payload: dict | list) -> TokenAttribution:
        """
        Attribute token costs across all fields in a JSON payload.

        Uses two-pass proportional attribution — see module docstring.
        The total is always the exact tiktoken count. Per-field counts
        are proportionally normalized and guaranteed to sum to the total.
        """
        total = self.count_json(payload)

        raw_fields: list[tuple[str, int]] = []
        self._walk(payload, path="", raw_fields=raw_fields)

        fields = self._normalize(raw_fields, total)

        return TokenAttribution(total_tokens=total, fields=fields)

    def _walk(
        self,
        node: Any,
        path: str,
        raw_fields: list[tuple[str, int]],
        is_root: bool = True,
    ) -> None:
        """Recursively walk a JSON node. Collect (path, raw_weight) pairs."""
        if isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{path}.{key}" if path else key
                raw = self._weigh(key, value)
                raw_fields.append((child_path, raw))
                # Recurse into containers
                if isinstance(value, (dict, list)):
                    self._walk(value, child_path, raw_fields, is_root=False)

        elif isinstance(node, list):
            for i, item in enumerate(node):
                child_path = f"{path}[{i}]"
                raw = self._weigh(None, item)
                raw_fields.append((child_path, raw))
                if isinstance(item, (dict, list)):
                    self._walk(item, child_path, raw_fields, is_root=False)

    def _weigh(self, key: str | None, value: Any) -> int:
        """
        Tokenize a key+value pair in isolation to get its raw weight.

        Serialize as a minimal JSON fragment to give tiktoken realistic
        context (quotes, colon, braces) without influence from the rest
        of the payload:
            key present:  {"key": <value>}
            key absent:   [<value>]
        """
        if key is not None:
            fragment = json.dumps({key: value})
        else:
            fragment = json.dumps([value])

        return max(1, self.count(fragment))

    def _normalize(
        self,
        raw_fields: list[tuple[str, int]],
        total: int,
    ) -> list[FieldTokens]:
        """
        Scale raw weights so attributed counts sum exactly to total.

        Each field gets: round(raw / sum_raw * total)
        Rounding correction applied to the largest field so sum is exact.
        """
        if not raw_fields:
            return []

        sum_raw = sum(w for _, w in raw_fields)
        if sum_raw == 0:
            equal = total // len(raw_fields)
            return [
                FieldTokens(
                    path=path,
                    raw_tokens=0,
                    attributed_tokens=equal,
                    pct_of_total=round(equal / total * 100, 2) if total else 0.0,
                )
                for path, _ in raw_fields
            ]

        attributed = [
            round(raw / sum_raw * total)
            for _, raw in raw_fields
        ]

        diff = total - sum(attributed)
        if diff != 0:
            largest_idx = max(range(len(attributed)), key=lambda i: attributed[i])
            attributed[largest_idx] += diff

        fields = []
        for (path, raw), attr in zip(raw_fields, attributed):
            fields.append(FieldTokens(
                path=path,
                raw_tokens=raw,
                attributed_tokens=attr,
                pct_of_total=round(attr / total * 100, 2) if total else 0.0,
            ))

        return fields



_tokenizer_cache: dict[str, Tokenizer] = {}


def get_tokenizer(encoding: str = "cl100k_base") -> Tokenizer:
    """Get or create a cached Tokenizer for a given encoding."""
    if encoding not in _tokenizer_cache:
        _tokenizer_cache[encoding] = Tokenizer(encoding)
    return _tokenizer_cache[encoding]


def count_tokens(text: str, encoding: str = "cl100k_base") -> int:
    """Count tokens in a plain string."""
    return get_tokenizer(encoding).count(text)


def attribute_tokens(
    payload: dict | list,
    encoding: str = "cl100k_base",
) -> TokenAttribution:
    """Attribute token costs across all fields in a JSON payload."""
    return get_tokenizer(encoding).attribute(payload)