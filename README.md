# TokenScope 🔬

### Profile your LLM payloads. Find the waste. Cut the cost.

```bash
pip install llm-tokenscope
```

---

## What It Does

Every LLM API call you make contains more than just your prompt. It contains JSON — keys, nested objects, tool schemas, conversation history, metadata, UUIDs. By the time it hits the API, your code has assembled something expensive that you've never actually looked at.

TokenScope intercepts your API calls, attributes token costs to individual fields, detects structural waste, and tells you exactly where your money is going.

---

## Quickstart

```python
from tokenscope import TokenScope
from openai import OpenAI

client = TokenScope(OpenAI())

response = client.chat.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

That's it. After your session ends, a report opens automatically in your browser.

---

## The Report

Every call in your session gets a card showing:

- **Top Cost Fields** — which specific JSON fields are consuming the most tokens
- **Cost Leaks** — detected waste with severity (High / Medium / Low)
- **Tokens Saveable** — how many tokens could be removed without losing signal

The session summary shows total calls, total tokens, total cost, and aggregate savings across all calls.

---

## Cost Leaks Detected

| Rule                | What It Catches                                      | Severity  |
| ------------------- | ---------------------------------------------------- | --------- |
| `VERBOSE_SCHEMA`    | Tool/function descriptions over 200 tokens           | 🔴 High   |
| `BLOATED_ARRAY`     | Arrays with 3+ similar items that could be trimmed   | 🔴 High   |
| `DUPLICATE_CONTENT` | Same content appearing in multiple fields            | 🔴 High   |
| `REPEATED_KEYS`     | Same key appearing 5+ times across the payload       | 🟡 Medium |
| `LOW_SIGNAL_FIELDS` | UUIDs, timestamps, IDs the model doesn't reason over | 🟡 Medium |
| `DEEP_NESTING`      | Objects nested 4+ levels deep                        | 🟢 Low    |

---

## Passing Extra Context

You can attach additional data to a call for profiling without it being sent to the API:

```python
client.chat.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Summarize the context"}],
    extra_data={
        "context": [{"text": chunk} for chunk in retrieved_chunks],
        "request_id": "abc-123",
    }
)
```

`extra_data` and `extra_metadata` are stripped before the API call and merged into the payload for analysis only.

---

## Context Manager

```python
with TokenScope(OpenAI()) as client:
    client.chat.create(...)
    client.chat.create(...)
    client.chat.create(...)
# Report generated automatically on exit
```

---

## Manual Report

```python
client = TokenScope(OpenAI(), auto_report=False)

client.chat.create(...)

# Generate whenever you want
client.report()

# Or access session data directly
print(client.session.total_input_tokens)
print(client.session.total_cost_usd)
print(client.session.total_tokens_saved)
```

---

## Supported Models (for cost calculation)

| Model             | Input (per 1M tokens) |
| ----------------- | --------------------- |
| GPT-4o            | $2.50                 |
| GPT-4o mini       | $0.15                 |
| GPT-4 Turbo       | $10.00                |
| Claude 3.5 Sonnet | $3.00                 |
| Claude 3 Haiku    | $0.25                 |
| Gemini 1.5 Pro    | $1.25                 |

Cost calculation is approximate for non-OpenAI models (~95% accurate for Claude, ~90% for Gemini).

---

## Requirements

- Python 3.10+
- `tiktoken` (installed automatically)
- `openai` (optional, install with `pip install llm-tokenscope[openai]`)

---

## Links

- **GitHub:** https://github.com/DevelopedBy-Siva/token-scope
- **Live API:** https://token-scope.onrender.com
- **Issues:** https://github.com/DevelopedBy-Siva/token-scope/issues
