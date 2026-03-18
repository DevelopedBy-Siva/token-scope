import re
import hashlib
from dataclasses import dataclass, field as dataclass_field
from enum import Enum

from parser import ParsedPayload, ParsedField, FieldType


class Severity(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


class RuleId(str, Enum):
    VERBOSE_SCHEMA    = "VERBOSE_SCHEMA"
    BLOATED_ARRAY     = "BLOATED_ARRAY"
    DUPLICATE_CONTENT = "DUPLICATE_CONTENT"
    REPEATED_KEYS     = "REPEATED_KEYS"
    LOW_SIGNAL_FIELDS = "LOW_SIGNAL_FIELDS"
    DEEP_NESTING      = "DEEP_NESTING"


@dataclass
class CostLeak:
    rule_id: RuleId
    severity: Severity
    path: str
    description: str
    estimated_savings: int
    affected_paths: list[str] = dataclass_field(default_factory=list)

    @property
    def severity_rank(self) -> int:
        return {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}[self.severity]


VERBOSE_SCHEMA_TOKEN_THRESHOLD  = 200
BLOATED_ARRAY_MIN_ITEMS         = 3
BLOATED_ARRAY_SIMILARITY_RATIO  = 0.5
REPEATED_KEY_MIN_COUNT          = 5
DEEP_NESTING_MIN_DEPTH          = 4
DUPLICATE_MIN_CHARS             = 50


class Detector:
    def detect(self, payload: ParsedPayload) -> list[CostLeak]:
        leaks: list[CostLeak] = []
        leaks.extend(self._check_verbose_schema(payload))
        leaks.extend(self._check_bloated_array(payload))
        leaks.extend(self._check_duplicate_content(payload))
        leaks.extend(self._check_repeated_keys(payload))
        leaks.extend(self._check_low_signal_fields(payload))
        leaks.extend(self._check_deep_nesting(payload))
        return sorted(leaks, key=lambda l: (l.severity_rank, -l.estimated_savings))

    def _check_verbose_schema(self, payload: ParsedPayload) -> list[CostLeak]:
        leaks = []
        for field in payload.fields:
            check_tokens = max(field.raw_tokens, field.attributed_tokens)
            if check_tokens >= VERBOSE_SCHEMA_TOKEN_THRESHOLD:
                leaks.append(CostLeak(
                    rule_id=RuleId.VERBOSE_SCHEMA,
                    severity=Severity.HIGH,
                    path=field.path,
                    description=(
                        f"'{field.path}' uses ~{check_tokens} tokens "
                        f"({field.pct_of_total:.1f}% of total). Verbose fields like "
                        f"tool schemas and long system prompts are a common hidden cost."
                    ),
                    estimated_savings=int(check_tokens * 0.4),
                    affected_paths=[field.path],
                ))
        return leaks

    def _check_bloated_array(self, payload: ParsedPayload) -> list[CostLeak]:
        leaks = []
        arrays = [f for f in payload.fields if f.field_type == FieldType.ARRAY]

        for array_field in arrays:
            if (array_field.array_length or 0) < BLOATED_ARRAY_MIN_ITEMS:
                continue

            prefix = f"{array_field.path}["
            children = [
                f for f in payload.fields
                if f.path.startswith(prefix)
                and f.path.count("[") == array_field.path.count("[") + 1
                and f.path.count(".") == array_field.path.count(".")
            ]

            if len(children) < BLOATED_ARRAY_MIN_ITEMS:
                continue

            token_counts = [c.attributed_tokens for c in children if c.attributed_tokens > 0]
            if not token_counts:
                continue

            avg = sum(token_counts) / len(token_counts)
            if avg < 5:
                continue

            similar_count = sum(
                1 for t in token_counts
                if abs(t - avg) / max(avg, 1) <= BLOATED_ARRAY_SIMILARITY_RATIO
            )

            if similar_count / len(token_counts) >= 0.6:
                total_array_tokens = sum(token_counts)
                trimmable = max(0, len(token_counts) - 2)
                savings = int((trimmable / len(token_counts)) * total_array_tokens)

                leaks.append(CostLeak(
                    rule_id=RuleId.BLOATED_ARRAY,
                    severity=Severity.HIGH,
                    path=array_field.path,
                    description=(
                        f"'{array_field.path}' has {array_field.array_length} similar items "
                        f"averaging {int(avg)} tokens each ({total_array_tokens} tokens total). "
                        f"Consider trimming to the most relevant items."
                    ),
                    estimated_savings=savings,
                    affected_paths=[array_field.path],
                ))
        return leaks

    def _check_duplicate_content(self, payload: ParsedPayload) -> list[CostLeak]:
        leaks = []
        string_fields = [
            f for f in payload.fields
            if f.field_type == FieldType.STRING
            and (f.char_length or 0) >= DUPLICATE_MIN_CHARS
        ]

        sentence_index: dict[str, list[ParsedField]] = {}
        for field in string_fields:
            for sentence in self._sentences(field.value):
                norm = self._normalize(sentence)
                if len(norm) >= DUPLICATE_MIN_CHARS:
                    sentence_index.setdefault(norm, []).append(field)

        already_flagged: set[str] = set()

        for sentence, fields in sentence_index.items():
            unique_fields = list({f.path: f for f in fields}.values())
            if len(unique_fields) >= 2:
                paths = [f.path for f in unique_fields]
                if any(p in already_flagged for p in paths):
                    continue
                already_flagged.update(paths)
                savings = sum(f.attributed_tokens for f in unique_fields[1:])
                leaks.append(CostLeak(
                    rule_id=RuleId.DUPLICATE_CONTENT,
                    severity=Severity.HIGH,
                    path=unique_fields[0].path,
                    description=(
                        f"Shared content detected across {len(unique_fields)} fields: "
                        f"{', '.join(paths)}. "
                        f"Deduplicating saves ~{savings} tokens."
                    ),
                    estimated_savings=savings,
                    affected_paths=paths,
                ))

        return leaks

    @staticmethod
    def _sentences(text: str) -> list[str]:
        import re as _re
        parts = _re.split(r'(?<=[.!?])\s+', text.strip())
        return [p for p in parts if len(p) >= DUPLICATE_MIN_CHARS]

    def _check_repeated_keys(self, payload: ParsedPayload) -> list[CostLeak]:
        leaks = []
        key_counts: dict[str, list[str]] = {}
        for field in payload.fields:
            if field.key:
                key_counts.setdefault(field.key, []).append(field.path)

        for key, paths in key_counts.items():
            if len(paths) >= REPEATED_KEY_MIN_COUNT:
                sample = next(f for f in payload.fields if f.key == key)
                key_token_cost = max(1, sample.attributed_tokens // 3)
                savings = key_token_cost * (len(paths) - 1)
                leaks.append(CostLeak(
                    rule_id=RuleId.REPEATED_KEYS,
                    severity=Severity.MEDIUM,
                    path=paths[0],
                    description=(
                        f"Key '{key}' appears {len(paths)} times across the payload. "
                        f"In structured data like conversation history, repeated keys "
                        f"add overhead with each turn."
                    ),
                    estimated_savings=savings,
                    affected_paths=paths,
                ))
        return leaks

    _UUID_PATTERN      = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
    _TIMESTAMP_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}')
    _UNIX_TS_PATTERN   = re.compile(r'^\d{10,13}$')
    _ID_KEY_PATTERN    = re.compile(r'^(id|_id|uuid|guid|request_id|trace_id|span_id|correlation_id|session_id|user_id|message_id)$', re.I)

    def _check_low_signal_fields(self, payload: ParsedPayload) -> list[CostLeak]:
        leaks = []
        for field in payload.fields:
            if not field.is_leaf:
                continue

            is_low_signal = False
            reason = ""

            if field.field_type == FieldType.STRING and isinstance(field.value, str):
                if self._UUID_PATTERN.match(field.value):
                    is_low_signal, reason = True, "UUID value"
                elif self._TIMESTAMP_PATTERN.match(field.value):
                    is_low_signal, reason = True, "timestamp value"
                elif self._UNIX_TS_PATTERN.match(field.value):
                    is_low_signal, reason = True, "unix timestamp value"

            if not is_low_signal and field.key and self._ID_KEY_PATTERN.match(field.key):
                is_low_signal, reason = True, f"key '{field.key}' is a metadata identifier"

            if is_low_signal and field.attributed_tokens > 0:
                leaks.append(CostLeak(
                    rule_id=RuleId.LOW_SIGNAL_FIELDS,
                    severity=Severity.MEDIUM,
                    path=field.path,
                    description=(
                        f"'{field.path}' contains a {reason} "
                        f"({field.attributed_tokens} tokens). "
                        f"Models don't reason over identifiers — safe to remove."
                    ),
                    estimated_savings=field.attributed_tokens,
                    affected_paths=[field.path],
                ))
        return leaks

    def _check_deep_nesting(self, payload: ParsedPayload) -> list[CostLeak]:
        leaks = []
        deep_fields = [f for f in payload.fields if f.depth >= DEEP_NESTING_MIN_DEPTH]

        if not deep_fields:
            return leaks

        ancestors: dict[str, list[ParsedField]] = {}
        for field in deep_fields:
            top = field.path.split(".")[0].split("[")[0]
            ancestors.setdefault(top, []).append(field)

        for ancestor, fields in ancestors.items():
            max_depth = max(f.depth for f in fields)
            total_tokens = sum(f.attributed_tokens for f in fields)
            leaks.append(CostLeak(
                rule_id=RuleId.DEEP_NESTING,
                severity=Severity.LOW,
                path=ancestor,
                description=(
                    f"'{ancestor}' reaches {max_depth} levels of nesting "
                    f"({len(fields)} deeply nested fields, {total_tokens} tokens). "
                    f"Deep nesting adds structural overhead and reduces readability."
                ),
                estimated_savings=int(total_tokens * 0.1),
                affected_paths=[f.path for f in fields],
            ))
        return leaks

    @staticmethod
    def _normalize(s: str) -> str:
        return " ".join(s.lower().split())


def detect_leaks(payload: ParsedPayload) -> list[CostLeak]:
    return Detector().detect(payload)