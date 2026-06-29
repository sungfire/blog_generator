from datetime import datetime
import os
import threading
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, BooleanVar, IntVar, StringVar, Tk, filedialog, messagebox
from tkinter import ttk

from config_store import delete_api_key, load_api_key, save_api_key
from content_tools import CTA_TEMPLATES, PRACTICE_TEMPLATES, build_ad_risk_report, build_seo_checklist
from core import (
    DEFAULT_MODEL,
    call_openai,
    convert_markdown_to_naver_text,
    extract_pdf_text,
    generate_blog_images,
    mask_sensitive_text,
    save_naver_html,
    scan_prohibited_expressions,
)


APP_TITLE = "판결문 기반 네이버 블로그 글 생성기"


class BlogWriterApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1040x760")
        self.pdf_path = StringVar()
        self.api_key = StringVar(value=os.getenv("OPENAI_API_KEY", "") or load_api_key())
        self.model = StringVar(value=DEFAULT_MODEL)
        self.status = StringVar(value="PDF 판결문을 선택하고 API Key를 입력해 주세요.")
        self.file_status = StringVar(value="PDF가 선택되지 않았습니다.")
        self.mask_before_send = BooleanVar(value=True)
        self.generate_images = BooleanVar(value=False)
        self.image_count = IntVar(value=2)
        self.practice_area = StringVar()
        self.target_reader = StringVar()
        self.region_keyword = StringVar()
        self.firm_name = StringVar()
        self.cta_method = StringVar(value="사건 검토 요청")
        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16, style="App.TFrame")
        outer.pack(fill=BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        header = ttk.Frame(outer, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="판결문 PDF를 분석해 SEO 블로그 글, 검수 리포트, 네이버 붙여넣기용 결과를 생성합니다.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        cards = ttk.Frame(outer, style="App.TFrame")
        cards.grid(row=1, column=0, sticky="ew")
        cards.columnconfigure(0, weight=1)
        cards.columnconfigure(1, weight=1)

        settings_card = ttk.LabelFrame(cards, text="설정", padding=12, style="Card.TLabelframe")
        settings_card.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 10))
        settings_card.columnconfigure(1, weight=1)
        ttk.Label(settings_card, text="OpenAI API Key", style="Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(settings_card, textvariable=self.api_key, show="*", width=44).grid(row=0, column=1, sticky="ew")
        ttk.Button(settings_card, text="저장", command=self.save_key, style="Secondary.TButton", width=8).grid(
            row=0, column=2, padx=(8, 4)
        )
        ttk.Button(settings_card, text="삭제", command=self.delete_key, style="Danger.TButton", width=8).grid(row=0, column=3)
        ttk.Label(settings_card, text="모델", style="Field.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(10, 0))
        ttk.Entry(settings_card, textvariable=self.model, width=22).grid(row=1, column=1, sticky="w", pady=(10, 0))

        file_card = ttk.LabelFrame(cards, text="파일", padding=12, style="Card.TLabelframe")
        file_card.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 10))
        file_card.columnconfigure(0, weight=1)
        ttk.Entry(file_card, textvariable=self.pdf_path).grid(row=0, column=0, sticky="ew")
        self.pdf_button = ttk.Button(file_card, text="PDF 선택", command=self.choose_pdf, style="Primary.TButton", width=12)
        self.pdf_button.grid(row=0, column=1, padx=(8, 0))
        ttk.Checkbutton(
            file_card,
            text="API 전송 전 민감정보 자동 마스킹",
            variable=self.mask_before_send,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(file_card, textvariable=self.file_status, style="StatusHint.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        content_card = ttk.LabelFrame(cards, text="콘텐츠 설정", padding=12, style="Card.TLabelframe")
        content_card.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(0, 10))
        for index in range(6):
            content_card.columnconfigure(index, weight=1)
        ttk.Label(content_card, text="작성 분야", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            content_card,
            textvariable=self.practice_area,
            values=list(PRACTICE_TEMPLATES.keys()),
            width=15,
        ).grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(4, 10))
        ttk.Label(content_card, text="타깃 독자", style="Field.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Entry(content_card, textvariable=self.target_reader, width=18).grid(
            row=1, column=1, sticky="ew", padx=(0, 8), pady=(4, 10)
        )
        ttk.Label(content_card, text="지역 키워드", style="Field.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Entry(content_card, textvariable=self.region_keyword, width=16).grid(
            row=1, column=2, sticky="ew", padx=(0, 8), pady=(4, 10)
        )
        ttk.Label(content_card, text="변호사/법무법인명", style="Field.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Entry(content_card, textvariable=self.firm_name, width=24).grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=(0, 8), pady=(4, 0)
        )
        ttk.Label(content_card, text="상담 CTA", style="Field.TLabel").grid(row=2, column=2, sticky="w")
        ttk.Combobox(
            content_card,
            textvariable=self.cta_method,
            values=list(CTA_TEMPLATES.keys()),
            width=18,
        ).grid(row=3, column=2, sticky="ew", padx=(0, 8), pady=(4, 0))
        ttk.Checkbutton(content_card, text="본문 이미지 생성", variable=self.generate_images).grid(
            row=2, column=3, sticky="w", padx=(8, 8)
        )
        ttk.Label(content_card, text="이미지 수", style="Field.TLabel").grid(row=2, column=4, sticky="w")
        ttk.Spinbox(content_card, from_=1, to=5, textvariable=self.image_count, width=5).grid(
            row=3, column=4, sticky="w", pady=(4, 0)
        )

        action_card = ttk.LabelFrame(cards, text="작업", padding=12, style="Card.TLabelframe")
        action_card.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(0, 10))
        for index in range(3):
            action_card.columnconfigure(index, weight=1)
        self.generate_button = ttk.Button(
            action_card, text="블로그 글 생성", command=self.generate, style="Primary.TButton", width=18
        )
        self.generate_button.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 8))
        ttk.Button(action_card, text="검수 리포트", command=self.append_review_report, style="Secondary.TButton", width=18).grid(
            row=0, column=1, sticky="ew", padx=(0, 8), pady=(0, 8)
        )
        ttk.Button(action_card, text="결과 저장", command=self.save_result, style="Secondary.TButton", width=18).grid(
            row=0, column=2, sticky="ew", pady=(0, 8)
        )
        ttk.Button(action_card, text="네이버용 복사", command=self.copy_naver_text, style="Secondary.TButton", width=18).grid(
            row=1, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(
            action_card, text="HTML 미리보기 저장", command=self.save_html_preview, style="Secondary.TButton", width=18
        ).grid(row=1, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(action_card, text="결과 지우기", command=self.clear_result, style="Danger.TButton", width=18).grid(
            row=1, column=2, sticky="ew"
        )

        body_card = ttk.LabelFrame(outer, text="본문", padding=10, style="Card.TLabelframe")
        body_card.grid(row=3, column=0, sticky="nsew", pady=(2, 10))
        body_card.columnconfigure(0, weight=1)
        body_card.rowconfigure(0, weight=1)
        self.notebook = ttk.Notebook(body_card)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        source_tab = ttk.Frame(self.notebook, padding=8)
        source_tab.columnconfigure(0, weight=1)
        source_tab.rowconfigure(1, weight=1)
        ttk.Label(source_tab, text="추출/마스킹된 판결문 텍스트", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        source_box, self.source_text = self._text_box(source_tab)
        source_box.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.notebook.add(source_tab, text="판결문 텍스트")

        result_tab = ttk.Frame(self.notebook, padding=8)
        result_tab.columnconfigure(0, weight=1)
        result_tab.rowconfigure(1, weight=1)
        ttk.Label(result_tab, text="생성된 네이버 블로그 글", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        result_box, self.result_text = self._text_box(result_tab)
        result_box.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.notebook.add(result_tab, text="생성 결과")

        status_bar = ttk.Frame(outer, padding=(10, 6), style="Status.TFrame")
        status_bar.grid(row=4, column=0, sticky="ew")
        ttk.Label(status_bar, textvariable=self.status, style="Status.TLabel").pack(anchor="w")

    def _text_box(self, parent: ttk.Frame):
        frame = ttk.Frame(parent, style="TextWrap.TFrame")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        text = __import__("tkinter").Text(
            frame,
            wrap="word",
            undo=True,
            font=("Malgun Gothic", 10),
            padx=12,
            pady=10,
            spacing1=2,
            spacing3=5,
            relief="flat",
            borderwidth=0,
            background="#ffffff",
            foreground="#1f2937",
            insertbackground="#1f2937",
        )
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        return frame, text

    def choose_pdf(self) -> None:
        path = filedialog.askopenfilename(title="판결문 PDF 선택", filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        api_key = self.api_key.get().strip()
        if api_key:
            save_api_key(api_key)
        self.pdf_path.set(path)
        self.file_status.set("PDF 분석 중입니다. 텍스트 추출 또는 OCR을 준비합니다.")
        self.status.set("PDF 분석 중입니다. 스캔본이면 OpenAI OCR을 사용합니다...")
        self.pdf_button.configure(state="disabled")
        self.generate_button.configure(state="disabled")
        self.source_text.delete("1.0", END)
        thread = threading.Thread(
            target=self._extract_pdf_worker,
            args=(path, api_key, self.model.get().strip()),
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
        self.root.after(0, self.file_status.set, f"OpenAI OCR 처리 중... {completed}/{total}페이지")
        self.root.after(0, self.status.set, f"OpenAI OCR 처리 중... {completed}/{total}페이지")

    def _show_extracted_pdf(self, preview: str) -> None:
        self.source_text.delete("1.0", END)
        self.source_text.insert(END, preview)
        self.file_status.set("PDF 텍스트가 준비되었습니다.")
        self.status.set("PDF 텍스트를 준비했습니다.")
        self.pdf_button.configure(state="normal")
        self.generate_button.configure(state="normal")

    def _show_extract_error(self, message: str) -> None:
        self.file_status.set("PDF 추출에 실패했습니다.")
        self.status.set("PDF 추출 실패")
        self.pdf_button.configure(state="normal")
        self.generate_button.configure(state="normal")
        messagebox.showerror(APP_TITLE, message)

    def generate(self) -> None:
        api_key = self.api_key.get().strip()
        if not api_key:
            messagebox.showwarning(APP_TITLE, "OpenAI API Key를 입력해 주세요.")
            return
        save_api_key(api_key)
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
        thread = threading.Thread(
            target=self._generate_worker,
            args=(
                api_key,
                self.model.get().strip(),
                judgment_text,
                self.generate_images.get(),
                self.image_count.get(),
                self.practice_area.get(),
                self.target_reader.get(),
                self.region_keyword.get(),
                self.firm_name.get(),
                self.cta_method.get(),
            ),
            daemon=True,
        )
        thread.start()

    def _generate_worker(
        self,
        api_key: str,
        model: str,
        judgment_text: str,
        should_generate_images: bool,
        image_count: int,
        practice_area: str,
        target_reader: str,
        region_keyword: str,
        firm_name: str,
        cta_method: str,
    ) -> None:
        try:
            result = call_openai(
                api_key,
                model or DEFAULT_MODEL,
                judgment_text,
                practice_area=practice_area,
                target_reader=target_reader,
                region_keyword=region_keyword,
                firm_name=firm_name,
                cta_method=cta_method,
            )
            prohibited = scan_prohibited_expressions(result)
            if prohibited:
                result += "\n\n[자동 경고]\n다음 광고 리스크 표현이 감지되었습니다. 게시 전 수정하세요: "
                result += ", ".join(prohibited)
            if should_generate_images:
                self.root.after(0, self.status.set, "본문 이미지 생성 중입니다...")
                output_dir = self._image_output_dir()
                image_paths = generate_blog_images(
                    api_key,
                    result,
                    output_dir,
                    count=image_count,
                    progress_callback=self._image_progress,
                )
                result = self._append_image_section(result, image_paths)
            self.root.after(0, self._show_result, result)
        except Exception as exc:
            self.root.after(0, self._show_error, str(exc))

    def _image_output_dir(self) -> Path:
        pdf_stem = Path(self.pdf_path.get()).stem if self.pdf_path.get() else "blog"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return Path.cwd() / "outputs" / f"{pdf_stem}_{timestamp}_images"

    def _image_progress(self, completed: int, total: int) -> None:
        self.root.after(0, self.status.set, f"본문 이미지 생성 중... {completed}/{total}장")

    def _append_image_section(self, result: str, image_paths: list[Path]) -> str:
        if not image_paths:
            return result
        locations = ["도입부 아래", "핵심 쟁점 설명 뒤", "상담 안내 문구 앞", "본문 중간", "마무리 전"]
        lines = ["", "", "[생성 이미지]", "아래 이미지를 네이버 블로그 본문 중간에 업로드해 사용하세요."]
        for index, path in enumerate(image_paths, start=1):
            location = locations[index - 1] if index <= len(locations) else "본문 중간"
            lines.append(f"{index}. 삽입 권장 위치: {location}")
            lines.append(f"   파일: {path}")
            lines.append(f"   마크다운 미리보기: ![블로그 삽입 이미지 {index}]({path})")
        return result + "\n".join(lines)

    def _show_result(self, result: str) -> None:
        self.result_text.delete("1.0", END)
        self.result_text.insert(END, result)
        self.notebook.select(1)
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

    def copy_naver_text(self) -> None:
        result = self.result_text.get("1.0", END).strip()
        if not result:
            messagebox.showwarning(APP_TITLE, "복사할 결과가 없습니다.")
            return
        naver_text = convert_markdown_to_naver_text(result)
        self.root.clipboard_clear()
        self.root.clipboard_append(naver_text)
        self.root.update()
        self.status.set("네이버 붙여넣기용 텍스트를 클립보드에 복사했습니다.")

    def append_review_report(self) -> None:
        result = self.result_text.get("1.0", END).strip()
        if not result:
            messagebox.showwarning(APP_TITLE, "검사할 결과가 없습니다.")
            return
        report = "\n\n" + build_ad_risk_report(result) + "\n\n" + build_seo_checklist(result, self.region_keyword.get())
        self.result_text.insert(END, report)
        self.status.set("광고 규정 리스크 및 SEO 체크리스트를 추가했습니다.")

    def save_html_preview(self) -> None:
        result = self.result_text.get("1.0", END).strip()
        if not result:
            messagebox.showwarning(APP_TITLE, "저장할 결과가 없습니다.")
            return
        default_name = "naver_blog_preview.html"
        if self.pdf_path.get():
            default_name = f"{Path(self.pdf_path.get()).stem}_naver_preview.html"
        path = filedialog.asksaveasfilename(
            title="HTML 미리보기 저장",
            defaultextension=".html",
            initialfile=default_name,
            filetypes=[("HTML files", "*.html")],
        )
        if not path:
            return
        save_naver_html(result, Path(path))
        self.status.set(f"HTML 미리보기 저장 완료: {path}")

    def clear_result(self) -> None:
        self.result_text.delete("1.0", END)
        self.status.set("결과를 지웠습니다.")

    def save_key(self) -> None:
        api_key = self.api_key.get().strip()
        if not api_key:
            messagebox.showwarning(APP_TITLE, "저장할 OpenAI API Key를 입력해 주세요.")
            return
        save_api_key(api_key)
        self.status.set("API Key를 로컬에 저장했습니다.")

    def delete_key(self) -> None:
        delete_api_key()
        self.api_key.set("")
        self.status.set("저장된 API Key를 삭제했습니다.")


def main() -> None:
    root = Tk()
    root.minsize(1120, 780)
    root.configure(background="#f3f5f7")
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    configure_styles(style)
    BlogWriterApp(root)
    root.mainloop()


def configure_styles(style: ttk.Style) -> None:
    style.configure("App.TFrame", background="#f3f5f7")
    style.configure("Status.TFrame", background="#e8edf3")
    style.configure("TextWrap.TFrame", background="#d5dbe3", borderwidth=1, relief="solid")
    style.configure("Title.TLabel", background="#f3f5f7", foreground="#111827", font=("Malgun Gothic", 18, "bold"))
    style.configure("Subtitle.TLabel", background="#f3f5f7", foreground="#667085", font=("Malgun Gothic", 10))
    style.configure("Section.TLabel", foreground="#111827", font=("Malgun Gothic", 10, "bold"))
    style.configure("Field.TLabel", foreground="#344054", font=("Malgun Gothic", 9))
    style.configure("StatusHint.TLabel", foreground="#667085", font=("Malgun Gothic", 9))
    style.configure("Status.TLabel", background="#e8edf3", foreground="#344054", font=("Malgun Gothic", 9))
    style.configure("Card.TLabelframe", background="#ffffff", borderwidth=1, relief="solid")
    style.configure(
        "Card.TLabelframe.Label",
        background="#ffffff",
        foreground="#1f2937",
        font=("Malgun Gothic", 10, "bold"),
    )
    style.configure("TLabel", background="#ffffff", foreground="#1f2937", font=("Malgun Gothic", 9))
    style.configure("TCheckbutton", background="#ffffff", foreground="#344054", font=("Malgun Gothic", 9))
    style.configure("TEntry", fieldbackground="#ffffff", foreground="#111827", padding=5)
    style.configure("TCombobox", fieldbackground="#ffffff", foreground="#111827", padding=5)
    style.configure("TNotebook", background="#ffffff", borderwidth=0)
    style.configure("TNotebook.Tab", padding=(14, 8), font=("Malgun Gothic", 9))
    style.configure("Primary.TButton", background="#1f4e79", foreground="#ffffff", padding=(12, 7), font=("Malgun Gothic", 9, "bold"))
    style.map("Primary.TButton", background=[("active", "#173f62"), ("disabled", "#9aa8b5")])
    style.configure("Secondary.TButton", background="#eef2f6", foreground="#1f2937", padding=(12, 7), font=("Malgun Gothic", 9))
    style.map("Secondary.TButton", background=[("active", "#dbe3ec"), ("disabled", "#f1f3f5")])
    style.configure("Danger.TButton", background="#b42318", foreground="#ffffff", padding=(12, 7), font=("Malgun Gothic", 9))
    style.map("Danger.TButton", background=[("active", "#912018"), ("disabled", "#d0d5dd")])


if __name__ == "__main__":
    main()
