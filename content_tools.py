import re

from prompt_template import PROHIBITED_EXPRESSIONS


PRACTICE_TEMPLATES = {
    "형사": {
        "title_focus": "혐의, 처벌 수위, 조사 대응, 양형자료, 무혐의·감형 판단 기준",
        "faq_focus": "초범 처벌, 경찰조사 전 준비, 합의 필요성, 양형자료, 실형 가능성",
        "evidence": "고소장, 피의자신문조서, 문자·카카오톡, 통화녹음, CCTV, 합의서, 반성문, 탄원서, 피해회복 자료",
        "cta": "조사 일정과 증거자료를 기준으로 혐의 인정 가능성과 방어 전략을 검토받아 보세요.",
    },
    "이혼": {
        "title_focus": "이혼 사유, 재산분할, 위자료, 양육권, 친권, 면접교섭",
        "faq_focus": "재산분할 기준, 유책배우자, 양육권 판단, 위자료 산정, 별거 기간",
        "evidence": "혼인관계 자료, 재산목록, 계좌거래내역, 부동산 등기부등본, 대화내역, 양육 자료, 소득자료",
        "cta": "혼인 경위와 재산·양육 자료를 기준으로 현실적인 협의 또는 소송 방향을 검토받아 보세요.",
    },
    "상간소송": {
        "title_focus": "상간소송 위자료, 부정행위 증거, 혼인 파탄 시점, 방어 전략",
        "faq_focus": "증거가 부족한 경우, 위자료 금액, 혼인 파탄 항변, 연락 기록, 합의 가능성",
        "evidence": "카카오톡, 문자, 사진, 숙박·결제내역, 통화기록, 사실확인서, 혼인 파탄 관련 자료",
        "cta": "증거의 적법성과 혼인 파탄 시점을 기준으로 청구 가능성 또는 방어 가능성을 검토받아 보세요.",
    },
    "전세사기": {
        "title_focus": "전세보증금 반환, 사기 고소, 임대인 책임, 보증보험, 배당 절차",
        "faq_focus": "사기 고소 가능성, 보증금 회수, 내용증명, 임차권등기, 경매 대응",
        "evidence": "임대차계약서, 등기부등본, 입금내역, 문자·카카오톡, 중개자료, 보증보험 서류, 내용증명",
        "cta": "계약서와 등기부, 송금내역을 기준으로 민사·형사 대응 가능성을 함께 검토받아 보세요.",
    },
    "부동산": {
        "title_focus": "계약해제, 계약금 반환, 명도, 손해배상, 등기, 하자 분쟁",
        "faq_focus": "계약금 반환 기준, 해제 통보, 명도 절차, 하자 입증, 손해배상 범위",
        "evidence": "매매·임대차계약서, 특약, 내용증명, 등기부등본, 사진, 하자진단서, 대화내역",
        "cta": "계약서와 특약, 통지 내역을 기준으로 해제·반환·손해배상 가능성을 검토받아 보세요.",
    },
    "노동": {
        "title_focus": "부당해고, 임금체불, 직장 내 괴롭힘, 징계, 산재, 퇴직금",
        "faq_focus": "해고 절차, 구제신청 기간, 체불임금 산정, 증거 확보, 합의 전략",
        "evidence": "근로계약서, 급여명세서, 출퇴근기록, 해고통지서, 징계자료, 대화내역, 취업규칙",
        "cta": "해고 통지와 근로자료를 기준으로 구제신청 또는 청구 가능성을 검토받아 보세요.",
    },
    "조세": {
        "title_focus": "세금 부과처분, 조세불복, 과세근거, 가산세, 세무조사 대응",
        "faq_focus": "불복 기간, 과세자료, 가산세 감면, 소명자료, 심판청구 가능성",
        "evidence": "과세예고통지서, 납세고지서, 세무조사 자료, 장부, 계약서, 송금내역, 소명자료",
        "cta": "과세근거와 소명자료를 기준으로 이의신청·심판청구 가능성을 검토받아 보세요.",
    },
    "행정": {
        "title_focus": "영업정지, 과징금, 인허가, 행정처분 취소, 집행정지",
        "faq_focus": "처분 취소 가능성, 집행정지 요건, 의견제출, 과징금 감경, 불복 기간",
        "evidence": "처분서, 사전통지서, 의견제출서, 현장자료, 영업자료, 행정청 공문, 소명자료",
        "cta": "처분서와 통지 일자를 기준으로 불복 기간과 집행정지 필요성을 검토받아 보세요.",
    },
    "의료": {
        "title_focus": "의료과실, 손해배상, 설명의무, 진료기록, 감정, 합의",
        "faq_focus": "의료과실 입증, 진료기록 확보, 설명의무 위반, 손해액 산정, 감정 절차",
        "evidence": "진료기록, 검사결과, 수술동의서, 설명자료, 진단서, 영상자료, 진료비 영수증",
        "cta": "진료기록과 설명자료를 기준으로 과실·인과관계·손해액 검토를 받아보세요.",
    },
}


