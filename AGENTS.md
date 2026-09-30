---
name: file-organizer-cli
version: 1.1.0
description: "AI 에이전트를 위해 최적화된 파일 정리 및 분류 자동화 도구입니다. 대화형 인터페이스를 우회하고, JSON 페이로드 입출력, 필드 마스크, 런타임 스키마 조회를 지원하여 파싱 에러와 할루시네이션의 여지를 줄입니다."
usage:
  - "python agent.py --json '<JSON_PAYLOAD>' --output ndjson --dry-run"
  - "python agent.py --json '<JSON_PAYLOAD>' --fields 'source,destination_dir,new_filename' --output ndjson"
metadata:
  target_audience: "Autonomous AI Agents"
---

# File Organizer CLI - 에이전트 연동 가이드

`file_agent`는 사람과 에이전트 모두를 위해 고안된 유연한 파일 시스템 인터페이스입니다. 
당신이 AI 에이전트로서 이 도구를 사용할 경우, 데이터 유실과 파싱 오류를 방지하기 위해 다음 규칙을 **반드시** 따라야 합니다.

## 핵심 4가지 규칙

1. **대화형 모드(Interactive Mode)를 피할 것**
   사람용 프롬프트(`input()`)는 파싱하기 어렵고 언제 입력이 요구될지 예측 불가능합니다.
   반드시 `--json` 파라미터를 사용하여 단일 명령으로 모든 지시를 종결하십시오.

2. **출력을 강제할 것 (`--output ndjson` 혹은 `--output json`)**
   에이전트가 결과를 활용하기 위해서는 플랫 텍스트(테이블)가 아닌, 구조화된 응답이 필수입니다. 
   출력으로 생성되는 *Proposal* 목록을 완벽하게 파싱하기 위해 꼭 `--output ndjson`을 사용해 컨텍스트 창 메모리를 아끼세요.

3. **필드 마스크로 작업 기억(컨텍스트 창)을 아낄 것 (`--fields`)**
   모든 메타데이터가 필요하지 않다면 `--fields "source,destination_dir,new_filename"` 플래그를 지정하여 필요한 필드만 수신하세요.
   불필요한 요약문이나 태그가 컨텍스트 창을 채우는 것을 방지합니다.

4. **파괴적 작업 도입 전 검열 (`--dry-run`)**
   실제 파일 이동이 발생하기 전, 에이전트의 로직이 원하는 방향인지 테스트하십시오.
   예: `python agent.py --json '{"request": "명세서 정리해", "target_dir": "./data"}' --dry-run --output json`

## 주요 명령어 사용법

### 1. 사용 가능한 스키마 확인하기
런타임에서 입력 매개변수와 반환 Proposal 스키마를 직접 조회합니다.
```bash
python agent.py --schema
```

### 2. 에이전트 모드로 실행 (단일 명령)
`request`와 `target_dir`는 필수 필드입니다.
```bash
python agent.py --json '{"request": "Recipes 폴더로 텍스트 문서들 내용 읽어서 이동해", "target_dir": "./demo_folder"}' --fields "source,destination_dir,new_filename,category" --output ndjson
```

## 안전 장치 (Validation & Sanitization)

- **경로 탐색 공격 방지**: 에이전트가 생성하는 대상 경로(`target_dir`, `destination_dir`)에 `../` 또는 `%00` 등이 포함될 경우 `validate_safe_output_dir`에 의해 실행이 거부됩니다.
- **제어 문자 금지**: ASCII 0x00 ~ 0x1F 사이의 제어 문자가 파라미터에 들어올 경우 파싱이 중단되고 실패 처리됩니다.
- **명령어 새니타이징**: `--json` 안에서 넘어온 `sudo` 혹은 `rm -rf` 등 파괴적인 서브 쉘 구문은 보안 필터에 의해 자동차단됩니다.
- **프롬프트 인젝션 격리**: 파일 내용을 읽을 때 악성 시스템 지시문이 침투하지 못하도록 `<untrusted_file_content>` 샌드박싱 태그로 감싸 안전하게 처리합니다.
