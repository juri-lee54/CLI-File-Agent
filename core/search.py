"""
Local Semantic Search & Desktop RAG
====================================
정리된 파일들의 메타데이터와 본문을 SQLite 기반 벡터 저장소에 인덱싱하고,
자연어 질의(Semantic Search)를 통해 가장 관련 있는 파일을 순위별로 검색합니다.
"""

import json
import math
import os
import sqlite3
import urllib.request
from pathlib import Path
from core import parsers

INDEX_DB_NAME = ".agent_index.sqlite"


def get_db_path(base_dir: str = None) -> str:
    """인덱스 데이터베이스 파일 경로를 반환합니다 (미지정 시 하위 폴더 자동 탐색)."""
    if base_dir:
        target = os.path.abspath(base_dir)
        if os.path.isfile(target) and target.endswith(".sqlite"):
            return target
        parent = os.path.dirname(target)
        if os.path.basename(target) in ["Recipes", "Travel", "Dev", "Finance", "Health", "Books", "Others", "Cooking", "Documents", "Images"]:
            return os.path.join(parent, INDEX_DB_NAME)
        return os.path.join(target, INDEX_DB_NAME)

    cur = os.path.join(os.getcwd(), INDEX_DB_NAME)
    if os.path.exists(cur):
        return cur

    # 하위 디렉토리(.agent_index.sqlite) 탐색
    for item in os.listdir(os.getcwd()):
        sub_path = os.path.join(os.getcwd(), item)
        if os.path.isdir(sub_path) and not item.startswith("."):
            candidate = os.path.join(sub_path, INDEX_DB_NAME)
            if os.path.exists(candidate):
                return candidate

    return cur


def init_db(db_path: str):
    """SQLite 인덱스 테이블 초기화"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE,
            filename TEXT,
            category TEXT,
            summary TEXT,
            tags TEXT,
            content_preview TEXT,
            embedding TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def get_embedding(text: str, model: str = None) -> list[float] | None:
    """
    Ollama Embeddings API를 호출하여 텍스트의 벡터 임베딩을 추출합니다.
    실패하거나 오프라인일 경우 None을 반환(어휘 기반 fallback 전환).
    """
    if not text.strip():
        return None

    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    # /v1/embeddings 또는 /api/embeddings 호출
    endpoint = ollama_url.replace("/v1", "") + "/api/embeddings"
    target_model = model or os.getenv("EMBED_MODEL", "nomic-embed-text")

    payload = {
        "model": target_model,
        "prompt": text[:1000]
    }

    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("embedding")
    except Exception:
        # Ollama 임베딩 모델 미지원 또는 연결 불가 시 None 반환
        return None


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """두 벡터 간의 코사인 유사도를 계산합니다."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def fallback_text_similarity(query: str, doc_text: str) -> float:
    """임베딩이 없을 때 단어 빈도 기반 유사도 계산 (Fallback)"""
    q_words = set(query.lower().split())
    d_words = doc_text.lower().split()
    if not q_words or not d_words:
        return 0.0
    matches = sum(1 for w in d_words if w in q_words)
    return matches / (len(d_words) + 5)


def index_file(
    file_path: str,
    category: str = "",
    summary: str = "",
    tags: list = None,
    db_path: str = None
):
    """단일 파일을 파싱하여 SQLite 색인에 저장합니다."""
    if not os.path.isfile(file_path):
        return

    db = db_path or get_db_path(os.path.dirname(os.path.abspath(file_path)))
    init_db(db)

    tags = tags or []
    tags_str = ", ".join(tags)
    content = parsers.parse_file_content(file_path, max_chars=1500)
    preview = content[:500].replace("\n", " ")

    # 임베딩용 텍스트 합성
    index_text = f"{os.path.basename(file_path)} {category} {summary} {tags_str} {content[:1000]}"
    vec = get_embedding(index_text)
    vec_json = json.dumps(vec) if vec else None

    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO documents (path, filename, category, summary, tags, content_preview, embedding, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(path) DO UPDATE SET
            filename=excluded.filename,
            category=excluded.category,
            summary=excluded.summary,
            tags=excluded.tags,
            content_preview=excluded.content_preview,
            embedding=excluded.embedding,
            updated_at=CURRENT_TIMESTAMP
    """, (
        os.path.abspath(file_path),
        os.path.basename(file_path),
        category,
        summary,
        tags_str,
        preview,
        vec_json
    ))
    conn.commit()
    conn.close()


def index_directory(target_dir: str) -> int:
    """디렉토리 내의 모든 문서를 일괄 색인화합니다."""
    target_dir = os.path.abspath(target_dir)
    db = get_db_path(target_dir)
    init_db(db)

    count = 0
    for root, dirs, files in os.walk(target_dir):
        # 숨김 폴더 무시
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.startswith(".") or f == INDEX_DB_NAME:
                continue
            full_path = os.path.join(root, f)
            index_file(full_path, db_path=db)
            count += 1

    return count


def search_documents(query: str, target_dir: str = None, top_k: int = 5) -> list[dict]:
    """
    자연어 질의(query)를 바탕으로 관련성 높은 문서를 순위별로 반환합니다.
    """
    db = get_db_path(target_dir)
    if not os.path.exists(db):
        return []

    query_vec = get_embedding(query)

    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("SELECT path, filename, category, summary, tags, content_preview, embedding FROM documents")
    rows = cur.fetchall()
    conn.close()

    results = []
    for r in rows:
        path, filename, cat, summary, tags, preview, emb_str = r
        score = 0.0

        if query_vec and emb_str:
            try:
                doc_vec = json.loads(emb_str)
                score = cosine_similarity(query_vec, doc_vec)
            except Exception:
                score = 0.0
        else:
            # Fallback text similarity
            full_text = f"{filename} {cat} {summary} {tags} {preview}"
            score = fallback_text_similarity(query, full_text)

        # 키워드 및 구문 직접 매칭 가산점
        q_lower = query.lower().strip()
        combined_text = f"{filename} {cat} {summary} {tags} {preview}".lower()
        if len(q_lower) >= 2 and q_lower in combined_text:
            score += 0.3

        for word in q_lower.split():
            if len(word) < 2:
                continue
            if word in filename.lower():
                score += 0.25
            if word in summary.lower():
                score += 0.2
            if word in preview.lower():
                score += 0.2
            if word in cat.lower():
                score += 0.15

        results.append({
            "filename": filename,
            "path": path,
            "category": cat or "(미지정)",
            "summary": summary or preview[:80],
            "tags": tags,
            "score": round(score, 3)
        })

    # 유사도 내림차순 정렬
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]
