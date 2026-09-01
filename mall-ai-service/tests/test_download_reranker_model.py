import tempfile
import unittest
from pathlib import Path

from scripts.download_reranker_model import _is_ready


class DownloadRerankerModelTests(unittest.TestCase):
    def test_readiness_requires_the_onnx_model_and_tokenizer_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir)
            self.assertFalse(_is_ready(target))
            (target / "onnx").mkdir()
            (target / "onnx" / "model.onnx").write_text("fixture", encoding="utf-8")
            (target / "config.json").write_text("{}", encoding="utf-8")
            self.assertFalse(_is_ready(target))
            (target / "tokenizer.json").write_text("{}", encoding="utf-8")
            self.assertTrue(_is_ready(target))


if __name__ == "__main__":
    unittest.main()
