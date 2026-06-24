import os
import threading
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, BooleanVar, StringVar, Tk, filedialog, messagebox
from tkinter import ttk

from core import DEFAULT_MODEL, call_openai, extract_pdf_text, mask_sensitive_text, scan_prohibited_expressions


APP_TITLE = "판결문 기반 네이버 블로그 글 생성기"


class BlogWriterApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1040x760")
        self.pdf_path = StringVar()
        self.api_key = StringVar(value=os.getenv("OPENAI_API_KEY", ""))
        self.model = StringVar(value=DEFAULT_MODEL)
        self.status = StringVar(value="PDF 판결문을 선택하고 API Key를 입력해 주세요.")
        self.mask_before_send = BooleanVar(value=True)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=BOTH, expand=True)

        top = ttk.Frame(outer)
        top.pack(fill=X)

        ttk.Label(top, text="OpenAI API Key").pack(anchor="w")
        key_row = ttk.Frame(top)
        key_row.pack(fill=X, pady=(4, 10))
        ttk.Entry(key_row, textvariable=self.api_key, show="*", width=80).pack(side=LEFT, fill=X, expand=True)
        ttk.Label(key_row, text="Model").pack(side=LEFT, padx=(12, 4))
        ttk.Entry(key_row, textvariable=self.model, width=18).pack(side=LEFT)

        file_row = ttk.Frame(top)
        file_row.pack(fill=X, pady=(0, 10))
        ttk.Entry(file_row, textvariable=self.pdf_path).pack(side=LEFT, fill=X, expand=True)
        self.pdf_button = ttk.Button(file_row, text="PDF 선택", command=self.choose_pdf)
        self.pdf_button.pack(side=LEFT, padx=(8, 0))
        ttk.Checkbutton(file_row, text="API 전송 전 민감정보 자동 마스킹", variable=self.mask_before_send).pack(
            side=LEFT, padx=(12, 0)
        )

        action_row = ttk.Frame(top)
        action_row.pack(fill=X, pady=(0, 10))
        self.generate_button = ttk.Button(action_row, text="블로그 글 생성", command=self.generate)
        self.generate_button.pack(side=LEFT)
        ttk.Button(action_row, text="결과 저장", command=self.save_result).pack(side=LEFT, padx=(8, 0))
        ttk.Button(action_row, text="결과 지우기", command=self.clear_result).pack(side=LEFT, padx=(8, 0))
        ttk.Label(action_row, textvariable=self.status).pack(side=LEFT, padx=(16, 0))

        panes = ttk.PanedWindow(outer, orient="horizontal")
        panes.pack(fill=BOTH, expand=True)

        left = ttk.Frame(panes, padding=(0, 0, 8, 0))
        right = ttk.Frame(panes, padding=(8, 0, 0, 0))
        panes.add(left, weight=1)
        panes.add(right, weight=1)

        ttk.Label(left, text="추출/마스킹된 판결문 텍스트").pack(anchor="w")
        self.source_text = self._text_box(left)

        ttk.Label(right, text="생성된 네이버 블로그 글").pack(anchor="w")
        self.result_text = self._text_box(right)

    def _text_box(self, parent: ttk.Frame):
        frame = ttk.Frame(parent)
        frame.pack(fill=BOTH, expand=True, pady=(4, 0))
        text = __import__("tkinter").Text(frame, wrap="word", undo=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill="y")
        return text

    def choose_pdf(self) -> None:
        path = filedialog.askopenfilename(title="판결문 PDF 선택", filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        self.pdf_path.set(path)
        self.status.set("PDF 분석 중입니다. 스캔본이면 OpenAI OCR을 사용합니다...")
        self.pdf_button.configure(state="disabled")
        self.generate_button.configure(state="disabled")
        self.source_text.delete("1.0", END)
        thread = threading.Thread(
            target=self._extract_pdf_worker,
            args=(path, self.api_key.get().strip(), self.model.get().strip()),
            daemon=True,
        )
        thread.start()

    def _extract_pdf_worker(self, path: str, api_key: str, model: str) -> None:
        try:
            extracted = extract_pdf_text(
                path,
                api_key=api_key,
                model=model or DEFAULT_MODEL,
                progress_callback=self._ocr_progress,
            )
            preview = mask_sensitive_text(extracted) if self.mask_before_send.get() else extracted
            self.root.after(0, self._show_extracted_pdf, preview)
        except Exception as exc:
            self.root.after(0, self._show_extract_error, str(exc))

    def _ocr_progress(self, completed: int, total: int) -> None:
        self.root.after(0, self.status.set, f"OpenAI OCR 처리 중... {completed}/{total}페이지")

    def _show_extracted_pdf(self, preview: str) -> None:
        self.source_text.delete("1.0", END)
        self.source_text.insert(END, preview)
        self.status.set("PDF 텍스트를 준비했습니다.")
        self.pdf_button.configure(state="normal")
        self.generate_button.configure(state="normal")

    def _show_extract_error(self, message: str) -> None:
        self.status.set("PDF 추출 실패")
        self.pdf_button.configure(state="normal")
        self.generate_button.configure(state="normal")
        messagebox.showerror(APP_TITLE, message)

    def generate(self) -> None:
        api_key = self.api_key.get().strip()
        if not api_key:
            messagebox.showwarning(APP_TITLE, "OpenAI API Key를 입력해 주세요.")
            return
        if not self.pdf_path.get():
            messagebox.showwarning(APP_TITLE, "판결문 PDF를 선택해 주세요.")
            return

        current_text = self.source_text.get("1.0", END).strip()
        if not current_text:
            messagebox.showwarning(APP_TITLE, "추출된 판결문 텍스트가 없습니다.")
            return

        judgment_text = mask_sensitive_text(current_text) if self.mask_before_send.get() else current_text
        self.source_text.delete("1.0", END)
        self.source_text.insert(END, judgment_text)

        self.generate_button.configure(state="disabled")
        self.status.set("ChatGPT API로 글을 생성 중입니다...")
        thread = threading.Thread(target=self._generate_worker, args=(api_key, self.model.get().strip(), judgment_text), daemon=True)
        thread.start()

    def _generate_worker(self, api_key: str, model: str, judgment_text: str) -> None:
        try:
            result = call_openai(api_key, model or DEFAULT_MODEL, judgment_text)
            prohibited = scan_prohibited_expressions(result)
            if prohibited:
                result += "\n\n[자동 경고]\n다음 광고 리스크 표현이 감지되었습니다. 게시 전 수정하세요: "
                result += ", ".join(prohibited)
            self.root.after(0, self._show_result, result)
        except Exception as exc:
            self.root.after(0, self._show_error, str(exc))

    def _show_result(self, result: str) -> None:
        self.result_text.delete("1.0", END)
        self.result_text.insert(END, result)
        self.status.set("생성이 완료되었습니다. 게시 전 변호사 검수를 진행하세요.")
        self.generate_button.configure(state="normal")

    def _show_error(self, message: str) -> None:
        self.status.set("생성 실패")
        self.generate_button.configure(state="normal")
        messagebox.showerror(APP_TITLE, message)

    def save_result(self) -> None:
        result = self.result_text.get("1.0", END).strip()
        if not result:
            messagebox.showwarning(APP_TITLE, "저장할 결과가 없습니다.")
            return
        default_name = "naver_blog_draft.txt"
        if self.pdf_path.get():
            default_name = f"{Path(self.pdf_path.get()).stem}_blog_draft.txt"
        path = filedialog.asksaveasfilename(
            title="결과 저장",
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[("Text files", "*.txt")],
        )
        if not path:
            return
        Path(path).write_text(result, encoding="utf-8")
        self.status.set(f"저장 완료: {path}")

    def clear_result(self) -> None:
        self.result_text.delete("1.0", END)
        self.status.set("결과를 지웠습니다.")


def main() -> None:
    root = Tk()
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    BlogWriterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
