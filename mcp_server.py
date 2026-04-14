import os
import sys
import json
import subprocess
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("FileOrganizerAgent")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLI_PYTHON = os.path.join(BASE_DIR, ".venv", "bin", "python")
AGENT_SCRIPT = os.path.join(BASE_DIR, "agent.py")

if not os.path.exists(CLI_PYTHON):
    CLI_PYTHON = "python"


@mcp.tool()
def organize_files_dry_run(request: str, target_dir: str) -> str:
    """파일을 실제로 이동하지 않고, 정리 계획(가상 실행 결과)만 생성하여 반환합니다."""
    payload = {
        "request": request,
        "target_dir": target_dir
    }
    
    cmd = [
        CLI_PYTHON,
        AGENT_SCRIPT,
        "--json", json.dumps(payload),
        "--output", "ndjson",
        "--dry-run"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # stderr는 무시하고, stdout의 ndjson 문자열을 반환합니다.
        if not result.stdout.strip():
            return "실행할 파일 정리 제안이 없습니다. (조건에 맞는 파일이 없거나 이미 정리됨)"
        return f"파일 정리 계획이 생성되었습니다. 상세 내용은 다음과 같습니다:\n\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        return f"CLI 실행 중 오류가 발생했습니다: {e.stderr}"
    except Exception as e:
        return f"알 수 없는 오류가 발생했습니다: {str(e)}"


@mcp.tool()
def organize_files_execute(request: str, target_dir: str) -> str:
    """요청에 따라 파일을 실제로 정리(이동 및 이름 변경)합니다."""
    payload = {
        "request": request,
        "target_dir": target_dir
    }
    
    cmd = [
        CLI_PYTHON,
        AGENT_SCRIPT,
        "--json", json.dumps(payload),
        "--output", "ndjson"
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return "파일 정리를 성공적으로 완료했습니다.\n(실행을 취소하려면 --undo 옵션을 사용하세요.)"
    except subprocess.CalledProcessError as e:
        return f"실행 중 오류가 발생했습니다: {e.stderr}"

if __name__ == "__main__":
    mcp.run(transport="stdio")