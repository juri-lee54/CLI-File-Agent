import os
import json
import argparse
import sys
import time
import threading
import re
import uuid

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

def get_current_provider_and_model():
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    default_model = "qwen2.5:14b" if provider == "ollama" else "gpt-4o"
    model = os.getenv("LLM_MODEL", default_model)
    return provider, model

def get_llm(json_mode: bool = False):
    """LLM 프로바이더(ollama/openai)에 따라 ChatOpenAI 호환 객체를 반환합니다."""
    provider, model = get_current_provider_and_model()
    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        kwargs = {
            "model": model,
            "base_url": base_url,
            "api_key": "ollama",
            "temperature": 0,
            "extra_body": {"num_ctx": 8192},
        }
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatOpenAI(**kwargs)
    elif provider == "openai":
        kwargs = {
            "model": model,
            "temperature": 0,
        }
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatOpenAI(**kwargs)
    else:
        return ChatOpenAI(model=model, temperature=0)

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
1. `tool_scan_directory_contents`를 가장 먼저 호출하여 대상 디렉토리 내 모든 파일의 내용 미리보기를 일괄 스캔하세요. (한 번의 호출로 모든 파일의 핵심 내용과 형식을 즉시 파악할 수 있어 가장 빠르고 효율적입니다.)
2. 스캔한 파일들의 분류 계획을 `tool_propose_batch_organization`을 호출하여 한 번에 일괄 등록하세요! (가장 빠르고 강력히 권장됩니다. 파일들을 하나씩 따로 등록하지 말고, `items` 리스트에 담아 한 번에 전달하세요.)
3. 제안 등록이 완료되면 `tool_summarize_directory`를 호출하여 작업을 완료하세요.

## 작업 순서 (시스템 제어 / 백그라운드 구동 등 관리자 명령어 요청 시)
- 사용자가 "백그라운드로 띄워줘", "감시 시작해줘", "이 스크립트 실행해줘" 등을 요구할 경우 `tool_execute_cli_command` 도구를 사용하여 즉각 터미널(CLI) 명령어를 백그라운드 등에서 실행하고 그 출력을 제공하세요.

## [가장 중요: 사용자 요청 범위 및 Others 폴더 금지 규칙]
- 사용자가 특정 카테고리나 특정 파일만 지정하여 요청한 경우 (예: "레시피만 모아줘", "여행 관련 파일만 정리해줘", "파이썬 코드만 옮겨줘"):
  - [절대 금지] 요청과 무관한 파일들을 'Others/' 폴더나 기타 폴더로 절대 이동 제안하지 마세요!
  - 오직 사용자가 요구한 대상 파일들만 제안 목록에 등록하고, 나머지 파일들은 제안에 포함하지 않고 원래 위치에 그대로 두어야 합니다.
- 전체 정리를 명시적으로 요청했을 때(예: "전체 파일을 주제별로 전부 분류해줘")에만 모든 파일을 적절한 카테고리로 나누세요.

## 카테고리 및 네이밍 규칙
[중요] 같은 카테고리의 파일은 반드시 동일한 prefix와 형식을 사용하세요.
형식: {category_prefix}_{descriptive_name}{extension}

- Recipes/  → recipe_ (예: recipe_티라미수.txt)
- Travel/   → travel_ (예: travel_교토.txt)
- Dev/      → dev_    (예: dev_python.py)
- Finance/  → finance_
- Health/   → health_
- Books/    → book_
- Others/   → other_ (전체 정리 요청 시에만 사용)

