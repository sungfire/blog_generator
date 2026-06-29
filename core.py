import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
from pathlib import Path
import json
import re
import ssl
import urllib.error
import urllib.request

from prompt_template import OCR_PROMPT, PROHIBITED_EXPRESSIONS, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_IMAGE_SIZE = "1024x1024"
DEFAULT_IMAGE_QUALITY = "low"
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


def call_openai(
    api_key: str,
    model: str,
    judgment_text: str,
    practice_area: str = "",
    target_reader: str = "",
    region_keyword: str = "",
    firm_name: str = "",
    cta_method: str = "",
) -> str:
    clipped_text = judgment_text[:MAX_INPUT_CHARS]
    user_prompt = USER_PROMPT_TEMPLATE.format(
        judgment_text=clipped_text,
        practice_area=practice_area.strip() or "판결문 내용을 바탕으로 가장 적절한 분야를 추론하세요.",
        target_reader=target_reader.strip() or "판결문 내용을 바탕으로 주요 타깃 독자를 추론하세요.",
        region_keyword=region_keyword.strip() or "없음",
        firm_name=firm_name.strip() or "본 법률사무소",
        cta_method=cta_method.strip() or "사건 검토 요청",
    )
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
        "temperature": 0.4,
        "max_output_tokens": 8000,
    }

    return _extract_output_text(_post_openai_response(api_key, payload))


def generate_blog_images(api_key: str, blog_text: str, output_dir: Path, count: int = 2, progress_callback=None) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_count = max(1, min(count, 5))
    image_paths = []
    prompts = build_blog_image_prompts(blog_text, safe_count)

    for index, prompt in enumerate(prompts, start=1):
        image_bytes = _generate_image_bytes(api_key, prompt)
        path = output_dir / f"blog_image_{index:02d}.png"
        path.write_bytes(image_bytes)
        image_paths.append(path)
        if progress_callback:
            progress_callback(index, safe_count)

    return image_paths


def build_blog_image_prompts(blog_text: str, count: int) -> list[str]:
    excerpt = re.sub(r"\s+", " ", blog_text).strip()[:1200]
    themes = [
        "a clean editorial blog header image with legal documents, a fountain pen, and a subtle courthouse silhouette",
        "a professional Korean law office desk scene with organized case files and calm natural light",
        "an abstract legal dispute resolution concept with balanced scales, documents, and neutral blue-gray tones",
        "a consultation scene represented without identifiable people, using chairs, documents, and a warm office atmosphere",
        "a court judgment explanation concept image with paper files, bookmarks, and restrained professional styling",
    ]
    prompts = []
    for theme in themes[: max(1, min(count, len(themes)))]:
        prompts.append(
            "Create a professional, non-sensational image for a Korean law firm Naver blog article. "
            "Do not include readable text, real people, logos, court seals, names, case numbers, or any personal data. "
            "Avoid dramatic crime-scene visuals. Use a trustworthy, modern, editorial style suitable for attorney marketing. "
            f"Theme: {theme}. "
            f"Article context for visual relevance: {excerpt}"
        )
    return prompts


