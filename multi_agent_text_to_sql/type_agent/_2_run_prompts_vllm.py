from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import datetime
import torch
from transformers import AutoTokenizer
from vllm import LLM, SamplingParams


SCRATCH = os.getenv("CINECA_SCRATCH", "./")
WORK = SCRATCH

PROMPTS_PATH = Path(__file__).resolve().parent / "_1_generated_prompts_by_id.json"
DEFAULT_MAX_TOKENS = int(os.getenv("VLLM_MAX_TOKENS", "8192"))
DEFAULT_TEMPERATURE = float(os.getenv("VLLM_TEMPERATURE", "0.0"))
ALLOWED_DATA_TYPES = {"INTEGER", "REAL", "TEXT", "DATE", "DATETIME"}


def compute_gpu_memory_utilization_from_free(target_free_ratio: float = 0.7) -> float:
    if not torch.cuda.is_available():
        return 0.9

    ratios = []
    for i in range(torch.cuda.device_count()):
        try:
            free_b, total_b = torch.cuda.mem_get_info(i)
            if total_b > 0:
                ratios.append(float(free_b) / float(total_b))
        except Exception:
            ratios.append(0.5)

    if not ratios:
        return 0.7

    return max(0.1, min(0.9, min(ratios) * float(target_free_ratio)))


def load_prompts_by_id(path: Path) -> list[tuple[str, str, str]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, list):
        raise ValueError(
            "Il file dei prompt deve essere una lista di record nel formato "
            "{'question_id': ..., 'db_id': ..., 'prompt': ...}."
        )

    records: list[tuple[str, str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        question_id = item.get("question_id")
        db_id = item.get("db_id")
        prompt = item.get("prompt")
        if not question_id or not db_id or not prompt:
            continue

        records.append((str(question_id), str(db_id), str(prompt)))

    def sort_key(item: tuple[str, str, str]) -> tuple[int, str]:
        key = item[0]
        if str(key).isdigit():
            return (0, f"{int(key):012d}")
        return (1, str(key))

    ordered = sorted(records, key=sort_key)
    return [(qid, dbid, prm) for qid, dbid, prm in ordered if prm.strip()]


def try_parse_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None


def extract_first_json_object(text: str) -> dict | None:
    """Estrae il primo oggetto JSON valido da una stringa libera."""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def normalize_types_payload(parsed: dict | None) -> dict[str, list[str]]:
    """
    Normalizza l'output in formato rigido:
    {"types_to_use": [...]} con soli tipi ammessi.
    """
    if not isinstance(parsed, dict):
        return {"types_to_use": []}

    raw_types = parsed.get("types_to_use")
    if not isinstance(raw_types, list):
        return {"types_to_use": []}

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_types:
        normalized = str(item).upper().strip()
        if normalized in ALLOWED_DATA_TYPES and normalized not in seen:
            cleaned.append(normalized)
            seen.add(normalized)

    return {"types_to_use": cleaned}


def build_chat_prompts(tokenizer, prompt_texts: list[str]) -> list[str]:
    chat_prompts: list[str] = []
    for prompt_text in prompt_texts:
        messages = [
            {"role": "user", "content": prompt_text},
        ]
        chat_prompts.append(
            tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        )
    return chat_prompts


def main() -> int:
    model_path = os.getenv("MODEL_PATH")
    if not model_path:
        print("ERRORE: Variabile d'ambiente MODEL_PATH obbligatoria mancante!")
        return 1

    if not PROMPTS_PATH.exists():
        print(f"ERRORE: File prompt non trovato: {PROMPTS_PATH}")
        return 1

    prompts_by_id = load_prompts_by_id(PROMPTS_PATH)
    if not prompts_by_id:
        print("ERRORE: Nessun prompt valido trovato nel file input.")
        return 1

    model_name = os.path.basename(model_path.rstrip("/\\"))
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"_2_vllm_type_selection_agent_outputs.json"

    print(f"Model: {model_path}")
    print(f"Prompt file: {PROMPTS_PATH}")
    print(f"Prompt totali: {len(prompts_by_id)}")
    print("Batching: disabilitato (singola chiamata)")
    print(f"Output: {output_file}")

    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

    gpu_util = compute_gpu_memory_utilization_from_free(0.7)
    llm = LLM(
        model=model_path,
        tensor_parallel_size=1,
        dtype="bfloat16",
        gpu_memory_utilization=gpu_util,
        max_model_len=4096,
        trust_remote_code=True,
    )

    sampling_params = SamplingParams(
        temperature=DEFAULT_TEMPERATURE,
        max_tokens=DEFAULT_MAX_TOKENS,
    )

    start = datetime.datetime.now()
    results: list[dict[str, object]] = []

    prompt_texts = [prompt for _, _, prompt in prompts_by_id]
    chat_prompts = build_chat_prompts(tokenizer, prompt_texts)

    #vediamo in tempo prima 
    start=datetime.datetime.now()
    outputs = llm.generate(chat_prompts, sampling_params)
    end=datetime.datetime.now()

    for out, (request_id, db_id, prompt_text) in zip(outputs, prompts_by_id):
        raw_text = out.outputs[0].text.strip() if out.outputs else ""
        parsed = try_parse_json(raw_text)
        if not isinstance(parsed, dict):
            parsed = extract_first_json_object(raw_text)
        cleaned = normalize_types_payload(parsed)

        results.append(
            {
                "question_id": request_id,
                "db_id": db_id,
                "prompt": prompt_text,
                "response": raw_text,
                "response_json": parsed,
                "cleaned_response_json": cleaned,
            }
        )

    print(f"Completati: {len(results)}/{len(prompts_by_id)}")
    print(f"Tempo totale: {(end - start).total_seconds():.2f} secondi")
    print(f"Tempo medio per prompt: {(end - start).total_seconds() / len(prompts_by_id):.2f} secondi")

    end = datetime.datetime.now()
    elapsed_s = (end - start).total_seconds()

    payload = {
        "meta": {
            "model_path": model_path,
            "model_name": model_name,
            "prompt_file": str(PROMPTS_PATH),
            "total_prompts": len(prompts_by_id),
            "batch_size": None,
            "temperature": DEFAULT_TEMPERATURE,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "started_at": start.isoformat(),
            "ended_at": end.isoformat(),
            "elapsed_seconds": elapsed_s,
        },
        "results": results,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\nFatto. File salvato: {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
