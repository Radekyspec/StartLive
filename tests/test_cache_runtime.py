import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import src.core.cache as cache
from src.core.constant import CacheType


class CacheRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        cache._cache_dir.clear()
        if hasattr(cache, "__compiled__"):
            delattr(cache, "__compiled__")

    def tearDown(self) -> None:
        cache._cache_dir.clear()
        if hasattr(cache, "__compiled__"):
            delattr(cache, "__compiled__")

    def test_windows_source_run_falls_back_to_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_cwd = Path.cwd()
            os.chdir(temp_dir)
            try:
                with patch.object(cache, "system", return_value="Windows"):
                    result = cache.cache_base_dir(CacheType.CONFIG)
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(result, Path(temp_dir).resolve() / CacheType.CONFIG)

    def test_windows_compiled_run_uses_executable_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            setattr(
                cache,
                "__compiled__",
                SimpleNamespace(containing_dir=temp_dir),
            )

            with patch.object(cache, "system", return_value="Windows"):
                result = cache.cache_base_dir(CacheType.LOGS)

        self.assertEqual(result, Path(temp_dir).resolve() / CacheType.LOGS)


if __name__ == "__main__":
    unittest.main()
