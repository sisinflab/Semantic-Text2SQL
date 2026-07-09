from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path

import torch
from vllm import LLM, SamplingParams

'''
This script takes the generated prompts from the previous step and runs them through a language model to get the selected semantic concepts for each question.
The concepts are read directly from the entry payload.
The output is saved in a JSON file with the original prompt, the raw response from the model, and a cleaned version of the response where only valid concepts are retained.
'''

SCRATCH = os.getenv("CINECA_SCRATCH", "./")
WORK = SCRATCH

PROMPTS_PATH = Path(__file__).resolve().parent / "_2.1_generated_semantic_prompts_by_id.json"
DEFAULT_MAX_TOKENS = int(os.getenv("VLLM_MAX_TOKENS", "8192"))
DEFAULT_TEMPERATURE = float(os.getenv("VLLM_TEMPERATURE", "0.0"))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# File di debug
DEBUG_FILE = Path(__file__).resolve().parent / f"_debug_prompt_analysis_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"


def estimate_token_length(text: str) -> int:
    """Stima approssimativa della lunghezza in token (1 token ~= 4 caratteri)."""
    return len(text) // 4


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


def load_prompts_payload(path: Path) -> list[dict]:
    """Carica l'intero file JSON preservando i dizionari originali."""
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, list):
        raise ValueError(
            "Il file dei prompt deve essere una lista di record."
        )

    valid_records = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        
        question_id = item.get("question_id")
        prompt = item.get("prompt")
        if question_id and prompt and prompt.strip():
            valid_records.append(item)

    # Ordina per question_id se numerico
    def sort_key(item: dict) -> tuple[int, str]:
        key = str(item.get("question_id", ""))
        if key.isdigit():
            return (0, f"{int(key):012d}")
        return (1, key)

    return sorted(valid_records, key=sort_key)


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