def convert_markdown_to_naver_text(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue

        image_match = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
        if image_match:
            alt_text = image_match.group(1).strip() or "이미지"
            image_path = image_match.group(2).strip()
            lines.append(f"[이미지 삽입: {alt_text}]")
            lines.append(f"파일: {image_path}")
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            heading_text = _strip_inline_markdown(heading_match.group(2))
            lines.append(f"[소제목] {heading_text}")
            continue

        if re.match(r"^\*\*(.+)\*\*$", stripped):
            lines.append(f"[강조] {_strip_inline_markdown(stripped)}")
            continue

        cleaned = _strip_inline_markdown(line)
        cleaned = re.sub(r"^\s*[-*]\s+", "- ", cleaned)
        lines.append(cleaned)

    return _collapse_blank_lines("\n".join(lines)).strip()


def build_naver_html(text: str) -> str:
    body = _markdown_like_to_html(text)
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>네이버 블로그 붙여넣기용 미리보기</title>
  <style>
    body {{
      font-family: "Malgun Gothic", "Apple SD Gothic Neo", Arial, sans-serif;
      line-height: 1.75;
      color: #222;
      max-width: 760px;
      margin: 40px auto;
      padding: 0 24px;
      background: #fff;
    }}
    h1 {{ font-size: 28px; margin: 32px 0 18px; }}
    h2 {{ font-size: 22px; margin: 30px 0 14px; }}
    h3 {{ font-size: 18px; margin: 24px 0 12px; }}
    p {{ font-size: 16px; margin: 0 0 14px; }}
    ul, ol {{ margin: 0 0 16px 24px; padding: 0; }}
    li {{ margin: 6px 0; }}
    strong {{ font-weight: 700; }}
    em {{ font-style: italic; }}
    img {{ max-width: 100%; display: block; margin: 22px 0; }}
    .image-note {{
      border: 1px solid #ddd;
      background: #f7f7f7;
      padding: 12px;
      margin: 18px 0;
      color: #555;
    }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def save_naver_html(text: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_naver_html(text), encoding="utf-8")
    return output_path


def _strip_inline_markdown(text: str) -> str:
    cleaned = re.sub(r"!\[(.*?)\]\((.*?)\)", r"\1 (\2)", text)
    cleaned = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", cleaned)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
    cleaned = re.sub(r"(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)", r"\1", cleaned)
    cleaned = re.sub(r"_(.*?)_", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    return cleaned


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


def _markdown_like_to_html(text: str) -> str:
    html_lines = []
    list_mode = None

    def close_list() -> None:
        nonlocal list_mode
        if list_mode:
            html_lines.append(f"</{list_mode}>")
            list_mode = None

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            close_list()
            continue

        image_match = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
        if image_match:
            close_list()
            alt_text = html.escape(image_match.group(1).strip() or "블로그 이미지")
            image_path = html.escape(image_match.group(2).strip())
            html_lines.append(f'<p class="image-note">이미지 파일: {image_path}</p>')
            html_lines.append(f'<img src="{image_path}" alt="{alt_text}">')
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            close_list()
            level = min(len(heading_match.group(1)), 3)
            heading_text = _inline_markdown_to_html(heading_match.group(2))
            html_lines.append(f"<h{level}>{heading_text}</h{level}>")
            continue

        ordered_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ordered_match:
            if list_mode != "ol":
                close_list()
                html_lines.append("<ol>")
                list_mode = "ol"
            html_lines.append(f"<li>{_inline_markdown_to_html(ordered_match.group(1))}</li>")
            continue

        bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet_match:
            if list_mode != "ul":
                close_list()
                html_lines.append("<ul>")
                list_mode = "ul"
            html_lines.append(f"<li>{_inline_markdown_to_html(bullet_match.group(1))}</li>")
            continue

        close_list()
        html_lines.append(f"<p>{_inline_markdown_to_html(stripped)}</p>")

    close_list()
    return "\n".join(html_lines)


def _inline_markdown_to_html(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"__(.*?)__", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"_(.*?)_", r"<em>\1</em>", escaped)
    escaped = re.sub(r"`([^`]*)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", escaped)
    return escaped


def _generate_image_bytes(api_key: str, prompt: str) -> bytes:
    payload = {
        "model": DEFAULT_IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": DEFAULT_IMAGE_SIZE,
        "quality": DEFAULT_IMAGE_QUALITY,
        "output_format": "png",
    }
    data = _post_image_generation(api_key, payload)
    image_data = data.get("data", [{}])[0]
    if image_data.get("b64_json"):
        return base64.b64decode(image_data["b64_json"])
    if image_data.get("url"):
        with urllib.request.urlopen(image_data["url"], timeout=120, context=ssl.create_default_context()) as response:
            return response.read()
    raise RuntimeError("OpenAI 이미지 응답에서 이미지 데이터를 찾지 못했습니다.")


def _post_image_generation(api_key: str, payload: dict) -> dict:
    request = urllib.request.Request(
        OPENAI_IMAGES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180, context=ssl.create_default_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI 이미지 API 오류: HTTP {exc.code}\n{detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI 이미지 API 연결 실패: {exc.reason}") from exc


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
