# app/nlp

## Implemented (Phase 3.8): optional intent prediction

The Phase 3.7 model - **Qwen2.5-0.5B-Instruct + LoRA adapter** (rank 8, trained 2 epochs on the
Phase 3.1 synthetic dataset) - is available through `POST /api/v1/nlp/predict`.

| File | Role |
|---|---|
| `intent_parsing.py` | The 12 labels, the training prompt, and the output parser. Standard library only. |
| `qwen_lora_service.py` | Adapter path resolution, background loading, single-inference lock, CPU generation. torch / transformers / peft are imported **lazily**, only when the model loads. |
| `responses.py` | Safe client-facing error messages and the response payload builder (pure functions). |

Related files: `app/schemas/nlp.py`, `app/api/v1/endpoints/nlp.py`, `requirements-nlp.txt`.

### Enabling it

It is **off by default** (`NLP_ENABLED=false`): nothing is loaded and `/predict` answers 503. The
rest of the API is unaffected. To enable it:

1. Install the optional dependencies into the backend virtual environment:
   `pip install -r requirements-nlp.txt`
2. Start the backend with `NLP_ENABLED=true`. The model loads in a **background thread**; the
   server starts immediately. While loading, `/predict` answers 503 with `Retry-After`.
   `GET /api/v1/nlp/status` reports `disabled | not_started | loading | ready | failed`.

| Setting (env var / `.env`) | Default | Meaning |
|---|---|---|
| `NLP_ENABLED` | `false` | Load the model at startup (in the background). |
| `NLP_ADAPTER_DIR` | *(empty)* | Empty -> `research/nlp/advanced_llm/models/lora_adapter`, resolved from the source location (not the working directory). Relative values resolve against the repo root. |
| `NLP_BASE_MODEL` | `Qwen/Qwen2.5-0.5B-Instruct` | Base model (downloaded to the Hugging Face cache on first use). |
| `NLP_LOCAL_FILES_ONLY` | `false` | `true` -> never contact the Hugging Face Hub. |
| `NLP_QUEUE_TIMEOUT_SECONDS` | `10` | Max wait for the single inference slot before 503 "busy". |
| `NLP_RETURN_RAW_OUTPUT` | `false` | `true` -> include the model's raw text as `raw_output` (debugging only). |

### Behaviour and limits

- **Advisory only.** A prediction never triggers an alert, SOS, navigation or any other action, and
  chat/rides/riders/locations never call this package.
- **No confidence score.** The model generates text; that is not a calibrated probability.
- **Failed parsing is explicit**: `predicted_intent` is `null` and `parse_succeeded` is `false`
  (`invalid_label`, `empty_output` or `ambiguous_output`). It never falls back to `GENERAL`.
  In the Phase 3.7 evaluation, 4 of 420 replies were invented categories (not one of the 12 labels).
- **Trained on synthetic data.** Phase 3.4/3.7 showed that accuracy drops on naturalistic wording;
  treat predictions on real rider messages with caution.
- Errors returned to clients are fixed, generic messages; details (with stack traces) are only in the server log.

## Not implemented

`intent_classifier.py` and `entity_extractor.py` are **older Phase 2 placeholders** that predate the
trained model. They define a different, outdated intent set (`find_rider`, `report_delay`, ...) and a
mandatory `confidence` field, still raise `NotImplementedError`, and are **not used** by the new
service. They are intentionally left untouched.
