import os
import shutil
import subprocess
from pathlib import Path

from langchain_core.tools import tool
from rich.console import Console

from core import history
from tools import metadata_db

console = Console()

PROPOSALS = []


def validate_safe_output_dir(path: str) -> bool:
    if not path:
        return False

    normalized = os.path.normpath(path)

    if normalized.startswith("..") or "/../" in normalized:
        return False

    if any(ord(c) < 0x20 for c in path):
        return False

    if "%" in path or "?" in path:
        return False

    return True


@tool
def tool_list_directory(path: str, show_hidden: bool = False) -> str:
    """디렉토리의 내용을 나열합니다."""

    if not validate_safe_output_dir(path):
        return "오류: 경로에 .. 또는 위험한 문자가 포함되어 있어 접근이 차단되었습니다."

    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return f"오류: '{path}' 경로가 존재하지 않습니다"
    if not os.path.isdir(path):
        return f"오류: '{path}'은 디렉토리가 아닙니다"

    items = []
    try:
        for entry in sorted(os.scandir(path), key=lambda e: (e.is_file(), e.name)):
            if not show_hidden and entry.name.startswith("."):
                continue
            stat = entry.stat()
            if entry.is_dir():
                sub_count = len([f for f in os.listdir(entry.path) if not f.startswith(".")])
                items.append(f"[DIR]  {entry.name}/ ({sub_count}개 파일)")
            else:
                size_str = _format_size(stat.st_size)
                ext = Path(entry.name).suffix.lower() or "(없음)"
                items.append(f"[FILE] {entry.name}  |  {size_str}  |  ext={ext}")
    except PermissionError:
        return f"오류: '{path}' 접근 권한 부족"

    if not items:
        return f"'{path}' 디렉토리에 아무것도 없습니다"
    return f"'{path}' 내용 ({len(items)}개):\n" + "\n".join(items)


@tool
def tool_read_file(path: str, max_chars: int = 2000) -> str:
    """파일의 내용을 읽습니다."""

    if not validate_safe_output_dir(path):
        return "오류: 경로에 .. 또는 위험한 문자가 포함되어 있어 접근이 차단되었습니다."

    path = os.path.expanduser(path)

    if not os.path.exists(path):
        return f"오류: '{path}' 파일이 존재하지 않습니다"
    if os.path.isdir(path):
        return f"오류: '{path}'은 디렉토리입니다"

    try:
        with open(path, "rb") as f:
            raw = f.read(512)
        if b"\x00" in raw:
            return f"[바이너리 파일 - 텍스트로 읽을 수 없음] 파일명: {os.path.basename(path)}"
    except Exception as e:
        return f"오류: 파일 읽기 실패: {e}"

    # 텍스트 파일 읽기 (인코딩 자동 감지)
    for encoding in ["utf-8", "utf-8-sig", "cp949", "euc-kr"]:
        try:
            with open(path, "r", encoding=encoding) as f:
                content = f.read(max_chars)
            truncated = len(content) == max_chars
            header = f"[파일: {os.path.basename(path)} | 인코딩: {encoding}]"
            footer = "\n... (내용 생략)" if truncated else ""
            return f"{header}\n{'?' * 40}\n{content}{footer}"
        except (UnicodeDecodeError, LookupError):
            continue

    return f"오류: '{path}' 인코딩을 인식할 수 없습니다"


@tool
def tool_create_directory(path: str) -> str:
    """디렉토리를 생성합니다."""

    if not validate_safe_output_dir(path):
        return "오류: 경로에 .. 또는 위험한 문자가 포함되어 있어 접근이 차단되었습니다."

    path = os.path.expanduser(path)
    if os.path.exists(path):
        return f"이미 존재: '{path}'"
    try:
        os.makedirs(path, exist_ok=True)
        return f"디렉토리 생성: '{path}'"
    except Exception as e:
        return f"오류: 디렉토리 생성 실패: {e}"


@tool
def tool_propose_file_organization(
    source: str,
    destination_dir: str,
    new_filename: str,
    category: str,
    summary: str,
    tags: list,
    extracted_terms: dict = None,
) -> str:
    """파일 정리 제안을 생성합니다."""

    if (
        not validate_safe_output_dir(source)
        or not validate_safe_output_dir(destination_dir)
        or not validate_safe_output_dir(new_filename)
    ):
        return "오류: 경로에 .. 또는 위험한 문자가 포함되어 있어 접근이 차단되었습니다."

    source = os.path.expanduser(source)
    destination_dir = os.path.expanduser(destination_dir)

    if not os.path.exists(source):
        return (
            f"오류: '{source}' 파일이 존재하지 않습니다. "
            "존재하지 않는 파일을 처리할 수 없습니다."
        )
    if os.path.isdir(source):
        return "오류: 대상이 디렉토리입니다 (파일만 처리 가능)"

    dest_path = os.path.join(destination_dir, new_filename)
    if os.path.exists(dest_path) and os.path.abspath(source) != os.path.abspath(dest_path):
        return (
            f"충돌 감지됨: 대상 파일 '{dest_path}'이 이미 존재합니다. "
            "새 파일명(new_filename)을 변경하거나 다른 이름을 사용해 "
            "'다시' tool_propose_file_organization을 호출하세요."
        )

    proposal = {
        "source": source,
        "destination_dir": destination_dir,
        "new_filename": new_filename,
        "category": category,
        "summary": summary,
        "tags": tags,
        "extracted_terms": extracted_terms or {},
    }
    PROPOSALS.append(proposal)
    return (
        "새 파일 이동 제안이 목록에 추가되었습니다: "
        f"{os.path.basename(source)} -> {destination_dir}/{new_filename}"
    )


