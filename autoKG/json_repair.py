import json
import re
from typing import Any


def loads(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        return []

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.IGNORECASE | re.DOTALL)
    for block in fenced_blocks:
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            continue

    array_start = raw.find("[")
    array_end = raw.rfind("]")
    if array_start != -1 and array_end != -1 and array_end > array_start:
        try:
            return json.loads(raw[array_start:array_end + 1])
        except json.JSONDecodeError:
            pass

    object_start = raw.find("{")
    object_end = raw.rfind("}")
    if object_start != -1 and object_end != -1 and object_end > object_start:
        try:
            return json.loads(raw[object_start:object_end + 1])
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("Unable to repair JSON payload", raw, 0)
