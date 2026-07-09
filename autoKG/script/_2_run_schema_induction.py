import argparse
import os
import sys
import json
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from atlas_rag.kg_construction.triple_config import ProcessingConfig
from atlas_rag.kg_construction.triple_extraction import KnowledgeGraphExtractor

from _0_generator_adapter import DEFAULT_MODEL_PATH, LocalQwenGenerator


DEFAULT_INPUT_DIR = ROOT_DIR / "extraction_input"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "generated"
DEFAULT_PROMPT_PATH = ROOT_DIR / "custom_extraction" / "custom_benchmark" / "custom_prompt.json"
DEFAULT_SCHEMA_PATH = ROOT_DIR / "custom_extraction" / "custom_benchmark" / "custom_schema.json"
DEFAULT_CACHE_DIR = ROOT_DIR / ".cache" / "huggingface"


def sanitize_llm_json_response(response_text: str) -> str:
    """
    Sanitizza e normalizza l'output del modello per garantire che sia sempre 
    un array JSON piatto composto unicamente da oggetti (dizionari).
    """
    if not response_text:
        return response_text
    
    cleaned = response_text.strip()
    
    # 1. Rimuove eventuali blocchi di codice markdown (```json ... ```)
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9]*\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except Exception:
        # Se fallisce, tenta di convertire gli apici singoli in doppi per recuperare la struttura
        try:
            fixed_quotes = cleaned.replace("'", '"')
            data = json.loads(fixed_quotes)
        except Exception:
            return response_text

    # 2. Se l'output è una lista, appiattisce le liste annidate e rimuove elementi non-dizionario
    if isinstance(data, list):
        flat_list = []
        for item in data:
            if isinstance(item, list):
                # Caso di lista annidata (es. [['long text'], {'subject': ...}] o [[{'subject': ...}]])
                for sub_item in item:
                    if isinstance(sub_item, dict):
                        flat_list.append(sub_item)
            elif isinstance(item, dict):
                flat_list.append(item)
        
        # Riconverte la lista piatta e pulita in stringa JSON standard
        return json.dumps(flat_list, ensure_ascii=False)
    
    return response_text


def apply_monkeypatch(generator_instance):
    """
    Intercetta i metodi di generazione di LocalQwenGenerator per sanificare
    automaticamente l'output prima che venga digerito da AutoKG.
    """
    def wrap_generation_method(original_method):
        def wrapper(*args, **kwargs):
            result = original_method(*args, **kwargs)
            if isinstance(result, str):
                return sanitize_llm_json_response(result)
            elif isinstance(result, list):
                return [sanitize_llm_json_response(r) if isinstance(r, str) else r for r in result]
            return result
        return wrapper

    methods_to_patch = ['generate', 'query', 'predict', '__call__', 'generate_triples']
    patched_count = 0
    for method_name in methods_to_patch:
        if hasattr(generator_instance, method_name):
            original = getattr(generator_instance, method_name)
            setattr(generator_instance, method_name, wrap_generation_method(original))
            patched_count += 1
            
    if patched_count > 0:
        print(f"[monkeypatch] Intercettati e blindati {patched_count} metodi di generazione in LocalQwenGenerator.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run AutoKG extraction and schema induction using graph_decoration's _0_generator."
    )
    parser.add_argument(
        "--keyword",
        required=True,
        help="Filename prefix to match inside extraction_input, e.g. california_schools",
    )
    parser.add_argument(
        "--model",
        default="Qwen2.5-Coder-7B-Instruct",
        help="Logical model name to label the run output.",
    )
    parser.add_argument(
        "--model-path",
        default=DEFAULT_MODEL_PATH,
        help="Local model path passed to graph_decoration/script/_0_generator.py",
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_DIR),
        help="Directory containing extraction-ready JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where generated outputs will be written.",
    )
    parser.add_argument(
        "--batch-size-triple",
        type=int,
        default=16,
        help="Batch size for triple extraction.",
    )
    parser.add_argument(
        "--batch-size-concept",
        type=int,
        default=16,
        help="Batch size for concept generation.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=8192,
        help="Maximum generation length.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=5,
        help="Maximum number of workers passed through the pipeline.",
    )
    return parser.parse_args()


def ensure_local_cache_env() -> None:
    os.environ.setdefault("HF_HOME", str(DEFAULT_CACHE_DIR))
    os.environ.setdefault("HF_DATASETS_CACHE", str(DEFAULT_CACHE_DIR / "datasets"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(DEFAULT_CACHE_DIR / "transformers"))



def main() -> None:
    args = parse_args()
    ensure_local_cache_env()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    
    # Questo è il nome che TU vuoi usare per la cartella
    model_dir_name = args.model.split("/")[-1] 
    run_output_dir = output_dir / model_dir_name / args.keyword

    triple_generator = LocalQwenGenerator(
        model_name=args.model,
        model_path=args.model_path,
        max_workers=args.max_workers,
    )

    apply_monkeypatch(triple_generator)

    kg_extraction_config = ProcessingConfig(
        model_path=args.model_path,
        data_directory=str(input_dir),
        filename_pattern=args.keyword,
        batch_size_triple=args.batch_size_triple,
        batch_size_concept=args.batch_size_concept,
        output_directory=str(run_output_dir),
        max_new_tokens=args.max_new_tokens,
        max_workers=args.max_workers,
        remove_doc_spaces=True,
        include_concept=True,
        triple_extraction_prompt_path=str(DEFAULT_PROMPT_PATH),
        triple_extraction_schema_path=str(DEFAULT_SCHEMA_PATH),
    )

    # 1. Inizializziamo l'estrattore
    kg_extractor = KnowledgeGraphExtractor(model=triple_generator, config=kg_extraction_config)

    # 2. FORZATURA DEL NOME: 
    # Se la classe interna ha un attributo 'model_name' o 'model' nella sua config, sovrascriviamolo qui.
    # Controlla se l'oggetto ha questi attributi:
    if hasattr(kg_extractor, 'model_name'):
        kg_extractor.model_name = args.model
    elif hasattr(kg_extractor.config, 'model_name'):
        kg_extractor.config.model_name = args.model
    
    # 3. Procedi con l'esecuzione
    kg_extractor.run_extraction()
    kg_extractor.convert_json_to_csv()
    kg_extractor.generate_concept_csv_temp()
    kg_extractor.create_concept_csv()

    print(f"Completed extraction and schema induction for '{args.keyword}'.")
    print(f"Model: {args.model}")
    print(f"Model path: {args.model_path}")
    print(f"Outputs written to: {run_output_dir}")


if __name__ == "__main__":
    main()