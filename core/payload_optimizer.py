import copy
import re
from dataclasses import dataclass, field as dataclass_field
from typing import Any

from core.leak_detector import CostLeak, RuleId
from core.parser import ParsedPayload, parse_payload


LOW_SIGNAL_KEY_PATTERN = re.compile(
    r'^(id|_id|uuid|guid|request_id|trace_id|span_id|correlation_id|session_id|user_id|message_id)$',
    re.I,
)
UUID_PATTERN      = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
TIMESTAMP_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}')
UNIX_TS_PATTERN   = re.compile(r'^\d{10,13}$')

DEFAULT_ARRAY_TRIM_SIZE = 3


@dataclass
class OptimizationResult:
    original_payload: dict | list
    optimized_payload: dict | list
    original_tokens: int
    optimized_tokens: int
    applied_rules: list[RuleId] = dataclass_field(default_factory=list)

    @property
    def tokens_saved(self) -> int:
        return self.original_tokens - self.optimized_tokens

    @property
    def pct_saved(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return round((self.tokens_saved / self.original_tokens) * 100, 2)


class Optimizer:
    def optimize(
        self,
        payload: dict | list,
        leaks: list[CostLeak],
        rules_to_apply: list[RuleId] | None = None,
    ) -> OptimizationResult:
        original_parsed = parse_payload(payload)
        original_tokens = original_parsed.total_tokens

        active_rules = set(rules_to_apply) if rules_to_apply else {r for r in RuleId}
        active_leaks = [l for l in leaks if l.rule_id in active_rules]

        optimized = copy.deepcopy(payload)
        applied: list[RuleId] = []

        rule_order = [
            RuleId.DUPLICATE_CONTENT,
            RuleId.LOW_SIGNAL_FIELDS,
            RuleId.VERBOSE_SCHEMA,
            RuleId.BLOATED_ARRAY,
            RuleId.REPEATED_KEYS,
            RuleId.DEEP_NESTING,
        ]

        for rule_id in rule_order:
            if rule_id not in active_rules:
                continue
            rule_leaks = [l for l in active_leaks if l.rule_id == rule_id]
            if not rule_leaks:
                continue

            handler = self._handlers().get(rule_id)
            if handler:
                changed = handler(optimized, rule_leaks)
                if changed:
                    applied.append(rule_id)

        optimized_tokens = parse_payload(optimized).total_tokens

        return OptimizationResult(
            original_payload=payload,
            optimized_payload=optimized,
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            applied_rules=applied,
        )

    def _handlers(self):
        return {
            RuleId.LOW_SIGNAL_FIELDS: self._apply_low_signal,
            RuleId.BLOATED_ARRAY:     self._apply_bloated_array,
            RuleId.DUPLICATE_CONTENT: self._apply_duplicate_content,
            RuleId.DEEP_NESTING:      self._apply_deep_nesting,
        }

    def _apply_low_signal(self, payload: dict | list, leaks: list[CostLeak]) -> bool:
        paths = {l.path for l in leaks}
        changed = False
        for path in paths:
            if _delete_path(payload, path):
                changed = True
        return changed

    def _apply_bloated_array(self, payload: dict | list, leaks: list[CostLeak]) -> bool:
        changed = False
        for leak in leaks:
            arr = _get_path(payload, leak.path)
            if isinstance(arr, list) and len(arr) > DEFAULT_ARRAY_TRIM_SIZE:
                parent, key = _resolve_parent(payload, leak.path)
                if parent is not None:
                    if isinstance(parent, dict):
                        parent[key] = arr[:DEFAULT_ARRAY_TRIM_SIZE]
                    elif isinstance(parent, list):
                        parent[int(key)] = arr[:DEFAULT_ARRAY_TRIM_SIZE]
                    changed = True
        return changed

    def _apply_duplicate_content(self, payload: dict | list, leaks: list[CostLeak]) -> bool:
        changed = False
        for leak in leaks:
            if len(leak.affected_paths) < 2:
                continue
            for path in leak.affected_paths[1:]:
                if _delete_path(payload, path):
                    changed = True
        return changed

    def _apply_deep_nesting(self, payload: dict | list, leaks: list[CostLeak]) -> bool:
        changed = False
        for leak in leaks:
            node = _get_path(payload, leak.path)
            if isinstance(node, dict):
                flattened = {}
                _flatten_dict(node, prefix="", out=flattened)
                parent, key = _resolve_parent(payload, leak.path)
                if parent is not None and isinstance(parent, dict):
                    parent[key] = flattened
                    changed = True
        return changed


def _get_path(payload: Any, path: str) -> Any:
    parts = _split_path(path)
    node = payload
    try:
        for part in parts:
            if isinstance(part, int):
                node = node[part]
            else:
                node = node[part]
    except (KeyError, IndexError, TypeError):
        return None
    return node


def _delete_path(payload: Any, path: str) -> bool:
    parts = _split_path(path)
    if not parts:
        return False
    node = payload
    try:
        for part in parts[:-1]:
            if isinstance(part, int):
                node = node[part]
            else:
                node = node[part]
        last = parts[-1]
        if isinstance(last, int) and isinstance(node, list):
            node.pop(last)
            return True
        elif isinstance(last, str) and isinstance(node, dict) and last in node:
            del node[last]
            return True
    except (KeyError, IndexError, TypeError):
        pass
    return False


def _resolve_parent(payload: Any, path: str) -> tuple[Any, str | int]:
    parts = _split_path(path)
    if not parts:
        return None, ""
    node = payload
    try:
        for part in parts[:-1]:
            if isinstance(part, int):
                node = node[part]
            else:
                node = node[part]
        return node, parts[-1]
    except (KeyError, IndexError, TypeError):
        return None, ""


def _split_path(path: str) -> list[str | int]:
    parts = []
    for segment in re.split(r'\.|\[(\d+)\]', path):
        if segment is None:
            continue
        segment = segment.strip()
        if not segment:
            continue
        if segment.isdigit():
            parts.append(int(segment))
        else:
            parts.append(segment)
    return parts


def _flatten_dict(node: dict, prefix: str, out: dict) -> None:
    for key, value in node.items():
        flat_key = f"{prefix}_{key}" if prefix else key
        if isinstance(value, dict):
            _flatten_dict(value, flat_key, out)
        else:
            out[flat_key] = value


def optimize_payload(
    payload: dict | list,
    leaks: list[CostLeak],
    rules_to_apply: list[RuleId] | None = None,
) -> OptimizationResult:
    return Optimizer().optimize(payload, leaks, rules_to_apply)