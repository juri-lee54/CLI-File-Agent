import os
import json
import argparse
import sys
import time
import threading

# 환경 변수 로드 (.env 파일이 있으면 여기서 로드됨)
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AnyMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from typing import Annotated, TypedDict
from tools import core_tools
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from core import history
from core.paths import demo_folder_str
from interfaces import watcher

console = Console()

MODEL = "gpt-4o"
MAX_TOKENS = 4096

# ══════════════════════════════════════════════════════
# 1. 파일 정리 전담 에이전트 프롬프트 (FILE_ORGANIZER)
# ══════════════════════════════════════════════════════
FILE_ORGANIZER_PROMPT = """당신은 파일의 내용을 읽고 카테고리별로 폴더에 분류하는 전문 AI Agent입니다.
[중요: 가상환경 실행 규칙]
- 모든 터미널 명령어(`tool_execute_cli_command`) 실행 시, 반드시 현재 디렉토리의 가상환경을 먼저 활성화해야 합니다.
- 가상환경 폴더명은 '.venv' 또는 'venv'라고 가정합니다.
- 명령어 형식 (Windows): ".\\venv\\Scripts\\activate && 명령어"
- 명령어 형식 (Linux/Mac): "source venv/bin/activate && 명령어"
- 절대로 가상환경 활성화 없이 pip install이나 python 명령어를 실행하지 마세요.

## 작업 순서 (파일 이동/분류 요청 시)
1. `tool_list_directory`로 대상 폴더의 파일 목록 파악
2. 각 파일을 `tool_read_file`로 내용 확인 (확장자가 아닌 내용으로 판단)
3. 필요 시 `tool_create_directory`로 분류용 하위 폴더를 먼저 생성
4. 내용 기반으로 카테고리 결정 (요약 내용 및 태그 도출)
5. `tool_propose_file_organization`으로 분류 폴더로 이동 제안
6. 모든 파일 처리 후 `tool_summarize_directory`로 최종 결과 보고

## 작업 순서 (시스템 제어 / 백그라운드 구동 등 관리자 명령어 요청 시)
- 사용자가 "백그라운드로 띄워줘", "감시 시작해줘", "이 스크립트 실행해줘" 등을 요구할 경우 `tool_execute_cli_command` 도구를 사용하여 즉각 터미널(CLI) 명령어를 백그라운드 등에서 실행하고 그 출력을 제공하세요.

## 카테고리 및 네이밍 규칙
[중요] 같은 카테고리의 파일은 반드시 동일한 prefix와 형식을 사용하세요.
형식: {category_prefix}_{descriptive_name}{extension}

- Recipes/  → recipe_ (예: recipe_티라미수.txt)
- Travel/   → travel_ (예: travel_교토.txt)
- Dev/      → dev_    (예: dev_python.py)
- Finance/  → finance_
- Health/   → health_
- Books/    → book_
- Others/   → other_

## 주의사항
- [핵심] 도구를 직접 호출하기 전에, 항상 당신이 지금 어떤 판단(추론 과정)을 해서 이 도구를 부르는지 짧게 글로 설명하세요.
- 파일 하나당 반드시 `tool_propose_file_organization` 도구(Tool)를 실제로 "호출(Call)"하여 시스템에 등록하세요.
- 사용자에게 텍스트로 "실행할까요?"라고 묻지 마세요. 도구를 호출하면 시스템이 알아서 승인을 받습니다.
- 목적지에 이미 같은 이름의 파일이 있다는 에러가 나면 스스로 파일명을 바꿔 `tool_propose_file_organization`을 다시 호출하세요.
- 완료 시 `tool_summarize_directory`를 호출하여 종료하세요.
"""

