"""
Qwen2.5-0.5B-Instruct + LoRA intent service (Phase 3.8).

Design points
  * OPTIONAL and LAZY: torch / transformers / peft are imported only inside the real backend
    (_TorchQwenLoraBackend), never at import time. The backend runs normally without them.
  * DISABLED BY DEFAULT: NLP_ENABLED=false -> nothing is loaded, prediction returns 503.
  * BACKGROUND LOADING, SINGLE-FLIGHT: the model loads in one daemon thread started from the
    application lifespan. start_background_load() is idempotent and guarded by a lock, so
    concurrent callers can never trigger a duplicate load. Requests never start loads; they only
    read the state and get a "loading" error until the model is READY.
  * ONE INFERENCE AT A TIME: a lock serialises generation (CPU torch gains nothing from parallel
    generations of the same model); waiting longer than NLP_QUEUE_TIMEOUT_SECONDS -> "busy".
  * EVALUATION-IDENTICAL DECODING: unmerged adapter, chat template, greedy decoding,
    max_new_tokens=12, same generate() arguments as research/.../evaluate_lora.py.
  * SAFE ERRORS: exceptions raised to callers carry no internal details; the real cause (with
    stack trace) goes to the server log only.
  * ADVISORY ONLY: this module is intentionally not imported by chat, rides, riders, locations or
    any alerting code. A prediction never triggers an action.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional, Protocol

from app.nlp.intent_parsing import MAX_NEW_TOKENS, ParseStatus, build_prompt, parse_model_output

logger = logging.getLogger("convoyconnect.nlp")

DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
MODEL_ID = "Qwen2.5-0.5B-Instruct + LoRA (ConvoyConnect Phase 3.7)"


# --------------------------------------------------------------------------- errors
class NLPServiceError(Exception):
    """Base class. Messages are intentionally empty/generic - details go to the log only."""


class NLPDisabledError(NLPServiceError):
    pass


class NLPNotReadyError(NLPServiceError):
    """Model not started yet, or still loading."""


class NLPUnavailableError(NLPServiceError):
    """Model failed to load."""


class NLPBusyError(NLPServiceError):
    pass


class NLPInferenceError(NLPServiceError):
    pass


class AdapterNotFoundError(Exception):
    """Internal (load time only). Its message may contain a path and is only ever logged."""


class NLPState(str, Enum):
    DISABLED = "disabled"
    NOT_STARTED = "not_started"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"


# --------------------------------------------------------------------------- paths
def repo_root() -> Path:
    # <repo>/backend/app/nlp/qwen_lora_service.py -> parents[3] == <repo>   (independent of the CWD)
    return Path(__file__).resolve().parents[3]


def default_adapter_dir() -> Path:
    return repo_root() / "research" / "nlp" / "advanced_llm" / "models" / "lora_adapter"


def resolve_adapter_dir(configured: str = "") -> Path:
    """Empty -> the default location inside the repo. A relative path is resolved against the
    REPO ROOT (never the current working directory). An absolute path is used as given."""
    configured = (configured or "").strip()
    if not configured:
        return default_adapter_dir()
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = repo_root() / path
    return path.resolve()


_WEIGHT_FILES = ("adapter_model.safetensors", "adapter_model.bin")


def validate_adapter_dir(path: Path) -> None:
    if not path.is_dir():
        raise AdapterNotFoundError(f"adapter directory not found: {path}")
    if not (path / "adapter_config.json").is_file():
        raise AdapterNotFoundError(f"adapter_config.json missing in: {path}")
    if not any((path / name).is_file() for name in _WEIGHT_FILES):
        raise AdapterNotFoundError(f"adapter weights ({' / '.join(_WEIGHT_FILES)}) missing in: {path}")


# --------------------------------------------------------------------------- results / backend protocol
@dataclass(frozen=True)
class PredictionResult:
    intent: Optional[str]
    status: str
    raw_output: str
    latency_ms: float

    @property
    def succeeded(self) -> bool:
        return self.intent is not None and self.status in ParseStatus.SUCCESS


class GenerationBackend(Protocol):
    def generate(self, user_prompt: str, max_new_tokens: int) -> str: ...


Loader = Callable[[Path, str, bool], GenerationBackend]


class _TorchQwenLoraBackend:
    """The real model. CPU only. torch / transformers / peft are imported here, lazily."""

    def __init__(self, adapter_dir: Path, base_model: str, local_files_only: bool):
        import torch  # optional dependency
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._torch = torch
        tokenizer_source = adapter_dir if (adapter_dir / "tokenizer_config.json").is_file() else base_model
        tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_source), local_files_only=local_files_only)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        tokenizer.padding_side = "left"
        base = AutoModelForCausalLM.from_pretrained(base_model, dtype=torch.float32, local_files_only=local_files_only)
        model = PeftModel.from_pretrained(base, str(adapter_dir))  # NOT merged: matches the evaluated setup
        model.to(torch.device("cpu"))
        model.eval()
        self._tokenizer = tokenizer
        self._model = model

    def generate(self, user_prompt: str, max_new_tokens: int) -> str:
        tok = self._tokenizer
        chat_text = tok.apply_chat_template(
            [{"role": "user", "content": user_prompt}], tokenize=False, add_generation_prompt=True
        )
        enc = tok([chat_text], return_tensors="pt", padding=True, truncation=True, max_length=512)
        with self._torch.no_grad():
            out = self._model.generate(
                **enc,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=tok.pad_token_id or tok.eos_token_id,
            )
        generated = out[0][enc["input_ids"].shape[1]:]
        return tok.decode(generated, skip_special_tokens=True)


def _load_torch_backend(adapter_dir: Path, base_model: str, local_files_only: bool) -> GenerationBackend:
    return _TorchQwenLoraBackend(adapter_dir, base_model, local_files_only)


# --------------------------------------------------------------------------- service
class QwenLoraIntentService:
    def __init__(
        self,
        *,
        enabled: bool,
        adapter_dir: Path,
        base_model: str = DEFAULT_BASE_MODEL,
        local_files_only: bool = False,
        queue_timeout_seconds: float = 10.0,
        return_raw_output: bool = False,
        loader: Optional[Loader] = None,
    ):
        self._enabled = bool(enabled)
        self._adapter_dir = Path(adapter_dir)
        self._base_model = base_model
        self._local_files_only = local_files_only
        self._queue_timeout = max(0.0, float(queue_timeout_seconds))
        self.return_raw_output = bool(return_raw_output)
        self._loader: Loader = loader or _load_torch_backend

        self._state = NLPState.NOT_STARTED if self._enabled else NLPState.DISABLED
        self._state_lock = threading.Lock()   # guards state transitions (single-flight loading)
        self._infer_lock = threading.Lock()   # one generation at a time
        self._backend: Optional[GenerationBackend] = None
        self._load_thread: Optional[threading.Thread] = None

    # ---- introspection (never exposes paths, errors or exception text)
    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def state(self) -> NLPState:
        return self._state

    def status(self) -> dict:
        state = self._state
        return {"enabled": self._enabled, "state": state.value, "ready": state is NLPState.READY, "model": MODEL_ID}

    # ---- loading
    def start_background_load(self) -> bool:
        """Start loading in a background thread. Returns True only for the call that started it.
        Idempotent and thread-safe: disabled / already started / loading / ready / failed -> False."""
        with self._state_lock:
            if self._state is not NLPState.NOT_STARTED:
                return False
            self._state = NLPState.LOADING
        thread = threading.Thread(target=self._load, name="nlp-model-loader", daemon=True)
        self._load_thread = thread
        thread.start()
        return True

    def join_loader(self, timeout: Optional[float] = None) -> None:
        thread = self._load_thread
        if thread is not None:
            thread.join(timeout)

    def _set_state(self, state: NLPState) -> None:
        with self._state_lock:
            self._state = state

    def _load(self) -> None:
        started = time.perf_counter()
        try:
            validate_adapter_dir(self._adapter_dir)
            backend = self._loader(self._adapter_dir, self._base_model, self._local_files_only)
        except AdapterNotFoundError as exc:
            logger.error("NLP model not loaded: %s", exc)
            self._set_state(NLPState.FAILED)
        except ImportError as exc:
            logger.error(
                "NLP model not loaded: optional NLP dependencies are missing (%s). "
                "Install them with: pip install -r requirements-nlp.txt", exc
            )
            self._set_state(NLPState.FAILED)
        except Exception:
            logger.exception("NLP model failed to load")
            self._set_state(NLPState.FAILED)
        else:
            with self._state_lock:
                self._backend = backend
                self._state = NLPState.READY
            logger.info("NLP model ready (loaded in %.1fs)", time.perf_counter() - started)

    # ---- inference
    def predict(self, text: str) -> PredictionResult:
        state = self._state
        if state is NLPState.DISABLED:
            raise NLPDisabledError()
        if state in (NLPState.NOT_STARTED, NLPState.LOADING):
            raise NLPNotReadyError()
        if state is NLPState.FAILED:
            raise NLPUnavailableError()

        if not self._infer_lock.acquire(timeout=self._queue_timeout):
            logger.warning("NLP request rejected: model busy (queue timeout %.1fs)", self._queue_timeout)
            raise NLPBusyError()
        try:
            started = time.perf_counter()
            raw = str(self._backend.generate(build_prompt(text), MAX_NEW_TOKENS))
            latency_ms = (time.perf_counter() - started) * 1000.0
        except Exception:
            logger.exception("NLP inference failed")
            raise NLPInferenceError() from None
        finally:
            self._infer_lock.release()

        parsed = parse_model_output(raw)
        # The rider's message text is deliberately NOT logged - only its length.
        logger.info("nlp.predict parse_status=%s latency_ms=%.0f text_chars=%d", parsed.status, latency_ms, len(text))
        return PredictionResult(parsed.intent, parsed.status, raw, latency_ms)


@lru_cache(maxsize=1)
def get_nlp_service() -> QwenLoraIntentService:
    """Process-wide singleton, also used as a FastAPI dependency (override it in tests)."""
    from app.core.config import get_settings  # imported lazily so this module stays importable without pydantic

    s = get_settings()
    return QwenLoraIntentService(
        enabled=s.NLP_ENABLED,
        adapter_dir=resolve_adapter_dir(s.NLP_ADAPTER_DIR),
        base_model=s.NLP_BASE_MODEL,
        local_files_only=s.NLP_LOCAL_FILES_ONLY,
        queue_timeout_seconds=s.NLP_QUEUE_TIMEOUT_SECONDS,
        return_raw_output=s.NLP_RETURN_RAW_OUTPUT,
    )
