import unittest

import core


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


if __name__ == "__main__":
    unittest.main()