# ══════════════════════════════════════════════════════
# 2. RAG 지식 추출 전담 에이전트 프롬프트 (RAG_EXTRACTOR)
# ══════════════════════════════════════════════════════
RAG_EXTRACTOR_PROMPT = """당신은 문서 속에서 전문 지식을 추출하여 RAG 데이터베이스를 구축하는 전문 AI Agent입니다.
당신은 파일을 이동하는 것이 주목적이 아니라, 파일 속의 '핵심 용어와 설명'을 뽑아내는 것이 목적입니다.

## 작업 순서
1. `tool_list_directory`로 대상 경로를 파악한 뒤, `tool_read_file`로 파일을 최대한 깊게 읽습니다.
2. 파일 내용 중 전문 용어, 개념, 핵심 이론을 찾아냅니다.
3. `tool_propose_file_organization`을 호출하되:
   - 파일 이동(destination_dir)은 현재 폴더와 동일하게 유지해도 좋고 별도 요청이 없다면 RAG_DB/ 와 같이 지정합니다.
   - [가장 중요] `extracted_terms` 파라미터에 반드시 용어를 key, 설명을 value로 최소 3개 이상 작성하세요.

## 주의사항
- [핵심] 도구를 호출하기 전, 어떤 키워드를 왜 뽑았는지 등 추론 과정(Thought Process)을 꼭 텍스트로 먼저 적으세요.
- 사용자가 준 상세 재지시(피드백)가 있다면 무조건 반영하여 추출 방식을 교정하세요.
- 완료 시 `tool_summarize_directory`를 호출하세요.
"""

# ══════════════════════════════════════════════════════
# 3. 수퍼바이저 라우팅 프롬프트 (SUPERVISOR)
# ══════════════════════════════════════════════════════
SUPERVISOR_PROMPT = """당신은 사용자의 요청을 분석하여 적절한 워커 에이전트에게 업무를 배분하는 Supervisor입니다.
요청을 보고 다음 중 하나의 분류를 정확히 선택해 JSON 형식으로만 응답하세요.

- "FILE_ORGANIZER" : 폴더 분류, 네이밍 규칙 변경 등에 대한 일반적인 내용
- "RAG_EXTRACTOR" : 지식 추출, 추출(extract), 전문 용어 정리, RAG 등 분석이 목적일 때

응답 예시:
{"agent": "FILE_ORGANIZER"}
"""


def print_banner():
    banner = Text()
    banner.append("🗂️  File Organizer Agent", style="bold cyan")
    banner.append("  v2", style="bold yellow")
    banner.append("\n    내용 기반 분류 + 일관된 제목 변경", style="dim")
    console.print(Panel(banner, border_style="cyan", padding=(1, 4)))


def print_tool_call(tool_name: str, params: dict):
    """Tool 호출을 시각적으로 표현 (LangChain 등록 이름: tool_* )"""
    icons = {
        "tool_list_directory": "📋",
        "tool_read_file": "👁️ ",
        "tool_create_directory": "📁",
        "tool_propose_file_organization": "✂️ ",
        "tool_summarize_directory": "📊",
        "tool_execute_cli_command": "💻",
    }
    icon = icons.get(tool_name, "🔧")

    console.print(f"\n  {icon} [yellow bold]{tool_name}[/yellow bold]", end="")

    # 핵심 파라미터만 터미널 명령어 스타일로 출력
    if tool_name == "tool_read_file":
        console.print(f"\n  [bold cyan]❯ cat {params.get('path', '')}[/bold cyan]")
    elif tool_name == "tool_propose_file_organization":
        src = os.path.basename(params.get("source", ""))
        dest_dir = os.path.basename(params.get("destination_dir", ""))
        new_name = params.get("new_filename", "")
        console.print(f"\n     [dim]{src}[/dim] ⇢ [green](제안) {dest_dir}/{new_name}[/green]")
    elif tool_name == "tool_list_directory":
        console.print(f"\n  [bold cyan]❯ ls -la {params.get('path', '')}[/bold cyan]")
    elif tool_name == "tool_create_directory":
        console.print(f"\n  [bold cyan]❯ mkdir -p {params.get('path', '')}[/bold cyan]")
    elif tool_name == "tool_summarize_directory":
        console.print(f"\n  [bold cyan]❯ tree {params.get('path', '')}[/bold cyan]")
    elif tool_name == "tool_execute_cli_command":
        console.print(f"\n  [bold magenta]❯ {params.get('command', '')}[/bold magenta]")
    else:
        console.print()
        for k, v in params.items():
            console.print(f"     [dim]{k}:[/dim] {v}")


