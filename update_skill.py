"""Check a Git-installed skill for upstream code changes, or update a clean clone."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
EXPECTED = 'https://github.com/yazaneva4/AI-token-saver'


def check(update=False, root=ROOT):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True, stderr=subprocess.PIPE, timeout=30).strip()
    origin = git('remote', 'get-url', 'origin').removesuffix('.git').rstrip('/')
    if origin != EXPECTED:
        raise ValueError('Update only a clone of the official AI-token-saver repository')
    local = git('rev-parse', 'HEAD')
    if update and git('status', '--porcelain'):
        raise ValueError('Local edits exist; commit or save them before updating')
    git('fetch', '--quiet', 'origin', 'main')
    latest = git('rev-parse', 'FETCH_HEAD')
    result = {'current': local, 'latest': latest, 'update_available': local != latest, 'updated': False}
    if update and local != latest:
        git('merge', '--ff-only', 'FETCH_HEAD')
        result.update(current=git('rev-parse', 'HEAD'), update_available=False, updated=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--update', action='store_true', help='Fast-forward a clean clone; reload the skill in its host afterwards')
    args = parser.parse_args(argv)
    try:
        print(json.dumps(check(args.update)))
        return 0
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc), 'hint': 'For ZIP installations, install a fresh package and reload the skill in your host.'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
