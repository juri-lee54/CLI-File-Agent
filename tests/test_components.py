import os
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core import parsers, search
from tools import core_tools
from agent import apply_field_mask


class TestFileAgentComponents(unittest.TestCase):

    def test_security_safe_output_dir(self):
        """보안 경로 탐색 및 제어 문자 필터링 테스트"""
        self.assertTrue(core_tools.validate_safe_output_dir("demo_folder/sub"))
        self.assertTrue(core_tools.validate_safe_output_dir("/Users/test/folder"))
        # 위험 경로 차단
        self.assertFalse(core_tools.validate_safe_output_dir("../secret.txt"))
        self.assertFalse(core_tools.validate_safe_output_dir("folder/../../etc/passwd"))
        self.assertFalse(core_tools.validate_safe_output_dir("folder/\x00nullbyte"))
        self.assertFalse(core_tools.validate_safe_output_dir("folder/test?query=1"))
        self.assertFalse(core_tools.validate_safe_output_dir("folder/%2e%2e/evil"))

    def test_multimodal_parsers(self):
        """멀티모달 파서 테스트 (DOCX, XLSX, CSV, JPG, TXT)"""
        demo_dir = Path("demo_folder")
        if not demo_dir.exists():
            self.skipTest("demo_folder not found")

        # 1. Word DOCX
        docx_path = demo_dir / "contract_q3.docx"
        if docx_path.exists():
            docx_text = parsers.parse_file_content(str(docx_path))
            self.assertIn("Word 문서", docx_text)
            self.assertIn("계약서", docx_text)

        # 2. Excel XLSX
        xlsx_path = demo_dir / "sales_2024.xlsx"
        if xlsx_path.exists():
            xlsx_text = parsers.parse_file_content(str(xlsx_path))
            self.assertIn("Excel 문서", xlsx_text)
            self.assertIn("호스팅", xlsx_text)

        # 3. CSV
        csv_path = demo_dir / "invoice_q3.csv"
        if csv_path.exists():
            csv_text = parsers.parse_file_content(str(csv_path))
            self.assertIn("CSV 스프레드시트", csv_text)
            self.assertIn("AWS Hosting Fee", csv_text)

        # 4. Image JPG
        jpg_path = demo_dir / "vacation_kyoto.jpg"
        if jpg_path.exists():
            jpg_text = parsers.parse_file_content(str(jpg_path))
            self.assertIn("이미지 미디어", jpg_text)
            self.assertIn("JPEG", jpg_text)

    def test_field_mask(self):
        """에이전트 필드 마스크 필터링 테스트"""
        sample_proposals = [
            {
                "source": "/path/a.txt",
                "destination_dir": "/path/Recipes",
                "new_filename": "recipe_a.txt",
                "category": "Recipes",
                "summary": "긴 요약문...",
                "tags": ["tag1", "tag2"]
            }
        ]
        masked = apply_field_mask(sample_proposals, ["source", "new_filename", "category"])
        self.assertEqual(len(masked), 1)
        self.assertEqual(list(masked[0].keys()), ["source", "new_filename", "category"])
        self.assertNotIn("summary", masked[0])
        self.assertNotIn("tags", masked[0])

    def test_semantic_search(self):
        """로컬 시맨틱 검색 테스트"""
        results = search.search_documents("호스팅 비용", target_dir="demo_folder", top_k=3)
        self.assertIsInstance(results, list)
        if results:
            self.assertIn("filename", results[0])
            self.assertIn("score", results[0])
            self.assertGreater(results[0]["score"], 0)

    def test_scan_directory_contents(self):
        """디렉토리 일괄 내용 스캔 도구 테스트"""
        res = core_tools.tool_scan_directory_contents.invoke({"path": "demo_folder", "max_files": 5})
        self.assertIn("일괄 내용 스캔 결과", res)
        self.assertIn("📄 [", res)

    def test_tui_app(self):
        """Textual TUI 검토 앱 실행 및 엔터 키 바인딩 테스트"""
        import asyncio
        from interfaces.tui import ProposalReviewApp

        sample_proposals = [
            {
                "source": "/Users/test/doc1.txt",
                "destination_dir": "/Users/test/Recipes",
                "new_filename": "recipe_tiramisu.txt",
                "category": "Recipes",
                "summary": "티라미수 레시피",
                "tags": ["레시피"]
            }
        ]
        app = ProposalReviewApp(sample_proposals)

        async def run_pilot():
            async with app.run_test() as pilot:
                self.assertEqual(app.query_one("#proposal-table").row_count, 1)
                await pilot.press("enter")
            self.assertEqual(app.result_action, "EXECUTED")

        asyncio.run(run_pilot())


if __name__ == "__main__":
    unittest.main()
