"""
Multimodal Document Parser Subsystem
===================================
다양한 문서 및 미디어 포맷(PDF, Word, Excel/CSV, 이미지)의 본문 및 메타데이터를
추출하여 LLM 에이전트가 이해할 수 있는 텍스트로 변환합니다.
"""

import csv
import os
from pathlib import Path


def parse_pdf(file_path: str, max_chars: int = 2000) -> str:
    """PDF 파일에서 텍스트 및 페이지 정보를 추출합니다."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        meta = reader.metadata
        title = meta.title if meta and meta.title else os.path.basename(file_path)

        extracted_text = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                extracted_text.append(f"--- [Page {i + 1}/{total_pages}] ---\n{text.strip()}")
            if sum(len(t) for t in extracted_text) >= max_chars:
                break

        full_content = "\n\n".join(extracted_text)
        truncated = len(full_content) > max_chars
        content_preview = full_content[:max_chars]

        return (
            f"[PDF 문서: {os.path.basename(file_path)} | 제목: {title} | 총 {total_pages}페이지]\n"
            f"{content_preview}"
            f"{'\n... (내용 일부 생략)' if truncated else ''}"
        )
    except Exception as e:
        return f"[PDF 파싱 오류: {os.path.basename(file_path)}] - {e}"


def parse_docx(file_path: str, max_chars: int = 2000) -> str:
    """Word (.docx) 파일에서 문단 및 표 내용을 추출합니다."""
    try:
        import docx

        doc = docx.Document(file_path)
        lines = []

        # 문단 추출
        for p in doc.paragraphs:
            text = p.text.strip()
            if text:
                # 스타일이 Heading인 경우 강조
                if p.style and p.style.name.startswith("Heading"):
                    lines.append(f"## {text}")
                else:
                    lines.append(text)
            if sum(len(l) for l in lines) >= max_chars:
                break

        # 표 내용 일부 추출 (문단이 적은 경우)
        if sum(len(l) for l in lines) < max_chars and doc.tables:
            lines.append("\n[포함된 표 내용]")
            for table in doc.tables[:3]:
                for row in table.rows[:5]:
                    row_text = " | ".join(c.text.strip() for c in row.cells if c.text.strip())
                    if row_text:
                        lines.append(f"| {row_text} |")

        full_content = "\n".join(lines)
        truncated = len(full_content) > max_chars
        return (
            f"[Word 문서: {os.path.basename(file_path)} | 총 {len(doc.paragraphs)}단락, {len(doc.tables)}개 표]\n"
            f"{full_content[:max_chars]}"
            f"{'\n... (내용 일부 생략)' if truncated else ''}"
        )
    except Exception as e:
        return f"[Word 파싱 오류: {os.path.basename(file_path)}] - {e}"


def parse_spreadsheet(file_path: str, max_chars: int = 2000) -> str:
    """Excel (.xlsx, .xls) 또는 CSV 파일에서 시트 구성 및 대표 데이터를 추출합니다."""
    ext = Path(file_path).suffix.lower()

    # CSV 처리
    if ext == ".csv":
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                rows = [row for i, row in enumerate(reader) if i < 15]
            if not rows:
                return f"[CSV 파일: {os.path.basename(file_path)} - 빈 파일]"

            header = " | ".join(rows[0])
            preview_rows = [" | ".join(r) for r in rows[1:10]]
            return (
                f"[CSV 스프레드시트: {os.path.basename(file_path)} | 열: {len(rows[0])}개]\n"
                f"헤더: {header}\n"
                f"샘플 데이터:\n" + "\n".join(preview_rows)
            )
        except Exception as e:
            return f"[CSV 파싱 오류: {os.path.basename(file_path)}] - {e}"

    # Excel 처리
    try:
        import openpyxl

        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        sheet_names = wb.sheetnames
        active_sheet = wb[sheet_names[0]]

        rows = []
        for i, row in enumerate(active_sheet.iter_rows(values_only=True)):
            if i >= 15:
                break
            filtered = [str(val).strip() for val in row if val is not None]
            if filtered:
                rows.append(" | ".join(filtered))

        wb.close()
        return (
            f"[Excel 문서: {os.path.basename(file_path)} | 시트 목록: {', '.join(sheet_names)}]\n"
            f"주요 시트 ('{sheet_names[0]}') 샘플:\n" + "\n".join(rows)
        )
    except Exception as e:
        return f"[Excel 파싱 오류: {os.path.basename(file_path)}] - {e}"


def parse_image(file_path: str, max_chars: int = 2000) -> str:
    """이미지 파일(PNG, JPG, WEBP 등)의 해상도, 포맷, Exif 메타데이터를 분석합니다."""
    try:
        from PIL import Image, ExifTags

        with Image.open(file_path) as img:
            w, h = img.size
            img_format = img.format or Path(file_path).suffix.upper().lstrip(".")

            info_lines = [
                f"[이미지 미디어: {os.path.basename(file_path)} | 포맷: {img_format} | 해상도: {w}x{h} px]"
            ]

            # EXIF 추출 (촬영일시, 카메라 기기, GPS)
            exif = img.getexif()
            if exif:
                exif_details = []
                for tag_id, value in exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if tag_name in ["DateTimeOriginal", "DateTime", "Make", "Model", "Software"]:
                        exif_details.append(f"- {tag_name}: {value}")
                if exif_details:
                    info_lines.append("메타데이터 (촬영 정보):")
                    info_lines.extend(exif_details[:5])

            info_lines.append(
                f"설명: 이 파일은 {img_format} 형식의 이미지입니다. 파일명과 메타데이터(크기, 촬영 정보)를 기반으로 적절한 이미지/미디어 폴더로 분류하세요."
            )

            return "\n".join(info_lines)
    except Exception as e:
        return f"[이미지 파싱 오류: {os.path.basename(file_path)}] - {e}"


def parse_plain_text(file_path: str, max_chars: int = 2000) -> str:
    """일반 텍스트 및 소스 코드 파일을 인코딩 자동 감지하여 읽습니다."""
    for encoding in ["utf-8", "utf-8-sig", "cp949", "euc-kr"]:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read(max_chars)
            truncated = len(content) == max_chars
            header = f"[텍스트 파일: {os.path.basename(file_path)} | 인코딩: {encoding}]"
            footer = "\n... (내용 생략)" if truncated else ""
            return f"{header}\n{content}{footer}"
        except (UnicodeDecodeError, LookupError):
            continue
    return f"오류: '{file_path}' 인코딩을 인식할 수 없습니다"


def parse_file_content(file_path: str, max_chars: int = 2000) -> str:
    """
    파일 확장자 및 내용에 따라 최적의 파서로 분기하여 텍스트를 반환합니다.
    """
    if not os.path.exists(file_path):
        return f"오류: 파일이 존재하지 않습니다: {file_path}"
    if os.path.isdir(file_path):
        return f"오류: 디렉토리입니다: {file_path}"

    ext = Path(file_path).suffix.lower()

    if ext == ".pdf":
        return parse_pdf(file_path, max_chars)
    elif ext in [".docx", ".doc"]:
        return parse_docx(file_path, max_chars)
    elif ext in [".xlsx", ".xls", ".csv", ".xlsm"]:
        return parse_spreadsheet(file_path, max_chars)
    elif ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".svg"]:
        return parse_image(file_path, max_chars)
    else:
        # 일반 텍스트 및 코드 파일 처리
        return parse_plain_text(file_path, max_chars)

