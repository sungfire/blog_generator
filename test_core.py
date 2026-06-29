import unittest
from pathlib import Path
import tempfile

import core
from content_tools import (
    build_ad_risk_report,
    build_seo_checklist,
    build_template_instruction,
    get_cta_instruction,
    get_practice_template,
)
from config_store import delete_api_key, load_api_key, save_api_key


class CoreTest(unittest.TestCase):
    def test_mask_sensitive_text(self) -> None:
        text = "010-1234-5678 900101-1234567 2024가단12345 test@example.com"
        masked = core.mask_sensitive_text(text)
        self.assertIn("전화번호 비공개", masked)
        self.assertIn("주민등록번호 비공개", masked)
        self.assertIn("사건번호 비공개", masked)
        self.assertIn("이메일 비공개", masked)

    def test_scan_prohibited_expressions(self) -> None:
        found = core.scan_prohibited_expressions("100% 승소와 무조건 해결을 보장합니다.")
        self.assertIn("100% 승소", found)
        self.assertIn("무조건 해결", found)

    def test_header_only_pdf_text_is_not_usable(self) -> None:
        text = "\n\n".join(
            f"[{index}페이지]\n제출자:법무법인, 제출일시:2019.02.09 17:41, 출력자:임경훈, 다운로드일시:2019.11.18 10:20"
            for index in range(1, 12)
        )
        self.assertFalse(core.is_extracted_text_usable(text))

    def test_judgment_like_text_is_usable(self) -> None:
        text = "서울중앙지방법원 판결\n사건 2024가단123\n원고 A\n피고 B\n주문\n이유\n" + "본문 " * 300
        self.assertTrue(core.is_extracted_text_usable(text))

    def test_ocr_speed_defaults(self) -> None:
        self.assertEqual(core.OCR_RENDER_SCALE, 1.5)
        self.assertEqual(core.OCR_IMAGE_DETAIL, "auto")
        self.assertEqual(core.OCR_MAX_WORKERS, 3)

    def test_remove_unsupported_temperature_for_retry(self) -> None:
        payload = {"model": "gpt-5.5", "temperature": 0.4, "input": []}
        retry = core.remove_unsupported_temperature_for_retry(
            payload,
            "Unsupported parameter: 'temperature' is not supported with this model.",
        )
        self.assertIsNotNone(retry)
        self.assertNotIn("temperature", retry)
        self.assertIn("temperature", payload)

    def test_build_blog_image_prompts(self) -> None:
        prompts = core.build_blog_image_prompts("손해배상 청구 기각 사례 본문입니다.", 2)
        self.assertEqual(len(prompts), 2)
        self.assertIn("Do not include readable text", prompts[0])

    def test_call_openai_prompt_metadata_defaults(self) -> None:
        prompt = core.USER_PROMPT_TEMPLATE.format(
            judgment_text="판결문",
            practice_area="",
            target_reader="",
            region_keyword="없음",
            firm_name="본 법률사무소",
            cta_method="사건 검토 요청",
            template_instruction="분야별 템플릿",
        )
        self.assertIn("핵심 키워드 10개", prompt)
        self.assertIn("릴스로 재가공할 경우의 30초 대본", prompt)

    def test_api_key_config_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            save_api_key("sk-test", config_path=config_path)
            self.assertEqual(load_api_key(config_path=config_path), "sk-test")
            delete_api_key(config_path=config_path)
            self.assertEqual(load_api_key(config_path=config_path), "")

    def test_convert_markdown_to_naver_text(self) -> None:
        source = "## 핵심 쟁점\n\n**중요 문장**\n\n- 준비자료\n\n![이미지](C:/blog/image.png)"
        converted = core.convert_markdown_to_naver_text(source)
        self.assertIn("[소제목] 핵심 쟁점", converted)
        self.assertIn("[강조] 중요 문장", converted)
        self.assertIn("- 준비자료", converted)
        self.assertIn("[이미지 삽입: 이미지]", converted)
        self.assertNotIn("##", converted)
        self.assertNotIn("**", converted)

    def test_build_naver_html(self) -> None:
        source = "## 핵심 쟁점\n\n본문의 **강조** 문장입니다.\n\n![이미지](C:/blog/image.png)"
        rendered = core.build_naver_html(source)
        self.assertIn("<h2>핵심 쟁점</h2>", rendered)
        self.assertIn("<strong>강조</strong>", rendered)
        self.assertIn("<img", rendered)
        self.assertIn("C:/blog/image.png", rendered)

    def test_practice_template_and_cta(self) -> None:
        template = get_practice_template("형사")
        self.assertIn("경찰조사", template["faq_focus"])
        self.assertIn("카카오톡 상담", get_cta_instruction("카카오톡 상담형"))
        instruction = build_template_instruction("전세사기", "증거자료 검토형")
        self.assertIn("전세보증금", instruction)
        self.assertIn("증거자료", instruction)

    def test_ad_risk_report(self) -> None:
        report = build_ad_risk_report("무조건 승소할 수 있습니다. 연락처는 010-1234-5678입니다.")
        self.assertIn("금지 표현", report)
        self.assertIn("결과 보장 의심", report)
        self.assertIn("개인정보 노출 의심", report)
        self.assertIn("수정 권장", report)

    def test_seo_checklist(self) -> None:
        sample = """
1. 핵심 키워드 10개
- 전세보증금 반환

3. 추천 최종 제목 1개
전세보증금 반환 판결로 본 대응 방법

4. 블로그 본문
전세보증금 반환 문제로 고민하는 분들이 많습니다.

## 사건 개요
본문입니다.

## 핵심 쟁점
본문입니다.

## 법원의 판단
본문입니다.

## 상담이 필요한 경우
본문입니다.

5. FAQ
Q. 전세보증금 반환 소송은 어떻게 준비하나요?

#전세보증금 #임대차 #보증금반환 #부동산소송 #내용증명 #임차권등기 #법률상담 #부동산변호사
""" + "본문" * 700
        checklist = build_seo_checklist(sample, "서울")
        self.assertIn("제목 길이", checklist)
        self.assertIn("FAQ 포함", checklist)
        self.assertIn("해시태그 수", checklist)


if __name__ == "__main__":
    unittest.main()
