import json
import os

def save_metadata(directory: str, filename: str, category: str, summary: str, tags: list, extracted_terms: dict = None):
    """해당 폴더의 .agent_metadata.json에 파일 메타데이터를 누적 기록합니다."""
    os.makedirs(directory, exist_ok=True)
    db_path = os.path.join(directory, ".agent_metadata.json")
    
    data = {}
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
            
    data[filename] = {
        "category": category,
        "summary": summary,
        "tags": tags,
        "extracted_terms": extracted_terms or {}
    }
    
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
