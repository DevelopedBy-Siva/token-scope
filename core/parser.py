import json
import re
from dataclasses import dataclass, field as dataclass_field
from enum import Enum
from typing import Any

from tokenizer import Tokenizer, TokenAttribution, attribute_tokens


class FieldType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    NULL = "null"
    OBJECT = "object"
    ARRAY = "array"



@dataclass
class ParsedField:
    """A single field in the JSON tree, fully enriched for detection."""

    path: str               
    key: str                

    attributed_tokens: int
    pct_of_total: float

    depth: int              
    field_type: FieldType

    value: Any             
    char_length: int | None    
    array_length: int | None    
    child_count: int | None    

    @property
    def is_leaf(self) -> bool:
        return self.field_type not in (FieldType.OBJECT, FieldType.ARRAY)

    @property
    def is_container(self) -> bool:
        return not self.is_leaf

    @property
    def total_tokens(self) -> int:
        """Alias for attributed_tokens — consistent with FieldTokens API."""
        return self.attributed_tokens



@dataclass
class ParsedPayload:
    """Complete parsed representation of a JSON payload."""

    total_tokens: int
    fields: list[ParsedField] = dataclass_field(default_factory=list)

    @property
    def sorted_by_cost(self) -> list[ParsedField]:
        return sorted(self.fields, key=lambda f: f.attributed_tokens, reverse=True)

    @property
    def top_contributors(self) -> list[ParsedField]:
        return self.sorted_by_cost[:5]

    @property
    def leaves(self) -> list[ParsedField]:
        """Only leaf fields (strings, numbers, booleans, nulls)."""
        return [f for f in self.fields if f.is_leaf]

    @property
    def containers(self) -> list[ParsedField]:
        """Only container fields (objects, arrays)."""
        return [f for f in self.fields if f.is_container]

    @property
    def max_depth(self) -> int:
        if not self.fields:
            return 0
        return max(f.depth for f in self.fields)

    def fields_at_depth(self, depth: int) -> list[ParsedField]:
        return [f for f in self.fields if f.depth == depth]

    def get(self, path: str) -> ParsedField | None:
        """Look up a field by its path."""
        for f in self.fields:
            if f.path == path:
                return f
        return None



class Parser:
    """
    Walks a JSON payload and produces a fully enriched ParsedPayload.

    Usage:
        parser = Parser()
        result = parser.parse(payload)
        for field in result.sorted_by_cost:
            print(field.path, field.attributed_tokens, field.field_type)
    """

    def __init__(self, encoding: str = "cl100k_base"):
        self._tokenizer = Tokenizer(encoding)

    def parse(self, payload: dict | list) -> ParsedPayload:
        """
        Parse a JSON payload into a fully enriched ParsedPayload.

        Steps:
            1. Run token attribution (tokenizer)
            2. Build a token lookup map by path
            3. Walk the tree again to collect metadata per field
            4. Merge token attribution + metadata → ParsedField list
        """
        attribution = self._tokenizer.attribute(payload)

        token_map: dict[str, tuple[int, float]] = {
            f.path: (f.attributed_tokens, f.pct_of_total)
            for f in attribution.fields
        }

        parsed_fields: list[ParsedField] = []
        self._walk(payload, path="", depth=0, fields=parsed_fields, token_map=token_map)

        return ParsedPayload(
            total_tokens=attribution.total_tokens,
            fields=parsed_fields,
        )

    def _walk(
        self,
        node: Any,
        path: str,
        depth: int,
        fields: list[ParsedField],
        token_map: dict[str, tuple[int, float]],
    ) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{path}.{key}" if path else key
                self._record(child_path, key, value, depth, fields, token_map)
                if isinstance(value, (dict, list)):
                    self._walk(value, child_path, depth + 1, fields, token_map)

        elif isinstance(node, list):
            for i, item in enumerate(node):
                child_path = f"{path}[{i}]"
                self._record(child_path, "", item, depth, fields, token_map)
                if isinstance(item, (dict, list)):
                    self._walk(item, child_path, depth + 1, fields, token_map)

    def _record(
        self,
        path: str,
        key: str,
        value: Any,
        depth: int,
        fields: list[ParsedField],
        token_map: dict[str, tuple[int, float]],
    ) -> None:
        """Build a ParsedField for a single node and append to fields."""
        attributed, pct = token_map.get(path, (0, 0.0))

        field_type = self._type_of(value)

        char_length = len(value) if isinstance(value, str) else None
        array_length = len(value) if isinstance(value, list) else None
        child_count = len(value) if isinstance(value, dict) else None

        fields.append(ParsedField(
            path=path,
            key=key,
            attributed_tokens=attributed,
            pct_of_total=pct,
            depth=depth,
            field_type=field_type,
            value=value,
            char_length=char_length,
            array_length=array_length,
            child_count=child_count,
        ))

    @staticmethod
    def _type_of(value: Any) -> FieldType:
        if isinstance(value, bool):
            return FieldType.BOOLEAN
        if isinstance(value, (int, float)):
            return FieldType.NUMBER
        if isinstance(value, str):
            return FieldType.STRING
        if isinstance(value, list):
            return FieldType.ARRAY
        if isinstance(value, dict):
            return FieldType.OBJECT
        return FieldType.NULL



def parse_payload(
    payload: dict | list,
    encoding: str = "cl100k_base",
) -> ParsedPayload:
    """Parse a JSON payload into a fully enriched ParsedPayload."""
    return Parser(encoding).parse(payload)