## 주의사항
- [멀티모달 지원] 텍스트(.txt, .md, .py)뿐만 아니라 Word(.docx), Excel(.xlsx), CSV(.csv), PDF(.pdf), 이미지(.jpg, .png)도 `tool_read_file`로 본문과 메타데이터를 모두 파싱할 수 있으니 모든 확장자의 파일을 `tool_read_file`로 읽고 분석하세요.
- [핵심: 도구 연속 호출] 작업이 진행 중일 때는 텍스트만 출력하고 멈추지 마세요. 판단 후 반드시 필요한 도구(`tool_read_file`, `tool_propose_file_organization` 등)를 실제로 호출해야 다음 단계로 진행됩니다.
- [도구 호출 형식] 도구를 호출할 때는 반드시 시스템 Function Call 메커니즘을 사용하세요. 텍스트로 도구 호출을 흉내내거나 멈추지 마세요.
- 파일 하나당 반드시 `tool_propose_file_organization` 도구(Tool)를 실제로 "호출(Call)"하여 시스템에 등록하세요.
- 사용자에게 텍스트로 "실행할까요?"라고 묻지 마세요. 도구를 호출하면 시스템이 알아서 승인을 받습니다.
- 목적지에 이미 같은 이름의 파일이 있다는 에러가 나면 스스로 파일명을 바꿔 `tool_propose_file_organization`을 다시 호출하세요.
- 모든 파일에 대한 제안이 완료되면 `tool_summarize_directory`를 호출하여 종료하세요.
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
    banner.append("\n    내용 기반 분류 + 일관된 제목 변경", style="dim")
    provider, model = get_current_provider_and_model()
    banner.append(f"\n    [LLM 엔진: {provider.upper()} ({model})]", style="magenta")
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
    client = get_llm(json_mode=True)
    console.print("\n[dim]🕵️ 수퍼바이저(Supervisor)가 업무를 배분 중입니다...[/dim]")
    try:
        response = client.invoke([
            SystemMessage(content=SUPERVISOR_PROMPT),
            HumanMessage(content=user_request)
        ])
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        if "{" in content and "}" in content:
            start = content.find("{")
            end = content.rfind("}") + 1
            content = content[start:end]
        decision = json.loads(content)
        agent_type = decision.get("agent", "FILE_ORGANIZER")
        console.print(f"[bold magenta]👉 라우팅 결정: {agent_type} 에이전트로 작업을 전달합니다.[/bold magenta]")
        return agent_type
    except Exception as e:
        console.print(f"[dim]라우팅 실패 (기본값 사용): {e}[/dim]")
        return "FILE_ORGANIZER"


def extract_fallback_tool_calls(content: str, valid_tool_names: set[str]) -> list[dict]:
    """오픈소스 LLM(Qwen 등)이 텍스트로 도구 호출 마크다운을 누출했을 때 복구"""
    recovered = []
    
    # 1. 'gc ... 'gc 패턴
    for m in re.finditer(r"'gc\s*(\{.*?\})\s*'gc", content, re.DOTALL):
        try:
            data = json.loads(m.group(1))
            name = data.get("name")
            args = data.get("arguments") or data.get("args") or {}
            if name in valid_tool_names:
                recovered.append({
                    "name": name,
                    "args": args,
                    "id": f"call_rec_{uuid.uuid4().hex[:8]}",
                    "type": "tool_call"
                })
        except Exception:
            pass

    # 2. <tool_call> ... </tool_call> 패턴
    for m in re.finditer(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", content, re.DOTALL):
        try:
            data = json.loads(m.group(1))
            name = data.get("name")
            args = data.get("arguments") or data.get("args") or {}
            if name in valid_tool_names:
                recovered.append({
                    "name": name,
                    "args": args,
                    "id": f"call_rec_{uuid.uuid4().hex[:8]}",
                    "type": "tool_call"
                })
        except Exception:
            pass

    # 3. ```json ... ``` 패턴
    for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL):
        try:
            data = json.loads(m.group(1))
            name = data.get("name")
            args = data.get("arguments") or data.get("args") or {}
            if name in valid_tool_names:
                recovered.append({
                    "name": name,
                    "args": args,
                    "id": f"call_rec_{uuid.uuid4().hex[:8]}",
                    "type": "tool_call"
                })
        except Exception:
            pass

    # 4. 일반 텍스트 내 단독 JSON 객체 탐색
    if not recovered:
        for tool_name in valid_tool_names:
            if tool_name in content:
                pattern = rf'(\{{\s*"name"\s*:\s*"{tool_name}".*?\}})'
                for m in re.finditer(pattern, content, re.DOTALL):
                    try:
                        data = json.loads(m.group(1))
                        args = data.get("arguments") or data.get("args") or {}
                        recovered.append({
                            "name": tool_name,
                            "args": args,
                            "id": f"call_rec_{uuid.uuid4().hex[:8]}",
                            "type": "tool_call"
                        })
                    except Exception:
                        pass

    return recovered


def custom_agent_node(state: AgentState):
    provider, model = get_current_provider_and_model()
    llm = get_llm().bind_tools(core_tools.ALL_TOOLS)
    with console.status(f"[bold cyan]🤖 [{provider.upper()}:{model}] 파일 내용을 분석하고 분류 계획을 수립하고 있습니다...[/bold cyan]", spinner="dots"):
        response = llm.invoke(state["messages"])
    if response.content:
        console.print(f"\n  💭 [cyan]{response.content.strip()}[/cyan]")
    
    # 오픈소스 LLM 텍스트 누출 도구 호출 복구
    if not getattr(response, "tool_calls", None) and response.content:
        valid_tools = {t.name for t in core_tools.ALL_TOOLS}
        recovered = extract_fallback_tool_calls(response.content, valid_tools)
        if recovered:
            response.tool_calls = recovered
            console.print(f"  [dim]🛠️ 텍스트에서 {len(recovered)}개의 도구 호출을 복구했습니다.[/dim]")

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
            try:
                result = str(tool_impl.invoke(func_args))
            except Exception as e:
                result = f"오류: '{func_name}' 도구 실행 실패 ({type(e).__name__}): {e}"
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


