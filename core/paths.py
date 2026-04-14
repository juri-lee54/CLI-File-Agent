"""프로젝트에서 쓰는 공통 경로."""

from pathlib import Path


def demo_folder_path() -> Path:
    """시연용 파일이 생성·사용되는 폴더: ./demo_folder"""
    return Path("./demo_folder").resolve()


def demo_folder_str() -> str:
    return str(demo_folder_path())