def print_tool_result(tool_name: str, result: str):
    """Tool 결과 출력 — 도구 종류에 따라 다르게 표시"""
    success = not result.startswith("오류")
    icon = "✅" if success else "❌"
    color = "green" if success else "red"

    # tool_read_file은 내용이 길어서 첫 줄만 표시
    if tool_name == "tool_read_file" and success:
        lines = result.split("\n")
        preview = lines[2] if len(lines) > 2 else lines[0]
        console.print(f"  {icon} [{color}]내용 확인됨[/{color}] [dim]— \"{preview[:50]}...\"[/dim]")
    elif tool_name == "tool_summarize_directory" and success:
        # 요약은 전체 출력
        console.print()
        for line in result.split("\n"):
            console.print(f"     {line}")
    elif tool_name == "tool_propose_file_organization" and success:
        console.print(f"  {icon} [yellow]제안됨:[/yellow] {result}")
    else:
        # 짧은 결과는 그대로
        first_line = result.split("\n")[0]
        console.print(f"  {icon} [{color}]{first_line}[/{color}]")


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

def run_supervisor(user_request: str) -> str:
    """사용자 요청을 분석하여 적절한 Worker Agent를 선택합니다."""
    # ... 기존 프롬프트와 ChatOpenAI 로직을 그대로 사용 ...
    client = ChatOpenAI(model=MODEL, temperature=0, model_kwargs={"response_format": {"type": "json_object"}})
    console.print("\n[dim]🕵️ 수퍼바이저(Supervisor)가 업무를 배분 중입니다...[/dim]")
    try:
        response = client.invoke([
            SystemMessage(content=SUPERVISOR_PROMPT),
            HumanMessage(content=user_request)
        ])
        decision = json.loads(response.content)
        agent_type = decision.get("agent", "FILE_ORGANIZER")
        console.print(f"[bold magenta]👉 라우팅 결정: {agent_type} 에이전트로 작업을 전달합니다.[/bold magenta]")
        return agent_type
    except Exception as e:
        console.print(f"[dim]라우팅 실패 (기본값 사용): {e}[/dim]")
        return "FILE_ORGANIZER"


def custom_agent_node(state: AgentState):
    llm = ChatOpenAI(model=MODEL, temperature=0).bind_tools(core_tools.ALL_TOOLS)
    console.print("[dim]... GPT 라우팅 판단 중 ...[/dim]")
    response = llm.invoke(state["messages"])
    if response.content:
        console.print(f"\n  💭 [cyan]{response.content.strip()}[/cyan]")
    return {"messages": [response]}


def custom_tool_node(state: AgentState):
    last_message = state["messages"][-1]
    tool_msgs = []
    
    for tc in last_message.tool_calls:
        func_name = tc["name"]
        func_args = tc["args"]
        print_tool_call(func_name, func_args)
        
        tool_impl = next((t for t in core_tools.ALL_TOOLS if t.name == func_name), None)
        if tool_impl:
            result = str(tool_impl.invoke(func_args))
        else:
            result = f"오류: '{func_name}' 도구를 찾을 수 없습니다"
            
        print_tool_result(func_name, result)
        tool_msgs.append(ToolMessage(content=result, tool_call_id=tc["id"]))
        
    return {"messages": tool_msgs}


def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


GRAPH_WORKFLOW = StateGraph(AgentState)
GRAPH_WORKFLOW.add_node("agent", custom_agent_node)
GRAPH_WORKFLOW.add_node("tools", custom_tool_node)
GRAPH_WORKFLOW.add_edge(START, "agent")
GRAPH_WORKFLOW.add_conditional_edges("agent", should_continue, ["tools", END])
GRAPH_WORKFLOW.add_edge("tools", "agent")
compiled_graph = GRAPH_WORKFLOW.compile()


def run_agent(user_request: str, target_dir: str, session_messages: list = None, agent_type: str = "FILE_ORGANIZER"):
    """LangGraph 기반 Agentic Loop"""
    
    if session_messages is None:
        system_prompt = RAG_EXTRACTOR_PROMPT if agent_type == "RAG_EXTRACTOR" else FILE_ORGANIZER_PROMPT
        session_messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=(
                f"대상 디렉토리: {os.path.abspath(target_dir)}\n\n"
                f"주의: 이 환경에서 실행되는 모든 CLI 명령어는 반드시 해당 경로의 가상환경(venv) 내에서 동작해야 합니다.\n\n"
                f"요청: {user_request}"
            ))
        ]
        console.print(f"\n📁 [bold]대상 디렉토리:[/bold] {os.path.abspath(target_dir)}")
        console.print(f"💬 [bold]요청:[/bold] {user_request}")
    else:
        # 피드백 루프로 호출된 경우
        session_messages.append(HumanMessage(content=f"사용자 피드백 (재지시): {user_request}\n위 피드백을 반영하여 계획을 완전히 수정하고, 즉시 다시 제안(propose)하세요."))
        console.print(f"\n💬 [bold yellow]피드백 전송:[/bold yellow] {user_request}")
        
    console.rule(f"\n[dim]{agent_type} LangGraph Agent 작동 중...[/dim]")

    # LangGraph 호출
    final_state = compiled_graph.invoke({"messages": session_messages})
    
    console.rule("[dim]LangGraph 실행 완료[/dim]")
    return final_state["messages"]