def extract_category_from_text(text: str, user_request: str = "") -> str:
    """텍스트 및 사용자 요청에서 실제 카테고리명을 스마트하게 도출 (지시대명사 배제)"""
    category_map = [
        (["recipe", "recipes", "레시피", "요리", "쿠킹", "음식"], "Recipes"),
        (["travel", "여행", "휴가", "관광"], "Travel"),
        (["dev", "개발", "프로그래밍", "코드", "코딩"], "Dev"),
        (["finance", "재무", "가계부", "회계", "지출", "비용", "청구"], "Finance"),
        (["health", "건강", "운동", "루틴", "단식"], "Health"),
        (["book", "books", "독서", "책", "도서"], "Books"),
    ]
    combined = (user_request + " " + text).lower()
    for keywords, cat in category_map:
        if any(kw in combined for kw in keywords):
            return cat

    invalid_words = {"해당", "이", "그", "저", "위", "다음", "아래", "어떤", "지정된", "관련", "대상", "새로운", "임의의"}
    matches = re.findall(r'([A-Za-z0-9_가-힣]+)\s*폴더', text)
    for m in matches:
        if m not in invalid_words:
            return m

    return "Others"


def parse_text_proposals(text: str, target_dir: str, user_request: str = "") -> list[dict]:
    """오픈소스 LLM이 도구 호출 대신 한국어 텍스트로 파일 목록과 대상 폴더를 나열했을 때 계획 복구"""
    proposals = []
    default_cat = extract_category_from_text(text, user_request)
    
    lines = text.split("\n")
    for line in lines:
        m = re.search(r'[-*•]?\s*([a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]+)\s*[:\-]?\s*(.*)', line.strip())
        if m:
            fn, summary = m.group(1), m.group(2).strip()
            src_path = os.path.join(os.path.abspath(target_dir), fn)
            if os.path.exists(src_path):
                if any(p["source"] == src_path for p in core_tools.PROPOSALS) or any(p["source"] == src_path for p in proposals):
                    continue
                prefix = default_cat.lower().rstrip("s") + "_"
                ext = os.path.splitext(fn)[1]
                safe_name = re.sub(r'[^a-zA-Z0-9가-힣_]', '', summary.split()[0]) if summary else ""
                new_fn = f"{prefix}{safe_name}{ext}" if safe_name else fn
                proposals.append({
                    "source": src_path,
                    "destination_dir": os.path.join(os.path.abspath(target_dir), default_cat),
                    "new_filename": new_fn,
                    "category": default_cat,
                    "summary": summary or fn,
                    "tags": [default_cat],
                    "extracted_terms": {}
                })
    return proposals


def run_agent(user_request: str, target_dir: str, session_messages: list = None, agent_type: str = "FILE_ORGANIZER"):
    """LangGraph 기반 Agentic Loop"""
    
    if session_messages is None:
        core_tools.PROPOSALS.clear()
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
    
    # 텍스트로만 나열하고 도구 호출을 깜빡한 경우 자동 복구
    if not core_tools.PROPOSALS:
        for msg in reversed(final_state["messages"]):
            if getattr(msg, "content", None):
                recovered = parse_text_proposals(msg.content, target_dir, user_request)
                if recovered:
                    core_tools.PROPOSALS.extend(recovered)
                    console.print(f"\n[bold green]💡 AI 응답 텍스트에서 {len(recovered)}개의 정리 계획을 자동 감지하여 등록했습니다.[/bold green]")
                    break

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