CTA_TEMPLATES = {
    "전화상담형": "전화상담으로 사건 경위와 보유 증거를 먼저 정리하고, 필요한 대응 순서를 안내받는 방식으로 작성하세요.",
    "방문상담형": "방문상담에서 계약서·판결문·증거자료를 직접 확인해 쟁점과 위험을 검토받도록 유도하세요.",
    "카카오톡 상담형": "카카오톡 상담으로 판결문, 계약서, 대화내역 등 핵심 자료를 먼저 보내 검토를 요청하도록 유도하세요.",
    "증거자료 검토형": "상담 전 증거자료 검토를 중심으로, 자료에 따라 가능성과 위험이 달라진다는 점을 강조하세요.",
    "긴급 대응형": "기한, 조사, 처분, 소송 진행 등 빠른 의사결정이 필요한 상황에서 신속한 사건 검토를 권유하세요.",
}


RESULT_GUARANTEE_PATTERNS = [
    r"승소(?:할|가)?\s*수\s*있습니다",
    r"해결(?:할|될)?\s*수\s*있습니다",
    r"감형(?:받을|될)?\s*수\s*있습니다",
    r"무혐의(?:를)?\s*받을\s*수\s*있습니다",
    r"처벌을\s*피할\s*수\s*있습니다",
    r"반드시\s*\S+",
    r"확실히\s*\S+",
]


PERSONAL_INFO_PATTERNS = {
    "전화번호": r"(?<!\d)01[016789]-?\d{3,4}-?\d{4}(?!\d)",
    "주민등록번호": r"(?<!\d)\d{6}-\d{7}(?!\d)",
    "이메일": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "주소 의심": r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)[^\n]{0,30}(시|군|구|동|읍|면|로|길)\s?\d*",
    "사건번호 의심": r"(?<!\d)\d{4}[가-힣]{1,4}\d{1,8}(?!\d)",
    "계좌번호 의심": r"(?<!\d)\d{2,6}-\d{2,6}-\d{2,8}(?!\d)",
}


def get_practice_template(practice_area: str) -> dict[str, str]:
    normalized = (practice_area or "").strip()
    return PRACTICE_TEMPLATES.get(normalized, {})


def get_cta_instruction(cta_method: str) -> str:
    normalized = (cta_method or "").strip()
    return CTA_TEMPLATES.get(normalized, normalized or "사건 검토 요청")


def build_template_instruction(practice_area: str, cta_method: str) -> str:
    template = get_practice_template(practice_area)
    if not template:
        return "작성 분야가 비어 있거나 템플릿에 없으면 판결문 내용에 맞춰 제목, FAQ, 준비자료, CTA를 구성하세요."

    return (
        f"분야별 작성 템플릿: {practice_area}\n"
        f"- 제목 초점: {template['title_focus']}\n"
        f"- FAQ 초점: {template['faq_focus']}\n"
        f"- 준비자료 체크리스트 후보: {template['evidence']}\n"
        f"- 기본 CTA 방향: {template['cta']}\n"
        f"- 선택 CTA 방식 반영: {get_cta_instruction(cta_method)}"
    )


def build_ad_risk_report(text: str) -> str:
    findings = []
    prohibited = scan_prohibited_expressions(text)
    for expression in prohibited:
        findings.append(("금지 표현", expression, suggest_replacement(expression)))

    for sentence in split_sentences(text):
        for pattern in RESULT_GUARANTEE_PATTERNS:
            if re.search(pattern, sentence):
                findings.append(("결과 보장 의심", sentence.strip(), "자료와 사실관계에 따라 가능성과 위험을 검토해야 한다는 표현으로 바꾸세요."))
                break

    for label, pattern in PERSONAL_INFO_PATTERNS.items():
        for match in re.finditer(pattern, text):
            findings.append(("개인정보 노출 의심", f"{label}: {match.group(0)}", "A씨, 상대방, 서울 소재 등 익명화된 표현으로 바꾸세요."))

    lines = ["[광고 규정 리스크 검사 리포트]"]
    if not findings:
        lines.append("- 중대한 금지 표현, 결과 보장 표현, 개인정보 패턴이 발견되지 않았습니다.")
        lines.append("- 그래도 게시 전 변호사가 사실관계와 광고 규정 위반 가능성을 최종 검수하세요.")
        return "\n".join(lines)

    for index, (kind, original, suggestion) in enumerate(findings, start=1):
        lines.append(f"{index}. 유형: {kind}")
        lines.append(f"   감지 내용: {original}")
        lines.append(f"   수정 권장: {suggestion}")
    return "\n".join(lines)


def scan_prohibited_expressions(text: str) -> list[str]:
    return [expr for expr in PROHIBITED_EXPRESSIONS if expr in text]


