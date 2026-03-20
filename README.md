# TokenScope

**Profile your LLM payloads. Find the waste. Cut the cost.**

```bash
pip install llm-tokenscope
```

Your LLM bill isn't just your prompt — it's JSON. Keys, nested objects, tool schemas, conversation history, metadata, context chunks. By the time it hits the API, your code has assembled something expensive that you've never actually looked at.

TokenScope shows you which fields are burning your budget, detects structural waste, and generates an HTML report after your session.

---

## SDK

Wrap your existing client. Zero changes to your app logic.

### OpenAI / OpenAI-compatible

```python
from tokenscope import TokenScope
from openai import OpenAI

with TokenScope.wrap(OpenAI()) as client:
    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
    )
# HTML report written to ./reports/
```

Works with any OpenAI-compatible API — OpenAI, Together, Anyscale, Ollama, anything.

```python
# Ollama example — cost shows $0.00, all other profiling works normally
with TokenScope.wrap(OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")) as client:
    client.chat.completions.create(model="llama3", messages=[...])
```

### Anthropic SDK

```python
import anthropic
from tokenscope import TokenScope

with TokenScope.wrap(anthropic.Anthropic()) as client:
    client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello"}],
    )
```

### LangChain

```python
from tokenscope import TokenScope
from langchain_openai import ChatOpenAI

handler = TokenScope.langchain_handler()

llm = ChatOpenAI(model="gpt-4o", callbacks=[handler])
llm.invoke("Hello")

handler.scope.report()  # write report manually
```

Or as a context manager:

```python
with TokenScope.langchain_handler() as handler:
    chain.invoke({"input": "..."}, config={"callbacks": [handler]})
```

### Attach extra context for analysis

Profile data that's generated in your app but stripped before the API call:

```python
with TokenScope.wrap(OpenAI()) as client:
    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Summarize"}],
        extra_data={"retrieved_chunks": chunks},  # stripped before API call, included in leak analysis
    )
```

### Manual report control

```python
scope = TokenScope()
client = scope.wrap_openai(OpenAI())

client.chat.completions.create(...)
client.chat.completions.create(...)

print(scope.session.total_input_tokens)
print(scope.session.total_cost_usd)
print(scope.session.total_tokens_saveable)

scope.report()  # write report whenever you want
```

---

## The Report

After your session, a self-contained HTML report is written to `./reports/tokenscope_<timestamp>.html`.

**Session summary** — total calls, input tokens, output tokens, analyzed tokens, total cost, tokens saveable.

**Per call** — top fields by token cost, detected cost leaks with severity and savings estimate, cost and duration.

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

## REST API

**Base URL:** `https://token-scope.onrender.com`

### `POST /api/v1/analyze`

```bash
curl -X POST https://token-scope.onrender.com/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "model": "gpt-4o",
      "messages": [{"role": "user", "content": "Hello"}]
    },
    "model_id": "gpt-4o",
    "requests_per_day": 100
  }'
```

**Response includes:**

- `total_tokens` — exact tiktoken count
- `top_fields` — top 5 most expensive leaf fields
- `leaks` — detected cost leaks with severity and savings estimate
- `optimization` — cleaned payload with tokens saved
- `cost` — per-request cost breakdown
- `monthly` — projected monthly cost at given request volume
- `all_models` — cost comparison across all supported models

### `GET /api/v1/health`

```json
{ "status": "ok", "version": "0.2.0" }
```

---

## Supported Models

| Model             | Provider  | Input (per 1M) | Output (per 1M) |
| ----------------- | --------- | -------------- | --------------- |
| GPT-4o            | OpenAI    | $2.50          | $10.00          |
| GPT-4o mini       | OpenAI    | $0.15          | $0.60           |
| GPT-4 Turbo       | OpenAI    | $10.00         | $30.00          |
| o3                | OpenAI    | $10.00         | $40.00          |
| o3-mini           | OpenAI    | $1.10          | $4.40           |
| Claude 3.7 Sonnet | Anthropic | $3.00          | $15.00          |
| Claude 3.5 Sonnet | Anthropic | $3.00          | $15.00          |
| Claude 3.5 Haiku  | Anthropic | $0.80          | $4.00           |
| Claude 3 Haiku    | Anthropic | $0.25          | $1.25           |
| Gemini 2.0 Flash  | Google    | $0.10          | $0.40           |
| Gemini 1.5 Pro    | Google    | $1.25          | $5.00           |
| Gemini 1.5 Flash  | Google    | $0.075         | $0.30           |

Pricing is stored in `src/tokenscope/prices.json` and loaded at runtime. A warning is shown if the file is more than 60 days old. Unknown models show `$0.00` — all other profiling works normally.

---

## How Token Counting Works

TokenScope uses `tiktoken` — OpenAI's tokenizer. Token counting is deterministic math, no API calls, no data leaves your machine.

**Accuracy:** Exact for OpenAI models. ~95% for Claude. ~90% for Gemini.

**Two token counts per call:**

- **Input tokens** — tiktoken count of what was actually sent to the API
- **Analyzed tokens** — full payload count including `extra_data`. What leak detection runs against.

Per-field attribution is proportionally estimated. The session total is always exact.

---

## Project Structure

```
token-scope/
├── pyproject.toml
├── Dockerfile
│
├── src/
│   └── tokenscope/
│       ├── __init__.py          ← public API: TokenScope, TokenScopeSession
│       ├── client.py            ← OpenAI wrapper, Anthropic wrapper, LangChain handler
│       ├── reporter.py          ← writes reports/ HTML
│       ├── prices.json          ← pricing data, update without touching code
│       └── core/
│           ├── tokenizer.py     ← tiktoken wrapper, per-field attribution
│           ├── parser.py        ← JSON tree walker
│           ├── leak_detector.py ← 6-rule waste detection
│           ├── payload_optimizer.py
│           └── calculator.py   ← token counts → dollar costs
│
├── api/
│   ├── main.py                  ← FastAPI app
│   ├── routes.py                ← /analyze, /health
│   └── models.py                ← Pydantic request/response models
│
└── tests/
    ├── test_calculator.py
    ├── test_leak_detector.py
    ├── test_payload_optimizer.py
    ├── test_tokenizer_parser.py
    └── test_api.py
```

---

## Running Locally

```bash
git clone https://github.com/DevelopedBy-Siva/token-scope
cd token-scope

# SDK only
pip install -e .

# API
pip install -e ".[api]"
uvicorn api.main:app --reload

# Tests
pip install -e ".[dev]"
pytest
```

## Docker

```bash
docker build -t tokenscope .
docker run -p 8000:8000 tokenscope
```
