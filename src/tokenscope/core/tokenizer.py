import json
import tiktoken
from dataclasses import dataclass, field as dataclass_field
from typing import Any


@dataclass
class FieldTokens:
    path: str
    raw_tokens: int
    attributed_tokens: int  
    pct_of_total: float

    @property
    def display_path(self) -> str:
        return self.path or "<root>"


@dataclass
class TokenAttribution:
    total_tokens: int                          
    fields: list[FieldTokens] = dataclass_field(default_factory=list)

    @property
    def sorted_by_cost(self) -> list[FieldTokens]:
        return sorted(self.fields, key=lambda f: f.attributed_tokens, reverse=True)

    @property
    def top_contributors(self) -> list[FieldTokens]:
        return self.sorted_by_cost[:5]


class Tokenizer:
    """
    Wraps tiktoken and provides per-field token attribution.

    Encoding choices:
        "cl100k_base"  — GPT-4, GPT-3.5-turbo, Claude (~95%), Gemini (~90%)
        "o200k_base"   — GPT-4o
        "p50k_base"    — GPT-3 legacy

    Default: cl100k_base — best general-purpose approximation.
    """

    def __init__(self, encoding_name: str = "cl100k_base"):
        self.encoding_name = encoding_name
        self._enc = tiktoken.get_encoding(encoding_name)

    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(self._enc.encode(text))

    def count_json(self, payload: dict | list) -> int:
        return self.count(json.dumps(payload))

    def attribute(self, payload: dict | list) -> TokenAttribution:
        total = self.count_json(payload)
        raw_fields: list[tuple[str, int]] = []
        self._walk(payload, path="", raw_fields=raw_fields)
        fields = self._normalize(raw_fields, total)
        return TokenAttribution(total_tokens=total, fields=fields)

    def _walk(self, node: Any, path: str, raw_fields: list[tuple[str, int]]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{path}.{key}" if path else key
                raw_fields.append((child_path, self._weigh(key, value)))
                if isinstance(value, (dict, list)):
                    self._walk(value, child_path, raw_fields)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                child_path = f"{path}[{i}]"
                raw_fields.append((child_path, self._weigh(None, item)))
                if isinstance(item, (dict, list)):
                    self._walk(item, child_path, raw_fields)

    def _weigh(self, key: str | None, value: Any) -> int:
        fragment = json.dumps({key: value}) if key is not None else json.dumps([value])
        return max(1, self.count(fragment))

    def _normalize(self, raw_fields: list[tuple[str, int]], total: int) -> list[FieldTokens]:
        if not raw_fields:
            return []

        sum_raw = sum(w for _, w in raw_fields)
        if sum_raw == 0:
            equal = total // len(raw_fields)
            return [
                FieldTokens(path=p, raw_tokens=0, attributed_tokens=equal,
                            pct_of_total=round(equal / total * 100, 2) if total else 0.0)
                for p, _ in raw_fields
            ]

        attributed = [round(raw / sum_raw * total) for _, raw in raw_fields]

        diff = total - sum(attributed)
        if diff != 0:
            largest = max(range(len(attributed)), key=lambda i: attributed[i])
            attributed[largest] += diff

        return [
            FieldTokens(
                path=path,
                raw_tokens=raw,
                attributed_tokens=attr,
                pct_of_total=round(attr / total * 100, 2) if total else 0.0,
            )
            for (path, raw), attr in zip(raw_fields, attributed)
        ]


_cache: dict[str, Tokenizer] = {}


def get_tokenizer(encoding: str = "cl100k_base") -> Tokenizer:
    if encoding not in _cache:
        _cache[encoding] = Tokenizer(encoding)
    return _cache[encoding]


def count_tokens(text: str, encoding: str = "cl100k_base") -> int:
    return get_tokenizer(encoding).count(text)


def attribute_tokens(payload: dict | list, encoding: str = "cl100k_base") -> TokenAttribution:
    return get_tokenizer(encoding).attribute(payload)