def suggest_replacement(expression: str) -> str:
    replacements = {
        "100% 승소": "이 사건에서는 판결문상 확인되는 사정이 유리하게 고려되었습니다.",
        "100% 해결": "자료와 사실관계에 따라 해결 방향이 달라질 수 있습니다.",
        "무조건 승소": "구체적 증거와 쟁점에 따라 판단이 달라질 수 있습니다.",
        "무조건 해결": "사건 자료를 기준으로 가능한 대응 방향을 검토해야 합니다.",
        "반드시 감형": "양형자료와 사건 경위에 따라 감형 가능성을 검토할 수 있습니다.",
        "처벌을 피할 수 있습니다": "처벌 수위와 대응 방향은 구체적 사정에 따라 달라질 수 있습니다.",
        "국내 최고": "해당 분야 사건 경험을 바탕으로 조력합니다.",
        "압도적 성공률": "개별 사건의 쟁점과 증거를 중심으로 검토합니다.",
        "상담만 받으면 해결됩니다": "상담을 통해 쟁점과 필요한 자료를 먼저 확인할 수 있습니다.",
    }
    return replacements.get(expression, "결과를 단정하지 말고 판결문상 확인되는 범위와 구체적 사정에 따라 달라질 수 있음을 함께 쓰세요.")


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"([.!?。])\s+", r"\1\n", text)
    normalized = normalized.replace("다. ", "다.\n").replace("요. ", "요.\n")
    return [part.strip() for part in normalized.splitlines() if part.strip()]


def build_seo_checklist(text: str, region_keyword: str = "") -> str:
    title = extract_recommended_title(text)
    keywords = extract_core_keywords(text)
    main_keyword = keywords[0] if keywords else ""
    first_paragraph = extract_first_paragraph(text)
    headings_count = count_headings(text)
    hashtag_count = len(re.findall(r"#[0-9A-Za-z가-힣_]+", text))
    compact_len = len(re.sub(r"\s+", "", extract_blog_body(text) or text))
    faq_present = "FAQ" in text or "자주 묻는 질문" in text
    region_count = text.count(region_keyword.strip()) if region_keyword and region_keyword.strip() else 0

    checks = [
        ("제목 길이", 15 <= len(title) <= 45, f"현재 {len(title)}자: {title or '추천 제목을 찾지 못했습니다.'}"),
        ("첫 문단 키워드 포함", bool(main_keyword and main_keyword in first_paragraph), f"메인 키워드 후보: {main_keyword or '없음'}"),
        ("소제목 수", headings_count >= 4, f"현재 {headings_count}개"),
        ("FAQ 포함", faq_present, "FAQ 또는 자주 묻는 질문 섹션 필요"),
        ("해시태그 수", 8 <= hashtag_count <= 12, f"현재 {hashtag_count}개"),
        ("지역 키워드 과다 반복", not region_keyword or region_count <= 5, f"현재 {region_count}회"),
        ("본문 길이", 2000 <= compact_len <= 3000, f"공백 제외 약 {compact_len}자"),
    ]

    lines = ["[네이버 SEO 체크리스트]"]
    for label, passed, detail in checks:
        mark = "통과" if passed else "점검 필요"
        lines.append(f"- {label}: {mark} ({detail})")
    return "\n".join(lines)


def extract_core_keywords(text: str) -> list[str]:
    match = re.search(r"핵심\s*키워드\s*10개(.+?)(?:제목\s*후보|추천\s*최종\s*제목|블로그\s*본문)", text, re.S)
    source = match.group(1) if match else text[:800]
    candidates = []
    for line in source.splitlines():
        cleaned = re.sub(r"^[\s\-*#\d.]+", "", line).strip()
        cleaned = cleaned.strip(",")
        if 2 <= len(cleaned) <= 30 and not cleaned.startswith("["):
            candidates.append(cleaned)
    return candidates[:10]


def extract_recommended_title(text: str) -> str:
    match = re.search(r"추천\s*최종\s*제목\s*1?개?\s*[:：]?\s*(.+)", text)
    if match:
        return re.sub(r"^[\s\-*#]+", "", match.group(1)).strip()
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("[") and len(cleaned) <= 70:
            return re.sub(r"^[#\s]+", "", cleaned)
    return ""


def extract_first_paragraph(text: str) -> str:
    body = extract_blog_body(text) or text
    for part in re.split(r"\n\s*\n", body):
        cleaned = part.strip()
        if cleaned and not cleaned.startswith("#") and not cleaned.startswith("["):
            return cleaned
    return ""


def extract_blog_body(text: str) -> str:
    match = re.search(r"블로그\s*본문(.+?)(?:\n\s*5\.\s*FAQ|\n\s*FAQ|\n\s*6\.\s*메타디스크립션|\n\s*메타디스크립션)", text, re.S)
    return match.group(1).strip() if match else ""


def count_headings(text: str) -> int:
    markdown_headings = len(re.findall(r"^#{2,3}\s+", text, re.M))
    bracket_headings = len(re.findall(r"^\[소제목\]", text, re.M))
    numbered_sections = len(re.findall(r"^\d+\.\s+.{2,40}$", text, re.M))
    return markdown_headings + bracket_headings + numbered_sections
