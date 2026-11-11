"""Package only reviewed project files; exclude user data and Git history."""
from pathlib import Path
import argparse
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'app.py', 'web/index.html', 'web/app.js', 'web/references.js',
    'start.bat', 'start.sh', 'README.md', 'LICENSE', 'CHANGELOG.md',
    'CONTRIBUTING.md', 'requirements-dev.txt', '.gitignore', '.gitattributes',
    '.github/workflows/ci.yml', 'docs/usage.md', 'docs/github-upload.md',
    'docs/assets/preview.jpg', 'tests/test_app.py', 'tests/test_distribution.py',
    'scripts/package_release.py',
)


def build(output_dir):
    version = re.search(r'^VERSION = "([0-9.]+)"', (ROOT / 'app.py').read_text(encoding='utf-8'), re.M).group(1)
    missing = [name for name in FILES if not (ROOT / name).is_file()]
    if missing:
        raise FileNotFoundError('Missing package files: ' + ', '.join(missing))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f'gpt-image-studio-{version}.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
        for name in FILES:
            file = ROOT / name
            if file.is_symlink():
                raise ValueError('Do not package symlinks: ' + name)
            package.write(file, 'gpt-image-studio/' + name)
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise ValueError('Archive integrity check failed')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    print(build(args.output_dir))
