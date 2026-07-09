# pyright: reportMissingImports=false
import os
from typing import Any
import torch
from transformers import AutoTokenizer

'''
This script loads Qwen3.6-27B directly into memory using vLLM in pipeline mode.
'''

SCRATCH = os.getenv('CINECA_SCRATCH', './')
# Impostiamo la cache offline per i nodi di calcolo
os.environ["HF_HUB_OFFLINE"] = "1"

# Snapshot esatto del modello in Scratch
DEFAULT_MODEL_PATH = "/hf_cache/hub/models--Qwen--Qwen3.6-27B/snapshots/6a9e13bd6fc8f0983b9b99948120bc37f49c13e9"

_LLM_CACHE: dict[str, Any] = {}
_TOKENIZER_CACHE: dict[str, Any] = {}

def _get_or_create_llm(model_path: str) -> Any:
    """Carica il motore vLLM distribuendolo sulle GPU disponibili."""
    try:
        from vllm import LLM
    except ImportError as exc:
        raise ImportError("vLLM non trovato nell'ambiente.")

    # Se viene passato un ID generico, usiamo il path assoluto interno al container
    if not model_path.startswith("/"):
        model_path = DEFAULT_MODEL_PATH

    if model_path not in _LLM_CACHE:
        # Conta quante GPU ti ha assegnato Slurm (saranno 4)
        tensor_parallel_size = torch.cuda.device_count() if torch.cuda.is_available() else 1
        print(f"--> Caricamento modello in corso su {tensor_parallel_size} GPU in Tensor Parallel...")
        
        _LLM_CACHE[model_path] = LLM(
            model=model_path,
            tensor_parallel_size=tensor_parallel_size,
            trust_remote_code=True
        )
    return _LLM_CACHE[model_path]

def _get_or_create_tokenizer(model_path: str) -> Any:
    if not model_path.startswith("/"):
        model_path = DEFAULT_MODEL_PATH
    if model_path not in _TOKENIZER_CACHE:
        _TOKENIZER_CACHE[model_path] = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    return _TOKENIZER_CACHE[model_path]

def _format_chat_prompts(prompts: list[str], model_path: str) -> list[str]:
    tokenizer = _get_or_create_tokenizer(model_path)
    chat_prompts: list[str] = []
    for prompt in prompts:
        messages = [{"role": "user", "content": prompt}]
        try:
            chat_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        except Exception:
            chat_text = prompt
        chat_prompts.append(chat_text)
    return chat_prompts

def query_qwen_batch(prompts: list[str], model_path: str = DEFAULT_MODEL_PATH, max_new_tokens: int = 256, temperature: float = 0.2) -> list[str]:
    try:
        from vllm import SamplingParams
    except ImportError as exc:
        raise ImportError("vLLM non trovato.")

    if not prompts:
        return []

    llm = _get_or_create_llm(model_path)
    formatted_prompts = _format_chat_prompts(prompts, model_path)
    
    # Abilitiamo il parsing del ragionamento nativo di Qwen 3.6
    sampling_params = SamplingParams(
        temperature=temperature,
        top_p=0.95,
        max_tokens=max_new_tokens,
        repetition_penalty=1.05,
    )

    outputs = llm.generate(formatted_prompts, sampling_params)
    return [output.outputs[0].text.strip() for output in outputs]

def query_qwen(prompt: str, model_path: str = DEFAULT_MODEL_PATH, max_new_tokens: int = 256, temperature: float = 0.2) -> str:
    responses = query_qwen_batch(prompts=[prompt], model_path=model_path, max_new_tokens=max_new_tokens, temperature=temperature)
    return responses[0] if responses else ""