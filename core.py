import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import ssl
import urllib.error
import urllib.request

from prompt_template import OCR_PROMPT, PROHIBITED_EXPRESSIONS, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-4.1-mini"
MAX_INPUT_CHARS = 45000
MAX_OCR_PAGES = 30
OCR_RENDER_SCALE = 1.5
OCR_IMAGE_DETAIL = "auto"
OCR_MAX_WORKERS = 3


def extract_pdf_text(pdf_path: str, api_key: str = "", model: str = DEFAULT_MODEL, progress_callback=None) -> str:
    extracted = _extract_pdf_text_with_pymupdf(pdf_path)
    if is_extracted_text_usable(extracted):
        return extracted

    extracted = _extract_pdf_text_with_pypdf(pdf_path)
    if is_extracted_text_usable(extracted):
        return extracted

    if not api_key:
        raise RuntimeError(
            "PDF 본문 텍스트를 직접 추출하지 못했습니다. 스캔본으로 판단되어 OpenAI OCR이 필요합니다. "
            "OpenAI API Key를 먼저 입력한 뒤 PDF를 다시 선택해 주세요."
        )

    ocr_text = extract_pdf_text_with_openai_ocr(pdf_path, api_key, model or DEFAULT_MODEL, progress_callback)
    if ocr_text:
        return ocr_text

    raise RuntimeError("OpenAI OCR로도 판결문 텍스트를 추출하지 못했습니다.")


def is_extracted_text_usable(text: str) -> bool:
    normalized = text.strip()
    if len(normalized) < 800:
        return False

    lines = [line.strip() for line in normalized.splitlines() if line.strip() and not line.startswith("[")]
    if not lines:
        return False

    metadata_lines = [
        line
        for line in lines
        if ("제출자:" in line and "출력자:" in line)
        or "다운로드일시" in line
        or "제출일시" in line
    ]
    if len(metadata_lines) >= 3 and len(metadata_lines) / len(lines) >= 0.4:
        return False

    keywords = ["판결", "주문", "이유", "청구취지", "원고", "피고", "법원", "선고", "사건"]
    keyword_hits = sum(1 for keyword in keywords if keyword in normalized)
    if keyword_hits >= 2:
        return True
    return len(normalized) >= 2500 and keyword_hits >= 1


def _extract_pdf_text_with_pymupdf(pdf_path: str) -> str:
    try:
        import fitz
    except ImportError:
        return ""

    pages = []
    with fitz.open(pdf_path) as document:
        for index, page in enumerate(document, start=1):
            text = page.get_text("text") or ""
            if text.strip():
                pages.append(f"[{index}페이지]\n{text.strip()}")
    return "\n\n".join(pages).strip()


def _extract_pdf_text_with_pypdf(pdf_path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF 처리를 위해 PyMuPDF 또는 pypdf가 필요합니다. `pip install -r requirements.txt`를 실행해 주세요."
        ) from exc

    reader = PdfReader(pdf_path)
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[{index}페이지]\n{text.strip()}")

    return "\n\n".join(pages).strip()


def extract_pdf_text_with_openai_ocr(pdf_path: str, api_key: str, model: str = DEFAULT_MODEL, progress_callback=None) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("OpenAI OCR을 위해 PyMuPDF가 필요합니다. `pip install -r requirements.txt`를 실행해 주세요.") from exc

    rendered_pages = []
    with fitz.open(pdf_path) as document:
        page_count = min(len(document), MAX_OCR_PAGES)
        for page_index in range(page_count):
            page = document[page_index]
            matrix = fitz.Matrix(OCR_RENDER_SCALE, OCR_RENDER_SCALE)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            png_bytes = pixmap.tobytes("png")
            image_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
            rendered_pages.append((page_index + 1, image_url))

    results = {}
    completed = 0
    worker_count = min(OCR_MAX_WORKERS, len(rendered_pages)) or 1
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(_ocr_page_with_openai, api_key, model, image_url, page_number): page_number
            for page_number, image_url in rendered_pages
        }
        for future in as_completed(futures):
            page_number = futures[future]
            results[page_number] = future.result().strip()
            completed += 1
            if progress_callback:
                progress_callback(completed, len(rendered_pages))

    pages = []
    for page_number in sorted(results):
        page_text = results[page_number]
        if page_text:
            pages.append(f"[{page_number}페이지]\n{page_text}")
    return "\n\n".join(pages).strip()


def _ocr_page_with_openai(api_key: str, model: str, image_url: str, page_number: int) -> str:
    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": f"{OCR_PROMPT}\n\n현재 페이지: {page_number}페이지"},
                    {"type": "input_image", "image_url": image_url, "detail": OCR_IMAGE_DETAIL},
                ],
            }
        ],
        "temperature": 0,
        "max_output_tokens": 2500,
    }
    return _extract_output_text(_post_openai_response(api_key, payload))


def mask_sensitive_text(text: str) -> str:
    patterns = [
        (r"\b\d{6}-\d{7}\b", "주민등록번호 비공개"),
        (r"\b01[016789]-?\d{3,4}-?\d{4}\b", "전화번호 비공개"),
        (r"\b\d{2,6}-\d{2,6}-\d{2,8}\b", "번호 비공개"),
        (r"\b\d{4}[가-힣]\d{4}\b", "차량번호 비공개"),
        (r"\b\d{4}[가-힣]{1,3}\d{1,8}\b", "사건번호 비공개"),
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "이메일 비공개"),
    ]
    masked = text
    for pattern, replacement in patterns:
        masked = re.sub(pattern, replacement, masked)
    return masked


def scan_prohibited_expressions(text: str) -> list[str]:
    return [expr for expr in PROHIBITED_EXPRESSIONS if expr in text]


def call_openai(api_key: str, model: str, judgment_text: str) -> str:
    clipped_text = judgment_text[:MAX_INPUT_CHARS]
    user_prompt = USER_PROMPT_TEMPLATE.format(judgment_text=clipped_text)
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
        "temperature": 0.4,
        "max_output_tokens": 5000,
    }

    return _extract_output_text(_post_openai_response(api_key, payload))


def _post_openai_response(api_key: str, payload: dict) -> dict:
    try:
        return _send_openai_response(api_key, payload)
    except RuntimeError as exc:
        retry_payload = remove_unsupported_temperature_for_retry(payload, str(exc))
        if retry_payload:
            return _send_openai_response(api_key, retry_payload)
        raise


def _send_openai_response(api_key: str, payload: dict) -> dict:
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120, context=ssl.create_default_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API 오류: HTTP {exc.code}\n{detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API 연결 실패: {exc.reason}") from exc


def remove_unsupported_temperature_for_retry(payload: dict, error_message: str) -> dict | None:
    if "Unsupported parameter" not in error_message or "temperature" not in error_message:
        return None
    if "temperature" not in payload:
        return None
    retry_payload = dict(payload)
    retry_payload.pop("temperature", None)
    return retry_payload


def _extract_output_text(data: dict) -> str:
    output_text = data.get("output_text")
    if output_text:
        return output_text.strip()

    chunks = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(content["text"])
    if chunks:
        return "\n".join(chunks).strip()

    raise RuntimeError("OpenAI 응답에서 글 본문을 찾지 못했습니다.")