def execute_all_pending_proposals(*, announce: bool = True) -> int:
    """PROPOSALS 큐를 순서대로 실행하고 비움. 반환: 실행한 건수."""
    n = len(core_tools.PROPOSALS)
    if n == 0:
        return 0
    if announce:
        console.print("\n[bold green]제안 자동 실행 중...[/bold green]")
    for i in range(n):
        res = core_tools.execute_proposal(i)
        console.print(f"  ✅ {res}")
    core_tools.PROPOSALS.clear()
    return n


def review_and_execute_proposals() -> str:
    """제안된 목록을 보여주고, 승인 시 실행(Human-in-the-loop)
    반환값: "EXECUTED", "CANCELLED", 또는 피드백 텍스트(문자열)
    """
    if not core_tools.PROPOSALS:
        console.print("\n[dim]현재 실행할 제안이 없습니다.[/dim]")
        return "EXECUTED"
        
    table = Table(title="📋 AI 이동/분류/추출 제안 목록 (실행 대기중)")
    table.add_column("No", justify="right", style="cyan")
    table.add_column("원본 파일명", style="magenta")
    table.add_column("새 대상/이름", style="green")
    table.add_column("요약/추출", style="yellow")
    table.add_column("태그", style="blue")
    
    for i, p in enumerate(core_tools.PROPOSALS):
        src_name = os.path.basename(p["source"])
        dest_cat = f"{os.path.basename(p['destination_dir'])}/ {p['new_filename']}"
        terms = p.get("extracted_terms", {})
        term_str = f"[{len(terms)}개 용어 추출됨]" if terms else p["summary"].replace("\n", " ")
        tags_str = ", ".join(p["tags"])
        table.add_row(str(i+1), src_name, dest_cat, term_str, tags_str)
        
    console.print(table)
    
    console.print("\n[bold]위 계획대로 실행할까요?[/bold]")
    console.print(" - [green]y[/green]: 승인 후 실행")
    console.print(" - [red]n[/red]: 취소")
    console.print(" - [yellow]기타 텍스트[/yellow]: AI에게 거절 사유 및 수정 지시 (수정해서 다시 가져와)")
    
    choice = input("입력 > ").strip()
    
    if choice.lower() == 'y':
        console.print("\n[bold green]실행을 시작합니다...[/bold green]")
        execute_all_pending_proposals(announce=False)
        console.print("\n[bold cyan]🎉 처리가 완료되었습니다. (되돌리려면 --undo 옵션을 사용하세요)[/bold cyan]")
        return "EXECUTED"
    elif choice.lower() == 'n':
        console.print("\n[yellow]실행이 취소되었습니다.[/yellow]")
        core_tools.PROPOSALS.clear()
        return "CANCELLED"
    else:
        # 사용자가 피드백을 입력한 경우
        return choice

def run_interactive_agent_loop(request: str, target: str):
    """피드백 루프를 처리하는 래퍼 함수"""
    agent_type = run_supervisor(request)
    session = None
    curr_req = request
    
    while True:
        session = run_agent(curr_req, target, session_messages=session, agent_type=agent_type)
        feedback = review_and_execute_proposals()
        
        if feedback in ["EXECUTED", "CANCELLED"]:
            break
        else:
            # 피드백이 들어옴 -> 도구 제안을 비우고 이 피드백을 들고 다시 루프를 돈다.
            core_tools.PROPOSALS.clear()
            curr_req = feedback


