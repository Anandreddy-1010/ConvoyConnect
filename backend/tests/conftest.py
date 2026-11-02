"""Backend test configuration (applies to the whole suite)."""
import os

# Hermetic tests: never load the real model, whatever the developer's shell or .env contains.
# (The real-model test builds its own service and is opt-in via RUN_MODEL_TESTS=1.)
os.environ["NLP_ENABLED"] = "false"
os.environ["NLP_RETURN_RAW_OUTPUT"] = "false"


def pytest_configure(config):
    config.addinivalue_line("markers", "model: loads the real Qwen+LoRA model (opt-in: set RUN_MODEL_TESTS=1)")
