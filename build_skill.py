"""Build a reproducible installable skill ZIP from the current source files."""
from pathlib import Path
import zipfile
ROOT = Path(__file__).resolve().parent


def build(destination=None):
    destination = Path(destination) if destination else ROOT / 'ai-token-saver.zip'
    files = [ROOT / 'SKILL.md', *ROOT.glob('*.py'), *sorted((ROOT / 'references').glob('*.md'))]
    files = sorted(files)
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            info = zipfile.ZipInfo('ai-token-saver/' + path.relative_to(ROOT).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return destination


if __name__ == '__main__':
    print(build())
