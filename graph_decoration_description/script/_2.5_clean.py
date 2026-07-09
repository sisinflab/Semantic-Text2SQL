#take all the descriptions in ../descriptions and clean them by removing all the text above the </think>

import argparse
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DESCRIPTION_DIR = SCRIPT_DIR.parent / "descriptions"

for desc_file in DESCRIPTION_DIR.glob("*.txt"):
    with open(desc_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Rimuove tutto il testo prima di </think>
    if "</think>" in content:
        cleaned_content = content.split("</think>", 1)[1].strip()
    else:
        cleaned_content = content.strip()  # Se non c'è </think>, lascia il contenuto così com'è
    

    #salviamo in una sottocartella le verisoni pulite
    cleaned_dir = DESCRIPTION_DIR / "cleaned"
    cleaned_dir.mkdir(exist_ok=True)
    cleaned_path = cleaned_dir / desc_file.name
    with open(cleaned_path, "w", encoding="utf-8") as f:
        f.write(cleaned_content)

    print(f"Pulito: {cleaned_path.name}")