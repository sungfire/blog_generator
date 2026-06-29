from datetime import datetime
import os
import threading
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, BooleanVar, IntVar, StringVar, Tk, filedialog, messagebox
from tkinter import ttk

from config_store import delete_api_key, load_api_key, save_api_key
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
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=BOTH, expand=True)

        top = ttk.Frame(outer)
        top.pack(fill=X)

        ttk.Label(top, text="OpenAI API Key").pack(anchor="w")
        key_row = ttk.Frame(top)
        key_row.pack(fill=X, pady=(4, 10))
        ttk.Entry(key_row, textvariable=self.api_key, show="*", width=80).pack(side=LEFT, fill=X, expand=True)
        ttk.Button(key_row, text="API Key 저장", command=self.save_key).pack(side=LEFT, padx=(8, 0))
        ttk.Button(key_row, text="삭제", command=self.delete_key).pack(side=LEFT, padx=(4, 0))
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

        options_row_1 = ttk.Frame(top)
        options_row_1.pack(fill=X, pady=(0, 6))
        ttk.Label(options_row_1, text="작성 분야").pack(side=LEFT)
        ttk.Entry(options_row_1, textvariable=self.practice_area, width=16).pack(side=LEFT, padx=(4, 12))
        ttk.Label(options_row_1, text="타깃 독자").pack(side=LEFT)
        ttk.Entry(options_row_1, textvariable=self.target_reader, width=16).pack(side=LEFT, padx=(4, 12))
        ttk.Label(options_row_1, text="지역 키워드").pack(side=LEFT)
        ttk.Entry(options_row_1, textvariable=self.region_keyword, width=14).pack(side=LEFT, padx=(4, 12))

        options_row_2 = ttk.Frame(top)
        options_row_2.pack(fill=X, pady=(0, 10))
        ttk.Label(options_row_2, text="변호사/법무법인명").pack(side=LEFT)
        ttk.Entry(options_row_2, textvariable=self.firm_name, width=28).pack(side=LEFT, padx=(4, 12))
        ttk.Label(options_row_2, text="상담 CTA").pack(side=LEFT)
        ttk.Entry(options_row_2, textvariable=self.cta_method, width=24).pack(side=LEFT, padx=(4, 12))

        action_row = ttk.Frame(top)
        action_row.pack(fill=X, pady=(0, 10))
        self.generate_button = ttk.Button(action_row, text="블로그 글 생성", command=self.generate)
        self.generate_button.pack(side=LEFT)
        ttk.Checkbutton(action_row, text="본문 이미지 생성", variable=self.generate_images).pack(side=LEFT, padx=(12, 0))
        ttk.Label(action_row, text="이미지 수").pack(side=LEFT, padx=(8, 4))
        ttk.Spinbox(action_row, from_=1, to=5, textvariable=self.image_count, width=4).pack(side=LEFT)
        ttk.Button(action_row, text="결과 저장", command=self.save_result).pack(side=LEFT, padx=(8, 0))
        ttk.Button(action_row, text="네이버용 복사", command=self.copy_naver_text).pack(side=LEFT, padx=(8, 0))
        ttk.Button(action_row, text="HTML 미리보기 저장", command=self.save_html_preview).pack(side=LEFT, padx=(8, 0))
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
        api_key = self.api_key.get().strip()
        if api_key:
            save_api_key(api_key)
        self.pdf_path.set(path)
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
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    BlogWriterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
