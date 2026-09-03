"""Privacy contract for the disposable local-demo bootstrap script."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_live_demo.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("bootstrap_live_demo_test_target", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load bootstrap_live_demo.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class BootstrapLiveDemoPrivacyTests(unittest.TestCase):
    def test_stdout_excludes_machine_identifiers_and_result_file_is_explicit(self) -> None:
        module = _load_script_module()
        first = module.DemoOrder("demo-a", 101, 201, "SYNTHETIC-ORDER-A")
        second = module.DemoOrder("demo-b", 102, 202, "SYNTHETIC-ORDER-B")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as temporary:
            result_file = temporary.name
        self.addCleanup(lambda: os.path.exists(result_file) and os.remove(result_file))

        environment = {
            "MALL_LIVE_DEMO_PASSWORD": "only-for-test-123",
            "MALL_LIVE_DEMO_RESULT_FILE": result_file,
        }
        client_context = MagicMock()
        client_context.__enter__.return_value = object()
        client_factory = MagicMock(return_value=client_context)
        with (
            patch.dict(os.environ, environment),
            patch.object(module.httpx, "Client", client_factory),
            patch.object(module, "_prepare_account_order", side_effect=[first, second]),
            contextlib.redirect_stdout(io.StringIO()) as stdout,
        ):
            self.assertEqual(0, module.main())

        output = stdout.getvalue()
        self.assertIn('"status": "prepared"', output)
        self.assertIn("demo-a", output)
        self.assertNotIn("SYNTHETIC-ORDER-A", output)
        self.assertNotIn("SYNTHETIC-ORDER-B", output)
        self.assertNotIn("member_id", output)
        self.assertNotIn("order_id", output)
        client_factory.assert_called_once_with(timeout=20, trust_env=False)

        payload = json.loads(Path(result_file).read_text(encoding="utf-8"))
        self.assertEqual("SYNTHETIC-ORDER-A", payload["account_a"]["order_sn"])
        self.assertEqual("SYNTHETIC-ORDER-B", payload["account_b"]["order_sn"])