def review_and_execute_proposals(use_tui: bool = True) -> str:
    """제안된 목록을 보여주고, 승인 시 실행(Human-in-the-loop)
    TUI 모드 지원 (터미널 환경 시), 미지원 시 텍스트 모드 fallback.
    반환값: "EXECUTED", "CANCELLED", 또는 피드백 텍스트(문자열)
    """
    if not core_tools.PROPOSALS:
        console.print("\n[dim]현재 실행할 제안이 없습니다.[/dim]")
        return "EXECUTED"

    # 1. Textual TUI 모드 (터미널 지원 시 기본 활성화)
    if use_tui and sys.stdin.isatty():
        try:
            from interfaces.tui import launch_tui_review
            action, selected = launch_tui_review(core_tools.PROPOSALS)
            if action == "EXECUTED":
                if not selected:
                    console.print("\n[yellow]선택된 제안 항목이 없습니다. (실행 건너뜀)[/yellow]")
                    core_tools.PROPOSALS.clear()
                    return "EXECUTED"
                console.print(f"\n[bold green]선택된 {len(selected)}개 항목 실행을 시작합니다...[/bold green]")
                core_tools.PROPOSALS = selected
                execute_all_pending_proposals(announce=False)
                console.print("\n[bold cyan]🎉 처리가 완료되었습니다. (되돌리려면 --undo 옵션을 사용하세요)[/bold cyan]")
                return "EXECUTED"
            elif action == "CANCELLED":
                console.print("\n[yellow]실행이 취소되었습니다.[/yellow]")
                core_tools.PROPOSALS.clear()
                return "CANCELLED"
            else:
                # 수정 재지시 피드백
                core_tools.PROPOSALS.clear()
                return action
        except Exception as e:
            console.print(f"[dim]TUI 실행 불가 ({e}), 텍스트 콘솔 모드로 전환합니다.[/dim]")

    # 2. 텍스트 콘솔 Fallback 모드
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

def run_interactive_agent_loop(request: str, target: str, use_tui: bool = True):
    """피드백 루프를 처리하는 래퍼 함수"""
    agent_type = run_supervisor(request)
    session = None
    curr_req = request
    
    while True:
        session = run_agent(curr_req, target, session_messages=session, agent_type=agent_type)
        feedback = review_and_execute_proposals(use_tui=use_tui)
        
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


def apply_field_mask(proposals: list[dict], fields: list[str] | None) -> list[dict]:
    """에이전트 컨텍스트 창 절약을 위한 필드 마스크 필터링"""
    if not fields:
        return proposals
    return [{k: p[k] for k in fields if k in p} for p in proposals]


