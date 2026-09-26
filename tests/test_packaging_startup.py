import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import StartLive
from startlive.PySide.updater.update_worker import VelopackUpdateWorker
from startlive.core import cache
from startlive.core.constant import CacheType


class PackagingStartupTests(unittest.TestCase):
    def test_help_supports_legacy_output_encodings(self):
        script = (
            "import sys; "
            "sys.modules['PySide6'] = None; "
            "sys.modules['keyring'] = None; "
            "import StartLive; sys.argv = ['startlive', '--help']; "
            "StartLive.cli()"
        )
        for encoding in ('cp1252', 'ascii', 'utf-8'):
            with self.subTest(encoding=encoding):
                env = dict(os.environ, PYTHONIOENCODING=f'{encoding}:strict')
                result = subprocess.run(
                    [sys.executable, '-B', '-c', script],
                    capture_output=True, env=env,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('--web.port', result.stdout.decode(encoding))

    def test_help_does_not_load_gui_or_keyring(self):
        script = (
            "import sys; "
            "sys.modules['PySide6'] = None; "
            "sys.modules['keyring'] = None; "
            "import StartLive; sys.argv = ['startlive', '--help']; "
            "StartLive.main()"
        )
        result = subprocess.run(
            [sys.executable, '-c', script], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--web.port', result.stdout)

    def test_version_does_not_load_gui_or_keyring(self):
        script = (
            "import sys; "
            "sys.modules['PySide6'] = None; "
            "sys.modules['keyring'] = None; "
            "import StartLive; sys.argv = ['startlive', '--version']; "
            "StartLive.main()"
        )
        result = subprocess.run(
            [sys.executable, '-c', script], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        from startlive.core.constant import VERSION
        self.assertIn(VERSION, result.stdout)

    def test_package_entry_uses_stable_windows_paths_and_skips_updater(self):
        self.assertTrue(callable(getattr(StartLive, 'cli', None)))
        from startlive.core import runtime

        def check_startup():
            with patch('startlive.core.cache.system', return_value='Windows'), \
                    patch.dict(os.environ, {
                        'LOCALAPPDATA': str(Path.home() / 'local-test')}), \
                    patch.dict(cache._cache_dir, {}, clear=True):
                for kind in CacheType:
                    self.assertEqual(
                        cache.cache_base_dir(kind),
                        Path.home() / 'local-test' / 'StartLive' / kind,
                    )
            for platform in ('Windows', 'Darwin', 'Linux'):
                with patch('startlive.PySide.updater.update_worker.system',
                           return_value=platform), \
                        patch.dict(sys.modules, {'velopack': None}):
                    worker = VelopackUpdateWorker('https://example.invalid',
                                                  Mock())
                    failed, finished = Mock(), Mock()
                    worker.failed.connect(failed)
                    worker.finished.connect(finished)
                    worker.run()
                    failed.assert_not_called()
                    finished.assert_called_once_with()
            return 7

        with patch.object(runtime, 'package_managed', False), \
                patch.object(StartLive, 'main', side_effect=check_startup), \
                patch.object(StartLive, '_run_velopack_hooks') as hooks:
            self.assertEqual(StartLive.cli(), 7)
            hooks.assert_not_called()


if __name__ == '__main__':
    unittest.main()
