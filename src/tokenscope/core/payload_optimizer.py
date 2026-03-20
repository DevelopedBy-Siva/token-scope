import copy
import re
from dataclasses import dataclass, field as dataclass_field
from typing import Any

from tokenscope.core.leak_detector import CostLeak, RuleId
from tokenscope.core.parser import parse_payload


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
        return max(0, self.original_tokens - self.optimized_tokens)

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
        original_tokens = parse_payload(payload).total_tokens
        active_rules = set(rules_to_apply) if rules_to_apply is not None else set(RuleId)

        if not active_rules:
            return OptimizationResult(
                original_payload=payload,
                optimized_payload=payload,
                original_tokens=original_tokens,
                optimized_tokens=original_tokens,
            )

        active_leaks = [l for l in leaks if l.rule_id in active_rules]
        optimized = copy.deepcopy(payload)
        applied: list[RuleId] = []

        for rule_id in [
            RuleId.DUPLICATE_CONTENT,
            RuleId.LOW_SIGNAL_FIELDS,
            RuleId.VERBOSE_SCHEMA,
            RuleId.BLOATED_ARRAY,
            RuleId.REPEATED_KEYS,
            RuleId.DEEP_NESTING,
        ]:
            if rule_id not in active_rules:
                continue
            rule_leaks = [l for l in active_leaks if l.rule_id == rule_id]
            if not rule_leaks:
                continue
            handler = self._handlers().get(rule_id)
            if handler and handler(optimized, rule_leaks):
                applied.append(rule_id)

        return OptimizationResult(
            original_payload=payload,
            optimized_payload=optimized,
            original_tokens=original_tokens,
            optimized_tokens=parse_payload(optimized).total_tokens,
            applied_rules=applied,
        )

    def _handlers(self):
        return {
            RuleId.LOW_SIGNAL_FIELDS: self._apply_low_signal,
            RuleId.BLOATED_ARRAY:     self._apply_bloated_array,
            RuleId.DUPLICATE_CONTENT: self._apply_duplicate_content,
            RuleId.DEEP_NESTING:      self._apply_deep_nesting,
        }

    def _apply_low_signal(self, payload, leaks):
        return any(_delete_path(payload, l.path) for l in leaks)

    def _apply_bloated_array(self, payload, leaks):
        changed = False
        for leak in leaks:
            arr = _get_path(payload, leak.path)
            if isinstance(arr, list) and len(arr) > DEFAULT_ARRAY_TRIM_SIZE:
                parent, key = _resolve_parent(payload, leak.path)
                if parent is not None:
                    target = parent[key] if isinstance(parent, dict) else parent[int(key)]
                    if isinstance(parent, dict):
                        parent[key] = arr[:DEFAULT_ARRAY_TRIM_SIZE]
                    else:
                        parent[int(key)] = arr[:DEFAULT_ARRAY_TRIM_SIZE]
                    changed = True
        return changed

    def _apply_duplicate_content(self, payload, leaks):
        changed = False
        for leak in leaks:
            for path in leak.affected_paths[1:]:
                if _delete_path(payload, path):
                    changed = True
        return changed

    def _apply_deep_nesting(self, payload, leaks):
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
    node = payload
    try:
        for part in _split_path(path):
            node = node[part] if isinstance(part, int) else node[part]
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
            node = node[part] if isinstance(part, int) else node[part]
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
            node = node[part] if isinstance(part, int) else node[part]
        return node, parts[-1]
    except (KeyError, IndexError, TypeError):
        return None, ""


def _split_path(path: str) -> list[str | int]:
    parts = []
    for segment in re.split(r'\.|\[(\d+)\]', path):
        if segment is None or not segment.strip():
            continue
        s = segment.strip()
        parts.append(int(s) if s.isdigit() else s)
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