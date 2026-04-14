"""
Demo Setup Script (v2)
======================
내용 기반 분류 시연용 - 다양한 실제 내용이 담긴 파일 생성

파일명은 의도적으로 모호/무관하게 설정 → Agent가 내용을 읽고 분류 + 제목 변경

기본 출력 위치: 바탕화면의 demo_folder (~/Desktop/demo_folder)
"""

import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.paths import demo_folder_path

# ══════════════════════════════════════════════════════
# 시연용 파일 목록
# 의도적으로 파일명 ≠ 내용 (Agent가 내용을 읽어야 분류 가능)
# ══════════════════════════════════════════════════════
DEMO_FILES = {

    # ── 요리 레시피 ────────────────────────────────────
    "document1.txt": """\
티라미수 만드는 법

재료 (4인분 기준):
- 마스카포네 치즈 250g
- 달걀노른자 3개
- 설탕 80g
- 에스프레소 200ml (식힌 것)
- 레이디핑거 비스킷 200g
- 코코아 파우더 (마무리용)
- 럼 또는 아마레토 2큰술 (선택)

만드는 순서:
1. 달걀노른자와 설탕을 거품기로 뽀얗게 될 때까지 휘핑한다.
2. 마스카포네 치즈를 넣고 부드럽게 섞는다.
3. 에스프레소에 럼을 섞어 비스킷을 빠르게 적신다.
4. 용기에 비스킷 → 크림 → 비스킷 → 크림 순으로 층을 쌓는다.
5. 냉장고에서 최소 4시간 이상 굳힌다.
6. 먹기 직전 코코아 파우더를 체에 걸러 뿌린다.

Tip: 달걀흰자를 머랭 쳐서 크림에 접으면 훨씬 가볍고 폭신한 식감이 납니다.
""",

    "notes_random.txt": """\
된장찌개 황금 레시피

기본 육수:
- 멸치 10마리 + 다시마 1장을 찬물 1L에 넣고 끓인다
- 끓기 시작하면 중불로 줄이고 10분간 더 끓인 뒤 건더기를 건진다

재료:
- 된장 3큰술, 고추장 0.5큰술
- 두부 반 모 (깍둑썰기)
- 애호박 반 개 (반달썰기)
- 감자 1개 (깍둑썰기)
- 대파 1대, 청양고추 1개
- 다진 마늘 1큰술

조리법:
1. 육수에 된장과 고추장을 풀어 넣는다.
2. 감자를 먼저 넣고 5분간 끓인다.
3. 두부, 호박, 마늘을 넣고 3분간 더 끓인다.
4. 파와 고추를 넣고 한소끔 더 끓이면 완성.

핵심 포인트: 된장은 마지막에 추가하면 향이 날아가므로 초반에 넣을 것.
""",

    "temp_001.md": """\
# 초간단 아보카도 토스트 레시피

## 준비물
- 사워도우 빵 2장
- 잘 익은 아보카도 1개
- 레몬즙 1/2개 분량
- 소금, 후추
- 레드페퍼 플레이크 (취향껏)
- 달걀 (선택: 포치드 에그)

## 순서
1. 빵을 노릇하게 굽는다.
2. 아보카도를 으깨고 레몬즙, 소금, 후추로 간한다.
3. 구운 빵 위에 아보카도를 펴 바른다.
4. 포치드 에그를 올리고 레드페퍼로 마무리.

> 아보카도는 갈변이 빠르니 만들자마자 먹을 것!
""",

    # ── 여행 일기 ──────────────────────────────────────
    "file_a.txt": """\
교토 여행기 — 2024년 봄

벚꽃이 만개한 마루야마 공원을 걸었다. 수백 년 된 수양벚나무 아래
돗자리를 펴고 앉은 현지인들의 모습이 마치 오래된 우키요에 그림 같았다.

기온 거리의 새벽은 고요했다. 오차야의 나무 격자문 사이로 샤미센 소리가
흘러나왔고, 마이코 한 명이 종종걸음으로 골목을 빠져나갔다.
사진을 찍으려 카메라를 들었지만 그냥 눈으로만 담기로 했다.

후시미 이나리 신사는 새벽 5시에 갔다. 수천 개의 도리이가 이어지는
산길을 거의 혼자 걸었는데, 안개가 자욱해서 도리이 너머가 보이지 않았다.
그 신비로움은 사진으로는 절대 전달이 안 된다.

3박 4일이 짧게 느껴진 건 오랜만이었다.
""",

    "untitled_doc.txt": """\
바르셀로나, 그 도시의 색깔

가우디의 건축물은 사진보다 실물이 훨씬 압도적이다.
사그라다 파밀리아 앞에서 처음 10분은 그냥 멍하니 서 있었다.
건물이 살아있는 것처럼 보인다는 말이 과장이 아니었다.

보케리아 시장에서 하몽을 얇게 썰어주던 노인의 손놀림,
람블라스 거리에서 플라멩코 공연을 보다 갑자기 쏟아진 소나기,
그리고 몬주익 언덕에서 내려다본 지중해의 색깔.

스페인은 감각적인 나라다.
음식, 소리, 색감 모든 것이 선명하고 뜨겁다.
""",

    "misc_2024.txt": """\
오사카 먹방 여행 3일 코스

1일차
- 아침: 난바 도톤보리에서 타코야키 (하나코타코 추천)
- 점심: 구로몬 시장 산책하며 신선한 해산물 꼬치
- 저녁: 우메다의 오코노미야키 전문점 "미즈노"

2일차
- 아침: 호텔 근처 모닝 커피와 타마고 산도
- 점심: 텐진바시스지 상점가의 우동 골목 탐방
- 저녁: 하루카스 전망대 레스토랑에서 야경과 함께

3일차
- 아침: 공항 가기 전 신오사카역의 551 호라이 돼지만두 必구매
- 쇼핑: 편의점 신상 디저트 싹쓸이

총평: 오사카는 먹으러 가는 도시가 맞다. 위장이 더 컸으면 좋겠다.
""",

    # ── 기술/개발 노트 ──────────────────────────────────
    "doc_final.txt": """\
Python 비동기 프로그래밍 핵심 정리

async/await 기본 구조:
- async def로 선언된 함수는 코루틴 객체를 반환
- await는 코루틴 내부에서만 사용 가능
- asyncio.run()으로 이벤트 루프 실행

자주 쓰는 패턴:

1. 여러 작업 동시 실행:
   results = await asyncio.gather(task1(), task2(), task3())

2. 타임아웃 적용:
   async with asyncio.timeout(5.0):
       result = await some_slow_operation()

3. 비동기 컨텍스트 매니저:
   async with aiohttp.ClientSession() as session:
       async with session.get(url) as response:
           data = await response.json()

주의사항:
- CPU 바운드 작업에는 asyncio 대신 multiprocessing 사용
- 블로킹 함수는 loop.run_in_executor()로 감싸기
- 예외 처리는 try/except를 각 코루틴 안에 배치
""",

    "notes_v2.txt": """\
Docker & Kubernetes 운영 노트

자주 쓰는 Docker 명령어:
- docker ps -a                    # 모든 컨테이너 확인
- docker logs -f [container_id]   # 실시간 로그 확인
- docker exec -it [id] /bin/bash  # 컨테이너 접속
- docker system prune -a          # 불필요한 리소스 정리

Kubernetes 트러블슈팅:
- kubectl get pods -n [namespace]
- kubectl describe pod [pod-name]
- kubectl logs [pod] --previous   # 크래시된 이전 로그

흔한 문제들:
1. CrashLoopBackOff → 앱 로직 오류나 환경변수 누락 확인
2. ImagePullBackOff → 이미지명 오타 또는 private registry 인증 문제
3. OOMKilled → resource.limits.memory 값 조정 필요

ConfigMap 핫 리로드:
- 볼륨 마운트 방식은 자동 반영 (약 1-2분 딜레이)
- 환경변수 방식은 pod 재시작 필요
""",

    "random_file.py": """\
#!/usr/bin/env python3
\"\"\"
간단한 할 일 관리 CLI 앱
\"\"\"
import json, os
from datetime import datetime

TODO_FILE = "todos.json"

def load_todos():
    if not os.path.exists(TODO_FILE):
        return []
    with open(TODO_FILE) as f:
        return json.load(f)

def save_todos(todos):
    with open(TODO_FILE, "w") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)

def add_todo(title, priority="medium"):
    todos = load_todos()
    todos.append({
        "id": len(todos) + 1,
        "title": title,
        "priority": priority,
        "done": False,
        "created": datetime.now().isoformat()
    })
    save_todos(todos)
    print(f"추가됨: {title}")

def list_todos():
    for t in load_todos():
        status = "완료" if t["done"] else "진행"
        print(f"[{status}] {t['id']}. {t['title']} ({t['priority']})")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        list_todos()
    elif sys.argv[1] == "add":
        add_todo(" ".join(sys.argv[2:]))
""",

    # ── 재무/투자 메모 ───────────────────────────────────
    "asdf.txt": """\
2024년 개인 재무 현황 정리

월 수입: 4,200,000원
월 고정지출:
  - 월세: 850,000
  - 관리비/공과금: 120,000
  - 통신비: 55,000
  - 보험료: 180,000
  - 구독서비스: 45,000
  소계: 1,250,000원

월 변동지출 (평균):
  - 식비: 400,000
  - 교통: 80,000
  - 여가/문화: 200,000
  - 의류/쇼핑: 150,000
  소계: 830,000원

순저축 가능액: 2,120,000원/월

투자 배분:
  - 주식 ETF (S&P500): 700,000/월
  - 국내 주식: 300,000/월
  - 적금: 500,000/월
  - 비상금 적립: 300,000/월
  - 자유 소비: 320,000/월
""",

    "project_x.txt": """\
ETF 투자 전략 노트 (2024 하반기)

핵심 원칙:
1. 지수 추종 ETF 중심 (개별 종목은 포트폴리오의 20% 이하)
2. 달러 비중 60% 유지 (환 헤지 목적)
3. 분기별 리밸런싱

주요 보유 ETF:
- VOO (S&P500): 비중 35%
- QQQ (나스닥100): 비중 15%
- SCHD (배당성장): 비중 10%
- TIGER 차이나항셍테크: 비중 5%
- KODEX 2차전지: 비중 5%

올해 수익률 (8월 기준): +14.3%
벤치마크(S&P500) 대비: +2.1%p 아웃퍼폼

다음 분기 조정 계획:
- QQQ 5% 축소 → SCHD로 이동 (변동성 리스크 줄이기)
- 국내 2차전지 비중 추가 검토
""",

    # ── 건강/운동 ────────────────────────────────────────
    "memo_draft.txt": """\
홈트레이닝 3분할 루틴

월/목 - 가슴 + 삼두
  - 푸시업 4세트 x 15회
  - 다이아몬드 푸시업 3세트 x 12회
  - 딥스 3세트 x 10회 (의자 이용)
  - 트라이셉스 킥백 3세트 x 15회

화/금 - 등 + 이두
  - 친업 4세트 x 8회
  - 밴드 로우 4세트 x 15회
  - 슈퍼맨 자세 3세트 x 20회
  - 밴드 컬 3세트 x 15회

수/토 - 하체 + 어깨 + 코어
  - 스쿼트 4세트 x 20회
  - 런지 3세트 x 15회(각)
  - 파이크 푸시업 3세트 x 12회
  - 플랭크 3세트 x 60초

일요일: 완전 휴식 또는 가벼운 스트레칭 30분

진행 상황: 8주차 — 친업 5→8개로 늘었고 체중 2kg 감량
""",

    "health_stuff.txt": """\
간헐적 단식 16:8 실천 일지

기본 규칙:
- 식사 가능 시간: 12:00 ~ 20:00
- 단식 시간: 20:00 ~ 다음날 12:00 (16시간)
- 단식 중 허용: 물, 아메리카노(설탕/크림 없음), 허브차

1주차 후기:
- 오전 11시쯤 배고픔이 심하지만 점차 적응됨
- 에너지 레벨은 오히려 더 안정적

3주차 후기:
- 공복감이 거의 없어짐
- 소화가 확실히 좋아진 느낌

2개월 결과:
- 체중: 74kg → 70.5kg (-3.5kg)
- 체지방률: 추정 23% → 20%대

주의: 격렬한 운동 날에는 식사 시간을 11:00~19:00으로 당기기
""",

    # ── 독서 메모 ────────────────────────────────────────
    "scan001.txt": """\
《총, 균, 쇠》 독서 메모 — 재레드 다이아몬드

핵심 주장:
왜 유럽인이 아메리카, 아프리카, 오세아니아를 정복했는가?
→ 인종적 우월함이 아니라 '지리적 행운'이 결정적이었다.

주요 논거:
1. 가축화 가능한 동물과 작물화 가능한 식물이 유라시아에 집중
   → 잉여 식량 → 전업 전사/관료/기술자 계층 발생

2. 유라시아의 동서 축(같은 위도) → 식물과 동물이 빠르게 전파
   아메리카/아프리카의 남북 축 → 기후 차이로 전파 느림

3. 가축에서 비롯된 천연두, 홍역 등의 전염병
   → 면역이 없는 원주민 인구의 90% 이상 사망

★★★★★ — 세계사를 보는 관점이 완전히 바뀌는 책
""",

    "page_notes.txt": """\
《원씽 (The One Thing)》 핵심 요약 — 게리 켈러

중심 질문:
"지금 내가 할 수 있는 한 가지는 무엇인가?
그것을 하면 다른 모든 것들이 쉬워지거나 불필요해지는?"

핵심 개념들:

1. 도미노 효과
   작은 한 가지가 더 큰 것을 쓰러뜨린다.

2. 성공의 거짓말들
   - 모든 것이 중요하다 (No → 일부만 중요)
   - 멀티태스킹 (No → 작업 전환 비용 존재)
   - 의지력은 항상 준비되어 있다 (No → 관리해야 할 자원)

3. 목적의식 있는 시간 블록
   - 하루 4시간을 '한 가지'에 집중
   - 방해를 차단하는 환경 설계가 핵심

실천: 내년 목표 → 월 목표 → 주 목표 → 오늘의 한 가지로 역산
""",

    # ── 기타 / 일상 / 업무 노트 ────────────────────────────────────
    "meeting_0912.txt": """\
주간 기획 회의 (9.12)
참석자: 김팀장, 이대리, 박사원

안건 1: 신규 앱 UI 개편 건
- 현재 플랫 디자인에서 뉴모피즘 요소 추가 논의
- 박사원: "반응형 애니메이션이 부족하다는 피드백이 많음. 애니메이션 추가 제안"
- 결론: 다음 주까지 A/B 테스트용 시안 2종 준비하기로 함.

안건 2: 송년회 워크샵 일정
- 12월 셋째 주 금요일 오후 반차 후 출발 예정
- 장소 후보: 가평 펜션 vs 서울 시내 호텔 파티룸
""",

    "scrap_insight.txt": """\
기획 아이디어 스크랩
- 구독 취소 페이지에서 '아쉽네요' 감성 터치 문구보다, 구독 유지 시 혜택을 수치화해서 보여주는 게 이탈 방지율이 15% 높음 (A회사 사례)
- 온보딩 과정은 무조건 3단계를 넘지 않게 만들 것.
- 향후 AI 비서 기능을 도입하려면 로그 데이터 정규화가 필수적임. 데이터 엔지니어 파트와 사전 조율 필요.
""",

    "invoice_q3.csv": """\
Date,Description,Amount,Status
2024-07-15,AWS Hosting Fee,-150.00,Paid
2024-08-01,Client A Project Deposit,5000.00,Received
2024-08-15,AWS Hosting Fee,-150.00,Paid
2024-09-05,Office Supplies,-85.50,Paid
2024-09-15,AWS Hosting Fee,-150.00,Pending
2024-09-30,Client A Project Final,5000.00,Pending
""",
}


