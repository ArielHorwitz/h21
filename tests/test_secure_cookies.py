from __future__ import annotations

import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import patch

from h21.config import load_config


class DeploymentConfigTests(unittest.TestCase):
    def test_secure_cookies_can_be_enabled_in_toml(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_dir = root / "config" / "h21"
            config_dir.mkdir(parents=True)
            (config_dir / "config.toml").write_text(
                'openai_api_key = "test-key"\nsecure_cookies = true\n',
            )
            with patch.dict(
                environ,
                {
                    "XDG_CONFIG_HOME": str(root / "config"),
                    "XDG_DATA_HOME": str(root / "data"),
                },
                clear=False,
            ):
                config = load_config()

            self.assertTrue(config.secure_cookies)


if __name__ == "__main__":
    unittest.main()
