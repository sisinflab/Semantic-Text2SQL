from __future__ import annotations

import sys
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Importazione dei moduli di validazione e di sistema
from atlas_rag.llm_generator.format.validate_json_output import (
    fix_triple_extraction_response,
    validate_output,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
TEXT_TO_SQL_ROOT = ROOT_DIR.parent
GRAPH_DECORATION_ROOT = TEXT_TO_SQL_ROOT / "graph_decoration"
GRAPH_DECORATION_SCRIPT_DIR = GRAPH_DECORATION_ROOT / "script"

if str(GRAPH_DECORATION_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(GRAPH_DECORATION_SCRIPT_DIR))

from _0_generator import DEFAULT_MODEL_PATH, query_qwen_batch  # noqa: E402

def sanitize_llm_json_response(response_text: str) -> str:
    """
    Rimuove tutto il testo fino al tag </think> (incluso) e poi 
    estrae il blocco JSON presente nel resto della stringa.
    """
    if not response_text:
        return "[]"

    # 1. Taglia tutto ciò che precede o include </think>
    if "</think>" in response_text:
        _, content = response_text.split("</think>", 1)
    else:
        content = response_text

    # 2. Estrae l'array JSON dalla parte rimanente
    match = re.search(r'\[.*\]', content, re.DOTALL)
    
    if not match:
        return "[]"
    
    json_str = match.group(0)

    # 3. Parsing e pulizia
    try:
        data = json.loads(json_str)
        if isinstance(data, dict):
            data = [data]
        return json.dumps(data, ensure_ascii=False)
    except json.JSONDecodeError:
        try:
            fixed_quotes = json_str.replace("'", '"')
            data = json.loads(fixed_quotes)
            return json.dumps(data, ensure_ascii=False)
        except Exception:
            return "[]"

@dataclass
class LocalGenerationConfig:
    max_tokens: int = 8192
    temperature: float = 0.7
    repetition_penalty: float | None = None

class LocalQwenGenerator:
    """Adattatore per utilizzare i generatori di graph_decoration in AutoKG."""

    def __init__(
        self,
        model_name: str = "Qwen2.5-Coder-7B-Instruct",
        model_path: str | None = None,
        max_workers: int = 8,
        default_config: LocalGenerationConfig | None = None,
    ) -> None:
        self.model_name = model_name
        self.model_path = model_path or DEFAULT_MODEL_PATH
        self.max_workers = max_workers
        self.config = default_config if default_config is not None else LocalGenerationConfig()

    def _messages_to_prompt(self, messages: list[dict[str, Any]]) -> str:
        sections = []
        for message in messages:
            role = str(message.get("role", "user")).upper()
            content = str(message.get("content", "")).strip()
            if content:
                sections.append(f"{role}:\n{content}")
        return "\n\n".join(sections)

    def generate_response(
        self,
        batch_messages,
        config: LocalGenerationConfig | None = None,
        **kwargs,
    ):
        if config is None:
            config = deepcopy(self.config)
            # Override da kwargs se presenti
            config.max_tokens = kwargs.get("max_new_tokens", config.max_tokens)
            config.temperature = kwargs.get("temperature", config.temperature)

        is_batch = isinstance(batch_messages[0], list)
        prompts = [self._messages_to_prompt(m) for m in (batch_messages if is_batch else [batch_messages])]
        
        # Esecuzione generazione
        outputs = query_qwen_batch(
            prompts=prompts,
            model_path=self.model_path,
            max_new_tokens=config.max_tokens,
            temperature=config.temperature,
        )
        print(f"[DEBUG RAW OUTPUT]: {outputs}")
        print("\n\n_________________________________________________________\n\n")
        # Sanitizzazione dell'output (Fase fondamentale)
        cleaned_outputs = [sanitize_llm_json_response(out) for out in outputs]
        print("\n\n_________________________________________________________\n\n")
        print(f"[DEBUG CLEANED OUTPUT]: {cleaned_outputs}")
        print("\n\n_________________________________________________________\n\n")

        # Validazione finale
        validate_function = kwargs.get("validate_function")
        if validate_function:
            final_outputs = [validate_function(out, **kwargs) for out in cleaned_outputs]
            return final_outputs if is_batch else final_outputs[0]

        return cleaned_outputs if is_batch else cleaned_outputs[0]

    def triple_extraction(
        self,
        messages,
        result_schema,
        max_tokens=None,
        record=False,
        allow_empty=True,
        repetition_penalty=None,
    ):
        messages = [messages] if isinstance(messages[0], dict) else messages
        return self.generate_response(
            messages,
            max_new_tokens=max_tokens,
            repetition_penalty=repetition_penalty,
            validate_function=validate_output,
            return_text_only=not record,
            schema=result_schema,
            fix_function=fix_triple_extraction_response,
            allow_empty=allow_empty,
        )