def normalize_concepts_payload(parsed: dict | None, available_concepts: list[str]) -> dict[str, list[str]]:
    """
    Normalizza l'output in formato rigido:
    {"concepts_to_use": [...]} con soli tipi ammessi.
    """
    if not isinstance(parsed, dict):
        return {"concepts_to_use": []}

    raw_concept = parsed.get("concepts_to_use")
    if not isinstance(raw_concept, list):
        return {"concepts_to_use": []}

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_concept:
        if len(cleaned) >= 8:
            break
        normalized = str(item).strip()
        if normalized in available_concepts and normalized not in seen:
            cleaned.append(normalized)
            seen.add(normalized)

    return {"concepts_to_use": cleaned}


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

    prompts_data = load_prompts_payload(PROMPTS_PATH)
    if not prompts_data:
        print("ERRORE: Nessun prompt valido trovato nel file input.")
        return 1

    model_name = os.path.basename(model_path.rstrip("/\\"))
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"_2.2_vllm_semantic_agent_outputs_{model_name}_{timestamp}.json"

    # ===== DEBUG: Informazioni modello e configurazione =====
    logger.info("="*80)
    logger.info("CONFIGURAZIONE MODELLO E PROMPT")
    logger.info("="*80)
    logger.info(f"Model: {model_path}")
    logger.info(f"Prompt file: {PROMPTS_PATH}")
    logger.info(f"Prompt totali: {len(prompts_data)}")
    logger.info(f"Temperature: {DEFAULT_TEMPERATURE}")
    logger.info(f"Max tokens (sampling): {DEFAULT_MAX_TOKENS}")
    logger.info(f"Output: {output_file}")

    # Analisi lunghezza dei prompt
    prompt_texts = [item["prompt"] for item in prompts_data]
    prompt_lengths = [len(p) for p in prompt_texts]
    token_estimates = [estimate_token_length(p) for p in prompt_texts]
    
    logger.info("="*80)
    logger.info("ANALISI LUNGHEZZA PROMPT")
    logger.info("="*80)
    logger.info(f"Lunghezza media prompt: {sum(prompt_lengths)//len(prompt_lengths)} caratteri")
    logger.info(f"Lunghezza max prompt: {max(prompt_lengths)} caratteri")
    logger.info(f"Lunghezza min prompt: {min(prompt_lengths)} caratteri")
    logger.info(f"Token stimati (media): {sum(token_estimates)//len(token_estimates)}")
    logger.info(f"Token stimati (max): {max(token_estimates)}")
    logger.info(f"⚠️  ATTENZIONE: Max model length è {DEFAULT_MAX_TOKENS}. Prompt che superano questa lunghezza causeranno errori!")
    
    num_over_limit = sum(1 for est in token_estimates if est > 3500)
    if num_over_limit > 0:
        logger.warning(f"⚠️  {num_over_limit} prompt potrebbero superare il limite (>3500 token)!")

    gpu_util = compute_gpu_memory_utilization_from_free(0.7)
    logger.info(f"GPU memory utilization: {gpu_util:.2%}")

    logger.info("="*80)
    logger.info("CARICAMENTO MODELLO...")
    logger.info("="*80)
    
    llm = LLM(
        model=model_path,
        tensor_parallel_size=4,
        dtype="bfloat16",
        gpu_memory_utilization=gpu_util,
        #max_model_len=4096,
        trust_remote_code=True,
    )
    tokenizer = llm.get_tokenizer()
    chat_prompt_texts = build_chat_prompts(tokenizer, prompt_texts)

    sampling_params = SamplingParams(
        temperature=DEFAULT_TEMPERATURE,
        max_tokens=DEFAULT_MAX_TOKENS,
    )

    logger.info("Modello caricato. Inizio elaborazione prompts...")

    start = datetime.datetime.now()
    results: list[dict[str, object]] = []
    debug_info: list[dict[str, object]] = []

    outputs = llm.generate(chat_prompt_texts, sampling_params)
    end = datetime.datetime.now()

    for idx, (out, item) in enumerate(zip(outputs, prompts_data)):
        raw_text = out.outputs[0].text.strip() if (hasattr(out, 'outputs') and out.outputs and len(out.outputs) > 0) else ""
        
        question_id = item.get("question_id")
        db_id = item.get("db_id")
        prompt_text = item.get("prompt")
        
        prompt_len = len(prompt_text)
        prompt_tokens = estimate_token_length(prompt_text)
        response_len = len(raw_text)
        
        debug_entry = {
            "question_id": question_id,
            "db_id": db_id,
            "prompt_length_chars": prompt_len,
            "prompt_tokens_estimated": prompt_tokens,
            "response_length_chars": response_len,
            "response_empty": response_len == 0,
            "response_sample": raw_text[:100] if raw_text else "(VUOTO)",
        }
        debug_info.append(debug_entry)
        
        if idx < 3 :
            logger.info(f"[{idx}] Question {question_id} ({db_id}): "
                        f"prompt={prompt_tokens} token, response={response_len} chars, "
                        f"empty={response_len==0}")
        
        parsed = try_parse_json(raw_text)
        if not isinstance(parsed, dict):
            parsed = extract_first_json_object(raw_text)

        # Recupera i concetti direttamente dall'entry corrente
        available_concepts = item.get("available_concepts", [])
        
        if len(available_concepts) == 0:
            logger.warning(f"⚠️  Nessun concetto disponibile trovato per question_id '{question_id}'! Verificare il file JSON di input.")

        cleaned = normalize_concepts_payload(parsed, available_concepts)

        results.append(
            {
                "question_id": question_id,
                "db_id": db_id,
                "prompt": prompt_text,
                "response": raw_text,
                "response_json": parsed,
                "cleaned_response_json": cleaned,
            }
        )

    # ===== SALVA FILE DEBUG =====
    empty_count = sum(1 for d in debug_info if d["response_empty"])
    logger.info("="*80)
    logger.info(f"RISULTATI: {len(results)} prompt elaborati, {empty_count} risposte vuote!")
    logger.info("="*80)
    
    avg_prompt_length = (sum(prompt_lengths) // len(prompt_lengths)) if prompt_lengths else 0
    max_prompt_length = max(prompt_lengths) if prompt_lengths else 0

    print(f"Tempo totale generazione: {(end - start).total_seconds():.2f} secondi")
    print(f"Tempo medio di esecuzione: {(((end - start).total_seconds()) / len(results)):.2f} secondi per prompt")

    with open(DEBUG_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "analysis": {
                "total_prompts": len(prompts_data),
                "debug_entries": len(debug_info),
                "empty_responses": empty_count,
                "avg_prompt_length": avg_prompt_length,
                "max_prompt_length": max_prompt_length,
                "model_config": {
                    "max_model_len": 4096,
                    "max_tokens": DEFAULT_MAX_TOKENS,
                    "temperature": DEFAULT_TEMPERATURE,
                }
            },
            "details": debug_info,
        }, f, ensure_ascii=False, indent=2)
    
    logger.info(f"File debug salvato: {DEBUG_FILE}")

    print(f"Completati: {len(results)}/{len(prompts_data)}")

    elapsed_s = (end - start).total_seconds()

    payload = {
        "meta": {
            "model_path": model_path,
            "model_name": model_name,
            "prompt_file": str(PROMPTS_PATH),
            "total_prompts": len(prompts_data),
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