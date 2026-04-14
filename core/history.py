import json
import os
import shutil

HISTORY_FILE = ".agent_history.json"

def log_action(source: str, dest: str):
    """이동/변경 내역 저장 (가장 최근이 직전에 오도록)"""
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
            
    history.append({
        "source": source,
        "dest": dest
    })
    
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def rollback(all: bool = True):
    """가장 최근 상태로 되돌립니다. all=True면 전체, False면 마지막 1건만 복구합니다."""
    if not os.path.exists(HISTORY_FILE):
        return "복구할 기록이 없습니다."
        
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        return "히스토리 파일 읽기 실패"
        
    if not history:
        return "복구할 기록이 없습니다."
        
    results = []
    
    def _do_rollback(action_item):
        source = action_item["source"]
        dest = action_item["dest"]
        if os.path.exists(dest):
            os.makedirs(os.path.dirname(source), exist_ok=True)
            shutil.move(dest, source)
            results.append(f"복구: {os.path.basename(dest)} -> {os.path.basename(source)}")
        else:
            results.append(f"파일 없음 (건너뜀): {dest}")

    if all:
        # 역순으로 전부 복구
        while history:
            _do_rollback(history.pop())
    else:
        # 단 1건만 복구
        _do_rollback(history.pop())
            
    # 남은 / 빈 배열 재저장
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
        
    return "\n".join(results)
