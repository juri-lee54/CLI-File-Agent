"""
Textual Interactive TUI Dashboard
=================================
터미널에서 AI의 파일 정리/이동 제안을 시각적으로 확인하고,
스페이스바/클릭으로 개별 항목을 선별 승인/취소할 수 있는 대화형 TUI 인터페이스입니다.
"""

import os
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.coordinate import Coordinate
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static


class ProposalReviewApp(App):
    """파일 정리 제안 검토 Textual 애플리케이션"""

    CSS = """
    Screen {
        background: #1e1e2e;
    }
    #main-container {
        padding: 1 2;
        height: 1fr;
    }
    #title-box {
        margin-bottom: 1;
        background: #313244;
        color: #cdd6f4;
        padding: 1 2;
        border: solid #89b4fa;
        text-align: center;
        text-style: bold;
    }
    DataTable {
        height: 1fr;
        border: solid #45475a;
        background: #181825;
    }
    #feedback-container {
        display: none;
        height: auto;
        padding: 1;
        background: #313244;
        border: solid #f9e2af;
        margin-top: 1;
    }
    #action-bar {
        dock: bottom;
        height: 3;
        background: #11111b;
        padding: 0 1;
        align: center middle;
    }
    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("space", "toggle_select", "선택 토글", priority=True),
        Binding("a", "toggle_all", "전체 선택/해제"),
        Binding("enter", "confirm_execution", "선택 실행"),
        Binding("r", "toggle_feedback", "수정 재지시"),
        Binding("q", "cancel", "취소"),
        Binding("escape", "cancel", "취소"),
    ]

    def __init__(self, proposals: list[dict]):
        super().__init__()
        self.proposals = proposals
        self.selected_indices = set(range(len(proposals)))  # 기본적으로 전체 선택
        self.result_action = "CANCELLED"
        self.user_feedback = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main-container"):
            yield Static(
                "📋 [bold cyan]AI 파일 정리 제안 검토[/bold cyan]\n"
                "[dim]스페이스바로 실행할 항목을 선택/해제한 후 [Enter]를 누르면 선택 항목만 적용됩니다.[/dim]",
                id="title-box",
            )
            yield DataTable(id="proposal-table")

            with Vertical(id="feedback-container"):
                yield Label("💬 AI에게 수정 지시사항을 입력하세요 (Enter로 전송):")
                yield Input(placeholder="예: 레시피 폴더명을 Cooking으로 바꿔서 다시 가져와", id="feedback-input")

        with Horizontal(id="action-bar"):
            yield Button("✅ 선택 항목 실행 [Enter]", variant="success", id="btn-execute")
            yield Button("💬 수정 재지시 [R]", variant="warning", id="btn-feedback")
            yield Button("❌ 전체 취소 [Q]", variant="error", id="btn-cancel")

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("선택", "번호", "원본 파일명", "새 대상 폴더/파일명", "카테고리", "요약")

        for i, p in enumerate(self.proposals):
            checked = "✅ [X]" if i in self.selected_indices else "⬜ [ ]"
            src_name = os.path.basename(p["source"])
            dest = f"{os.path.basename(p['destination_dir'])}/{p['new_filename']}"
            summary = p.get("summary", "").replace("\n", " ")[:40]
            table.add_row(
                checked,
                str(i + 1),
                src_name,
                dest,
                p.get("category", "-"),
                summary,
                key=str(i),
            )

    def refresh_table_row(self, row_idx: int):
        table = self.query_one(DataTable)
        checked = "✅ [X]" if row_idx in self.selected_indices else "⬜ [ ]"
        p = self.proposals[row_idx]
        src_name = os.path.basename(p["source"])
        dest = f"{os.path.basename(p['destination_dir'])}/{p['new_filename']}"
        summary = p.get("summary", "").replace("\n", " ")[:40]
        table.update_cell_at(Coordinate(row_idx, 0), checked)

    def action_toggle_select(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self.proposals):
            idx = table.cursor_row
            if idx in self.selected_indices:
                self.selected_indices.remove(idx)
            else:
                self.selected_indices.add(idx)
            self.refresh_table_row(idx)

    def action_toggle_all(self) -> None:
        if len(self.selected_indices) == len(self.proposals):
            self.selected_indices.clear()
        else:
            self.selected_indices = set(range(len(self.proposals)))
        for i in range(len(self.proposals)):
            self.refresh_table_row(i)

    def action_confirm_execution(self) -> None:
        fb_box = self.query_one("#feedback-container")
        if fb_box.styles.display == "block":
            return
        self.result_action = "EXECUTED"
        self.exit()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_confirm_execution()

    def action_toggle_feedback(self) -> None:
        fb_box = self.query_one("#feedback-container")
        fb_input = self.query_one("#feedback-input", Input)
        if fb_box.styles.display == "none":
            fb_box.styles.display = "block"
            fb_input.focus()
        else:
            fb_box.styles.display = "none"

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            self.result_action = text
            self.exit()

    def action_cancel(self) -> None:
        self.result_action = "CANCELLED"
        self.exit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-execute":
            self.action_confirm_execution()
        elif event.button.id == "btn-feedback":
            self.action_toggle_feedback()
        elif event.button.id == "btn-cancel":
            self.action_cancel()


def launch_tui_review(proposals: list[dict]) -> tuple[str, list[dict]]:
    """
    TUI 검토 화면을 띄워 사용자의 결정을 수신합니다.
    반환값: (결과 액션["EXECUTED", "CANCELLED", 피드백문자열], 선택된 제안 목록)
    """
    if not proposals:
        return "EXECUTED", []

    app = ProposalReviewApp(proposals)
    app.run()

    if app.result_action == "EXECUTED":
        selected = [p for i, p in enumerate(proposals) if i in app.selected_indices]
        return "EXECUTED", selected
    elif app.result_action == "CANCELLED":
        return "CANCELLED", []
    else:
        # 사용자가 피드백 텍스트를 입력하고 전송한 경우
        return app.result_action, []

