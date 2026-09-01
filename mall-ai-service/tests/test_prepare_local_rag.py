"""Unit coverage for public-release local RAG artifact preparation."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "prepare_local_rag.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("prepare_local_rag_test_target", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load local RAG preparation script")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PrepareLocalRagTests(unittest.TestCase):
    def test_script_makes_service_root_importable(self) -> None:
        module = _load_module()

        self.assertIn(str(module.PROJECT_ROOT), sys.path)

    def test_embedding_ready_requires_every_runtime_file(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertFalse(module.embedding_model_ready(target))
            for name in module.REQUIRED_EMBEDDING_FILES:
                (target / name).write_text("fixture", encoding="utf-8")
            self.assertTrue(module.embedding_model_ready(target))

    def test_copy_runtime_model_files_uses_allow_list_only(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            for name in module.REQUIRED_EMBEDDING_FILES:
                (source / name).write_text(name, encoding="utf-8")
            (source / "untrusted-extra.bin").write_text("not copied", encoding="utf-8")

            module.copy_runtime_model_files(source, target)

            self.assertTrue(module.embedding_model_ready(target))
            self.assertFalse((target / "untrusted-extra.bin").exists())

    def test_check_only_does_not_download_or_rebuild(self) -> None:
        module = _load_module()
        original_model_ready = module.embedding_model_ready
        original_index_ready = module.policy_index_ready
        original_download = module.download_embedding_model
        original_build = module.build_policy_index
        try:
            module.embedding_model_ready = lambda: False
            module.policy_index_ready = lambda: False
            module.download_embedding_model = lambda: self.fail("download must not run")
            module.build_policy_index = lambda: self.fail("build must not run")
            self.assertEqual(2, module.main(["--check-only"]))
        finally:
            module.embedding_model_ready = original_model_ready
            module.policy_index_ready = original_index_ready
            module.download_embedding_model = original_download
            module.build_policy_index = original_build
