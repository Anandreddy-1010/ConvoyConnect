import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
ADAPTER = Path("research/nlp/advanced_llm/models/lora_adapter")

if not ADAPTER.is_dir():
    raise FileNotFoundError(f"Adapter not found: {ADAPTER.resolve()}")

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(str(ADAPTER))

print("Loading base model on CPU...")
start = time.perf_counter()

base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.float32,
    device_map="cpu",
)

model = PeftModel.from_pretrained(base_model, str(ADAPTER))
model.eval()

print(f"Model loaded in {time.perf_counter() - start:.1f} seconds.")

message = "We are running low on fuel. We need to stop soon."
prompt = (
    "Classify the rider message into exactly one of these intents: "
    "REFUELING, REST_BREAK, FOOD_BREAK, VEHICLE_PROBLEM, TRAFFIC_DELAY, "
    "FALLING_BEHIND, LOST, REGROUP_REQUEST, DESTINATION_CHANGE, "
    "EMERGENCY, STATUS_UPDATE, GENERAL.\n"
    f"Message: {message}\nIntent:"
)

inputs = tokenizer(prompt, return_tensors="pt")
start = time.perf_counter()

with torch.inference_mode():
    outputs = model.generate(
        **inputs,
        max_new_tokens=12,
        do_sample=False,
        pad_token_id=tokenizer.eos_token_id,
    )

generated = outputs[0][inputs["input_ids"].shape[1]:]
prediction = tokenizer.decode(generated, skip_special_tokens=True).strip()

print(f"\nInput: {message}")
print(f"Raw model output: {prediction}")
print(f"Inference time: {time.perf_counter() - start:.2f} seconds")
