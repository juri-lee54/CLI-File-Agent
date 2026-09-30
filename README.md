# File Organizer AI Agent 

단순히 확장자(`*.txt`, `*.jpg`)에 의존해 폴더를 분류하는 기존의 방식을 넘어선 **진정한 형태의 지능형 파일 정리 에이전트**입니다. 

LangGraph 기반의 AI 에이전트가 지정된 폴더 안의 파일들을 직접 열어 내용을 읽고(Reading), 그 문맥에 맞춰 목적과 카테고리를 추론한 뒤, 일관된 네이밍 규칙을 부여하여 자동으로 폴더를 정리합니다.

이제 **OpenAI API 없이도 로컬 오픈소스 LLM(Ollama + Qwen 2.5)**을 통해 **비용 0원, 완전 오프라인, 100% 프라이버시 보호** 환경에서 동작합니다.

---

## 주요 특징 (Key Features)

- **로컬 오픈소스 LLM & 멀티 프로바이더 지원 (NEW):**
  - **Ollama (`qwen2.5:14b`, `qwen2.5:7b` 등)**: API 비용 0원, 쿼터 제한 없이 내 컴퓨터에서 안전하게 로컬 실행.
  - **OpenAI (`gpt-4o`)**: 필요 시 `.env` 또는 `--provider openai`로 손쉽게 전환 가능.
- **내용 기반 분류 (Content-based Reasoning):** 
  - `document1.txt`, `temp_001.md` 같이 이름이 무작위여도 파일 내부의 텍스트가 '파이썬 코드'인지 '갈비찜 레시피'인지 스스로 읽고 파악합니다.
- **Human-in-the-loop (승인 기반 실행):** 
  - AI가 혼자 사고 치지 않도록, 정리할 파일 목록과 이동 경로를 미리 테이블 형태로 사용자에게 제안(Proposal)하고 `[y/n]` 승인을 받습니다. (수정 지시도 가능)
- **실시간 감시 (Watchdog Mode):** 
  - 특정 폴더(예: 다운로드 폴더)를 백그라운드에서 상시 감시하여, 새 파일이 들어오는 즉시 사용자의 개입 없이 자동으로 정리합니다.
- **지식 추출 (RAG Extractor):**
  - 단순 이동뿐만 아니라 "문서에서 IT 기술 용어만 추출해줘"라고 명령하면 문서 내의 핵심 지식을 뽑아 메타데이터(`.agent_metadata.json`)로 축적합니다.
- **타임머신 복구 (Undo):** 
  - 정리 결과가 마음에 들지 않거나 실수가 발생하면 단축 명령어 한 번으로 완벽하게 **실행 취소(Rollback)** 할 수 있습니다.

---

## 설치 및 설정

### 1. 가상 환경 구축 및 패키지 설치
파이썬 3.10 이상의 환경을 권장합니다. (Python 3.12 권장)

```bash
# 가상 환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# 의존성 패키지 설치
pip install -r requirements.txt
```

### 2. LLM 엔진 설정

#### 방법 A: 로컬 오픈소스 Ollama 사용 (추천, 완전 무료/무제한)
```bash
# 1) Ollama 설치 및 백그라운드 서비스 시작 (macOS)
brew install ollama
brew services start ollama

# 2) 추천 모델 다운로드 (Qwen 2.5 14B 또는 7B)
ollama pull qwen2.5:14b
# 또는 ollama pull qwen2.5:7b
```

`.env` 파일에 다음과 같이 설정합니다 (기본값):
```env
LLM_PROVIDER="ollama"
LLM_MODEL="qwen2.5:14b"
OLLAMA_BASE_URL="http://localhost:11434/v1"
```

#### 방법 B: OpenAI API 사용 (선택)
```env
LLM_PROVIDER="openai"
LLM_MODEL="gpt-4o"
OPENAI_API_KEY="sk-여러분들의-발급받은-키"
```

---

## 사용 방법

### 1. 기본 대화형 모드 (수동 정리)
CLI에서 인터랙티브하게 AI와 소통하며 파일 정리를 지시합니다. 승인을 받아야만 실제로 파일이 이동됩니다.
```bash
python agent.py
```
> 실행 후 정리할 디렉토리 경로와 희망하는 정리 방식(예: "레시피랑 개발 문서로 나눠줘")을 입력합니다.

### 2. 프로바이더 / 모델 지정 실행
CLI 옵션으로 프로바이더나 모델을 즉석에서 바꿀 수 있습니다.
```bash
# 로컬 Qwen 2.5 7B로 실행
python agent.py --provider ollama --model qwen2.5:7b

# OpenAI로 실행
python agent.py --provider openai --model gpt-4o
```

### 3. 실시간 자동 모드 (배치 백그라운드 감시)
지정 폴더를 상시 감시하며 새 파일이 생성되면 자동으로 정리합니다.
```bash
python agent.py --watch
```

### 4. 복구 모드 (실행 취소 / Undo)
최근 AI가 실행한 이동 작업을 원상태로 안전하게 되돌립니다.
```bash
python agent.py --undo
```
> 직전 1건만 되돌릴 것인지, 전체 내역을 영구 복구시킬 것인지 선택할 수 있습니다.

### 5. 에이전트/자동화 연동 모드 (Headless JSON)
자율 에이전트 및 CI/CD 연동을 위해 JSON 입출력과 `--dry-run`을 지원합니다.
```bash
python agent.py --json '{"request": "문서 내용 읽고 분류해줘", "target_dir": "./demo_folder"}' --dry-run --output json
```

---

## 기술 스택 (Architecture)

- **언어:** Python 3.12+
- **LLM 프레임워크:** LangChain, LangGraph
- **지원 AI 모델:** 
  - 로컬 오픈소스: `Qwen 2.5 (14B / 7B)`, `Llama 3.1 / 3.3` (via Ollama)
  - 클라우드: OpenAI `gpt-4o`, `gpt-4o-mini`
- **인터페이스 & 시스템 제어:** `rich` (CLI UI), `watchdog` (파일시스템 감시)
- **에이전트 프로토콜:** Model Context Protocol (FastMCP)