def run_watch_organize_once(new_file: str, target: str, default_request: str) -> None:
    """감시 모드 전용: 승인 입력 없이 에이전트 실행 후 제안을 즉시 반영 (웹 API와 동일한 자동 실행)."""
    core_tools.PROPOSALS.clear()
    req = (
        f"'{new_file}' 파일만 읽고 카테고리를 파악해서 적절한 폴더로 분류 및 이름 변경 계획을 제안해줘. "
        f"같은 폴더의 다른 파일은 건드리지 마. (사용자 요청 가이드: {default_request})"
    )
    agent_type = run_supervisor(req)
    run_agent(req, target, session_messages=None, agent_type=agent_type)
    n = execute_all_pending_proposals(announce=True)
    if n == 0:
        console.print("[yellow]이번 파일에 대해 이동 제안이 없었습니다. (이미 정리됐거나 도구만 호출된 경우)[/yellow]")
    else:
        console.print(f"[bold cyan]🎉 자동 정리 완료 ({n}건)[/bold cyan]")


def watch_mode(
    target: str,
    default_request: str,
    *,
    stop_event: threading.Event | None = None,
) -> None:
    """지정된 디렉토리를 계속 감시하며 파일 생성 시 Agent를 깨움 (터미널 y/n 없이 자동 실행).

    stop_event: 웹 등에서 설정하면 is_set()일 때 루프를 빠져나옵니다 (Ctrl+C 불필요).
    """
    console.print(f"\n[bold green]👀 '{target}' 폴더 실시간 감시 시작...[/bold green]")
    if stop_event is None:
        console.print("[dim]루트에 직접 생기거나 저장되는 파일만 감지합니다. (Ctrl+C 로 종료)[/dim]\n")
    else:
        console.print("[dim]루트에 직접 생기거나 저장되는 파일만 감지합니다. (웹에서 감시 중지 가능)[/dim]\n")

    import queue

    file_queue = queue.Queue()
    debounce: dict[str, float] = {}
    debounce_sec = 2.0

    def on_new_file(path: str):
        # 콜백은 watchdog 스레드에서 호출되므로 여기서 블로킹 sleep 하지 않음
        file_queue.put(path)

    observer = watcher.start_watching(target, on_new_file)
    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            try:
                new_file = file_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if stop_event is not None and stop_event.is_set():
                break

            now = time.monotonic()
            if new_file in debounce and (now - debounce[new_file]) < debounce_sec:
                continue
            debounce[new_file] = now

            time.sleep(0.6)
            if stop_event is not None and stop_event.is_set():
                break
            if not os.path.isfile(new_file):
                continue

            console.print(f"\n[bold yellow]🔔 새 파일 감지됨:[/bold yellow] [dim]{new_file}[/dim]")
            console.print("[dim]🤖 AI 분석 및 자동 적용 중...[/dim]")
            try:
                run_watch_organize_once(new_file, target, default_request)
            except Exception as e:
                console.print(f"[red]감시 처리 중 오류: {e}[/red]")
            console.print("\n[bold green]👀 계속 감시 중...[/bold green]")

    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
    if stop_event is not None:
        console.print("\n[dim][웹/API] 감시를 종료했습니다.[/dim]")
    else:
        console.print("\n[dim]감시가 종료되었습니다.[/dim]")