def main():
    parser = argparse.ArgumentParser(description="File Organizer AI Agent v2")
    parser.add_argument("--watch", "-w", action="store_true", help="지정된 폴더를 실시간 감시 모드로 실행합니다.")
    parser.add_argument("--undo", action="store_true", help="가장 마지막으로 실행한 파일 정리 작업을 복구합니다.")
    
    # AI 에이전트를 위한 새로운 플래그 추가
    parser.add_argument("--json", type=str, help="작업 요청을 단일 JSON 문자열 페이로드로 제공합니다 (에이전트용).")
    parser.add_argument("--output", choices=["text", "json", "ndjson"], default="text", help="출력 형식을 지정합니다.")
    parser.add_argument("--schema", action="store_true", help="이 CLI의 입력 및 출력 설명에 대한 JSON Schema를 반환합니다.")
    parser.add_argument("--dry-run", action="store_true", help="실제 파일을 이동/변경하지 않고 계획만 생성/출력합니다.")
    parser.add_argument("--provider", choices=["ollama", "openai"], default=None, help="사용할 LLM 프로바이더 (기본값: .env 설정 또는 ollama).")
    parser.add_argument("--model", type=str, default=None, help="사용할 모델명 (예: qwen2.5:14b, gpt-4o).")
    parser.add_argument("--fields", type=str, default=None, help="출력 JSON/NDJSON에서 포함할 필드 마스크 (쉼표 구분, 예: 'source,new_filename,category').")
    parser.add_argument("--search", type=str, default=None, help="정리된 파일 내용 및 메타데이터를 자연어로 시맨틱 검색합니다.")
    parser.add_argument("--index", type=str, nargs="?", const=".", default=None, help="지정된 디렉토리의 파일들을 시맨틱 검색용으로 일괄 색인화합니다 (기본값: 현재 디렉토리).")
    parser.add_argument("--no-tui", action="store_true", help="인터랙티브 모드에서 Textual TUI를 비활성화하고 기본 텍스트 콘솔을 사용합니다.")
    
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    # 1. 시맨틱 검색 실행
    if args.search:
        from core import search
        query = args.search
        console.print(f"\n🔍 [bold cyan]'{query}' 시맨틱 검색 중...[/bold cyan]")
        results = search.search_documents(query)
        if not results:
            console.print("[yellow]검색 결과가 없습니다. 먼저 디렉토리를 색인화해보세요: python agent.py --index [폴더경로][/yellow]")
        else:
            table = Table(title=f"🔎 검색 결과: '{query}'")
            table.add_column("순위", justify="right", style="cyan")
            table.add_column("파일명", style="magenta")
            table.add_column("카테고리", style="blue")
            table.add_column("관련도", justify="right", style="green")
            table.add_column("내용 요약", style="yellow")
            table.add_column("파일 경로", style="dim")
            for i, r in enumerate(results):
                table.add_row(
                    str(i + 1),
                    r["filename"],
                    r["category"],
                    f"{int(r['score'] * 100)}%",
                    r["summary"][:60],
                    r["path"]
                )
            console.print(table)
        sys.exit(0)

    # 2. 일괄 색인화(Indexing) 실행
    if args.index:
        from core import search
        target = args.index
        console.print(f"\n📚 [bold cyan]'{target}' 디렉토리 문서 색인화 중...[/bold cyan]")
        n = search.index_directory(target)
        console.print(f"✅ [bold green]총 {n}개 파일 색인화 완료![/bold green] (이제 --search 로 검색 가능)")
        sys.exit(0)

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
                    },
                    "provider": {
                        "type": "string",
                        "enum": ["ollama", "openai"],
                        "description": "사용할 LLM 프로바이더 (ollama 또는 openai)"
                    },
                    "model": {
                        "type": "string",
                        "description": "사용할 모델명 (예: qwen2.5:14b, gpt-4o)"
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "컨텍스트 창 절약을 위한 반환 필드 마스크 목록 (예: ['source', 'destination_dir', 'new_filename'])"
                    }
                },
                "required": ["request", "target_dir"]
            },
            "returns": {
                "type": "array",
                "description": "생성된 파일 이동 및 정리 제안(Proposal) 목록",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "원본 파일 절대 경로"},
                        "destination_dir": {"type": "string", "description": "이동할 대상 디렉토리 경로"},
                        "new_filename": {"type": "string", "description": "변경될 새 파일명"},
                        "category": {"type": "string", "description": "분류된 카테고리"},
                        "summary": {"type": "string", "description": "파일 내용 요약"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "연관 태그 목록"},
                        "extracted_terms": {"type": "object", "description": "RAG 추출 전문 용어 사전"}
                    }
                }
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
        if payload.get("provider"):
            os.environ["LLM_PROVIDER"] = payload["provider"]
        if payload.get("model"):
            os.environ["LLM_MODEL"] = payload["model"]
        
        # 필드 마스크 추출 (CLI 옵션 우선, JSON 페이로드 차선)
        fields = None
        if args.fields:
            fields = [f.strip() for f in args.fields.split(",") if f.strip()]
        elif payload.get("fields"):
            raw_fields = payload.get("fields")
            if isinstance(raw_fields, list):
                fields = [str(f).strip() for f in raw_fields if str(f).strip()]
            elif isinstance(raw_fields, str):
                fields = [f.strip() for f in raw_fields.split(",") if f.strip()]

        if not target or not request:
            sys.stderr.write(json.dumps({"error": "Missing required fields: target_dir, request"}) + "\n")
            sys.exit(1)
            
        if not agent_type:
            agent_type = run_supervisor(request)
            
        # 에이전트 실행
        run_agent(request, target, session_messages=None, agent_type=agent_type)
        
        # 출력 형식이 JSON / NDJSON 인 경우 필드 마스킹 적용
        output_proposals = apply_field_mask(core_tools.PROPOSALS, fields)
        if args.output == "json":
            sys.stdout.write(json.dumps(output_proposals, ensure_ascii=False, indent=2) + "\n")
        elif args.output == "ndjson":
            for p in output_proposals:
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
    console.print("[dim](Enter = 현재 디렉토리, q = 종료)[/dim]")
    
    attempts = 0
    target = ""
    while attempts < 3:
        raw_target = input("  📂 경로: ").strip()
        if raw_target.lower() in ["q", "quit", "exit", "취소", ":q"]:
            console.print("\n[dim]프로그램을 종료합니다.[/dim]")
            sys.exit(0)
        target = raw_target or "."
        
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
    console.print("[dim](Enter = 기본 요청 사용, q = 종료)[/dim]")
    request = input("  💬 요청: ").strip()

    if request.lower() in ["q", "quit", "exit", "취소", ":q"]:
        console.print("\n[dim]작업을 취소하고 프로그램을 종료합니다.[/dim]")
        sys.exit(0)

    if not request:
        request = "파일 내용을 읽고 카테고리를 파악해서 적절한 폴더로 분류하고, 같은 분류의 파일들은 일관된 네이밍 규칙으로 제목을 수정해줘."

    if args.watch:
        watch_mode(target, request)
    else:
        run_interactive_agent_loop(request, target, use_tui=not args.no_tui)

if __name__ == "__main__":
    main()