def execute_proposal(index: int) -> str:
    """제안서를 실제로 실행합니다 (파일 이동, 메타데이터 저장, 기록)."""
    if index < 0 or index >= len(PROPOSALS):
        return "오류: 잘못된 인덱스입니다"

    p = PROPOSALS[index]
    source = p["source"]
    dest_dir = p["destination_dir"]
    new_filename = p["new_filename"]

    if not os.path.exists(source):
        return f"오류: 원본 파일이 더 이상 존재하지 않습니다: {source}"

    if not os.path.exists(dest_dir):
        console.print(f"\n  [bold cyan]mkdir -p {dest_dir}[/bold cyan]")
    os.makedirs(dest_dir, exist_ok=True)

    dest_path = os.path.join(dest_dir, new_filename)
    dest_path = _resolve_conflict(dest_path)

    try:
        console.print(f"  [bold cyan]mv {source} {dest_path}[/bold cyan]")
        shutil.move(source, dest_path)
        history.log_action(source, dest_path)
        metadata_db.save_metadata(
            dest_dir,
            new_filename,
            p["category"],
            p["summary"],
            p["tags"],
            p.get("extracted_terms", {}),
        )
        return f"이동 성공: {os.path.basename(dest_path)}"
    except Exception as e:
        return f"오류: 이동 실패: {e}"


@tool
def tool_summarize_directory(path: str) -> str:
    """디렉토리의 요약을 생성합니다."""

    if not validate_safe_output_dir(path):
        return "오류: 경로에 .. 또는 위험한 문자가 포함되어 있어 접근이 차단되었습니다."

    path = os.path.expanduser(path)
    if not os.path.isdir(path):
        return f"오류: '{path}'은 디렉토리가 아닙니다"

    lines = [f"디렉토리 요약: '{path}'", ""]

    try:
        entries = sorted(os.scandir(path), key=lambda e: e.name)
        root_files = []

        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                files = sorted(
                    f.name for f in os.scandir(entry.path) if f.is_file() and not f.name.startswith(".")
                )
                lines.append(f"폴더 {entry.name}/ ({len(files)}개)")
                for f in files:
                    lines.append(f"   파일 {f}")
            else:
                root_files.append(entry.name)

        if root_files:
            lines.append(f"\n루트 파일 ({len(root_files)}개):")
            for f in root_files:
                lines.append(f"   {f}")

    except Exception as e:
        return f"오류: {e}"

    return "\n".join(lines)


# ------------------------------------------------------------
# 보조 함수
# ------------------------------------------------------------
def _format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _resolve_conflict(path: str) -> str:
    if not os.path.exists(path):
        return path
    base = Path(path)
    counter = 1
    while True:
        new_path = base.parent / f"{base.stem}_{counter}{base.suffix}"
        if not os.path.exists(new_path):
            return str(new_path)
        counter += 1


@tool
def tool_execute_cli_command(command: str) -> str:
    """
    터미널 명령어를 실행합니다. 
    현재 디렉토리에 가상환경(.venv 또는 venv)이 존재하면 자동으로 활성화 후 명령어를 수행합니다.
    """
    import platform
    
    try:
        # 1. 위험 명령어 차단 (기존 유지)
        if any(bad_char in command for bad_char in ["sudo", "rm -rf", "\0"]):
            return "오류: 위험한 명령어(삭제 또는 파괴적인 명령어)가 차단되었습니다."

        # 2. 가상환경 자동 감지 및 접두어 생성
        venv_name = ".venv" if os.path.exists(".venv") else "venv"
        full_command = command
        
        if os.path.exists(venv_name):
            if platform.system() == "Windows":
                # Windows: .\venv\Scripts\activate && 명령어
                prefix = f".\\{venv_name}\\Scripts\\activate && "
            else:
                # Linux/Mac: source venv/bin/activate && 명령어
                prefix = f"source {venv_name}/bin/activate && "
            
            full_command = prefix + command
            # console.print(f"[dim]Auto-activating venv: {full_command}[/dim]") # 디버그용

        # 3. 명령어 실행
        result = subprocess.run(
            full_command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=15
        )
        
        output = result.stdout if result.returncode == 0 else result.stderr
        if not output.strip():
            output = f"명령어 '{command}'가 정상적으로 실행되었습니다. (출력 없음)"
            
        return output

    except subprocess.TimeoutExpired:
        return "오류: 명령어 실행 시간이 너무 오래 걸렸습니다 (15초 제한)."
    except Exception as e:
        return f"명령어 실행 실패: {e}"


ALL_TOOLS = [
    tool_list_directory,
    tool_read_file,
    tool_create_directory,
    tool_propose_file_organization,
    tool_summarize_directory,
    tool_execute_cli_command,
]