def create_demo_environment():
    demo_path = demo_folder_path()

    if demo_path.exists():
        shutil.rmtree(demo_path)
    demo_path.mkdir(parents=True, exist_ok=True)

    print(f"\n📁 시연 환경 생성 중: '{demo_path}/'")
    print("─" * 55)

    for filename, content in DEMO_FILES.items():
        filepath = demo_path / filename
        filepath.write_text(content, encoding="utf-8")
        preview = content.strip().split('\n')[0][:38]
        print(f"  ✓ {filename:25s}  \"{preview}\"")

    print("─" * 55)
    print(f"\n✅ {len(DEMO_FILES)}개 파일 생성 완료! (파일명은 의도적으로 모호하게 설정)")
    print(f"\n예상 분류:")
    print(f"  🍳 Recipes/    3개 — 티라미수, 된장찌개, 아보카도 토스트")
    print(f"  ✈️  Travel/     3개 — 교토, 바르셀로나, 오사카")
    print(f"  💻 Dev/        3개 — Python 비동기, Docker/K8s, CLI 앱")
    print(f"  💰 Finance/    3개 — 월간 가계부, ETF 전략, 3분기 청구서(CSV)")
    print(f"  💪 Health/     2개 — 홈트레이닝, 간헐적 단식")
    print(f"  📚 Books/      2개 — 총균쇠, 원씽")
    print(f"  📦 Others/     2개 — 주간 회의록, 아이디어 스크랩")
    print(f"\n🚀 에이전트 실행 시 대상 경로: {demo_path}\n")


if __name__ == "__main__":
    create_demo_environment()