def main():
    parser = argparse.ArgumentParser(description="File Organizer AI Agent v2")
    parser.add_argument("--watch", "-w", action="store_true", help="지정된 폴더를 실시간 감시 모드로 실행합니다.")
    parser.add_argument("--undo", action="store_true", help="가장 마지막으로 실행한 파일 정리 작업을 복구합니다.")
    
    # AI 에이전트를 위한 새로운 플래그 추가
    parser.add_argument("--json", type=str, help="작업 요청을 단일 JSON 문자열 페이로드로 제공합니다 (에이전트용).")
    parser.add_argument("--output", choices=["text", "json", "ndjson"], default="text", help="출력 형식을 지정합니다.")
    parser.add_argument("--schema", action="store_true", help="이 CLI의 입력 및 출력 설명에 대한 JSON Schema를 반환합니다.")
    parser.add_argument("--dry-run", action="store_true", help="실제 파일을 이동/변경하지 않고 계획만 생성/출력합니다.")
    
    args = parser.parse_args()

    # json이나 ndjson 포맷 출력을 요청받았다면, 터미널 꾸밈 요소 출력을 끕니다.
    if args.output in ["json", "ndjson"] or args.schema:
        console.quiet = True
    if not args.schema and args.output not in ["json", "ndjson"]:
        print_banner()

    if args.schema:
        schema = {
            "name": "File_Organizer_Agent_CLI",
            "description": "AI Agent를 위한 파일 정리 및 분류 자동화 CLI",
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": "수행할 작업에 대한 자연어 요청. (예: 'demo_folder 내부의 파일들을 확장자 기준이 아닌 내용 기반으로 문서와 이미지로 나누어줘')"
                    },
                    "target_dir": {
                        "type": "string",
                        "description": "명령을 수행할 대상 디렉토리 절대/상대 경로"
                    },
                    "agent_type": {
                        "type": "string",
                        "enum": ["FILE_ORGANIZER", "RAG_EXTRACTOR"],
                        "description": "요청을 처리할 에이전트 종류. 알 수 없는 경우 생략하면 스스로 결정."
                    }
                },
                "required": ["request", "target_dir"]
            }
        }
        # json 출력이므로 quiet를 해제하거나 sys.stdout.write 로 출력
        sys.stdout.write(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")
        sys.exit(0)

    # ---------------------------------------------------------
    # 에이전트용 JSON 페이로드 처리 모드
    # ---------------------------------------------------------
    if args.json:
        try:
            payload = json.loads(args.json)
        except json.JSONDecodeError:
            sys.stderr.write(json.dumps({"error": "Invalid JSON payload"}) + "\n")
            sys.exit(1)
            
        target = payload.get("target_dir")
        request = payload.get("request")
        agent_type = payload.get("agent_type")
        
        if not target or not request:
            sys.stderr.write(json.dumps({"error": "Missing required fields: target_dir, request"}) + "\n")
            sys.exit(1)
            
        if not agent_type:
            agent_type = run_supervisor(request)
            
        # 에이전트 실행
        run_agent(request, target, session_messages=None, agent_type=agent_type)
        
        # 출력 형식이 JSON / NDJSON 인 경우
        if args.output == "json":
            sys.stdout.write(json.dumps(core_tools.PROPOSALS, ensure_ascii=False, indent=2) + "\n")
        elif args.output == "ndjson":
            for p in core_tools.PROPOSALS:
                sys.stdout.write(json.dumps(p, ensure_ascii=False) + "\n")

        # dry-run이 아니면 실제 실행
        if not args.dry_run:
            execute_all_pending_proposals(announce=args.output=="text")
        
        sys.exit(0)
    # ---------------------------------------------------------

    if args.undo:
        console.print("\n[bold yellow]⏪ 실행 취소 (Rollback) 옵션[/bold yellow]")
        console.print("  [1] 마지막 작업 1건만 복구 (기본값)")
        console.print("  [2] 여태까지의 모든 히스토리 전체 복구")
        choice = input("\n숫자를 입력하세요 (1/2) [기본: 1] > ").strip()
        
        if choice == "2":
            console.print("\n[dim]⏪ 전체 작업을 복구 중입니다...[/dim]")
            result = history.rollback(all=True)
        else:
            console.print("\n[dim]⏪ 마지막 작업 1건을 복구 중입니다...[/dim]")
            result = history.rollback(all=False)
            
        console.print(result)
        sys.exit(0)

    console.print("\n[bold]정리할 디렉토리 경로를 입력하세요[/bold]")
    console.print("[dim](Enter = 현재 디렉토리)[/dim]")
    
    attempts = 0
    target = ""
    while attempts < 3:
        target = input("  📂 경로: ").strip() or "."
        
        # 한국어 음성/오타 보정기 (데모 전용)
        if target.replace(" ", "") in ["데모폴더", "데포폴더", "데모폴더줘", "demo", "데모", "demo_folder"]:
            target = demo_folder_str()
            console.print(f"  [dim]💡 시연 폴더로 자동 보정: {target}[/dim]")
            
        if os.path.isdir(target):
            break
            
        attempts += 1
        console.print(f"  [red]오류: '{target}' 디렉토리를 찾을 수 없습니다. (남은 기회: {3-attempts}번)[/red]")
        
    if not os.path.isdir(target):
        console.print("  [red]❌ 디렉토리 경로를 찾지 못해 프로그램을 종료합니다.[/red]")
        return

    console.print("\n[bold]어떻게 정리할까요?[/bold]")
    console.print("[dim](Enter = 기본 요청 사용)[/dim]")
    request = input("  💬 요청: ").strip()

    if not request:
        request = "파일 내용을 읽고 카테고리를 파악해서 적절한 폴더로 분류하고, 같은 분류의 파일들은 일관된 네이밍 규칙으로 제목을 수정해줘."

    if args.watch:
        watch_mode(target, request)
    else:
        run_interactive_agent_loop(request, target)

if __name__ == "__main__":
    main()
