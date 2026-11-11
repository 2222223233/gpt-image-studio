import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('package_release', ROOT / 'scripts/package_release.py')
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class DistributionTests(unittest.TestCase):
    def test_package_excludes_user_data_and_can_run_after_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'source'
            for name in packager.FILES:
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, destination)
            (root / '.env').write_text('DO_NOT_DISTRIBUTE=private', encoding='utf-8')
            (root / 'generated').mkdir()
            (root / 'generated/private.png').write_bytes(b'private image')
            (root / 'personal-photo.jpg').write_bytes(b'private image')
            with patch.object(packager, 'ROOT', root):
                archive = packager.build(Path(temp) / 'dist')
            with zipfile.ZipFile(archive) as package:
                names = package.namelist()
                self.assertFalse(any('.env' in n or 'private.png' in n or 'personal-photo' in n for n in names))
                self.assertIn('gpt-image-studio/.github/workflows/ci.yml', names)
                self.assertIn('gpt-image-studio/LICENSE', names)
                self.assertIn('gpt-image-studio/web/app.js', names)
                package.extractall(Path(temp) / 'extracted')
            result = subprocess.run([sys.executable, 'app.py', '--version'], cwd=Path(temp) / 'extracted/gpt-image-studio', capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertRegex(result.stdout, r'GPT Image Studio \d+\.\d+\.\d+')

    def test_invalid_port_fails_without_starting_server(self):
        result = subprocess.run([sys.executable, str(ROOT / 'app.py'), '--port', '65536', '--no-browser'], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--port', result.stderr)


if __name__ == '__main__':
    unittest.main()
