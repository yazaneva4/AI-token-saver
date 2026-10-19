"""Watch a local UTF-8 context file and publish only changed compacted snapshots."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from ai_token_saver import compact_text, write_state_file


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class LiveWatcher:
    def __init__(self, source, output, state=None, dedupe='runs'):
        self.source = Path(source).resolve()
        self.output = Path(output).resolve()
        self.state = Path(state).resolve() if state else self.output.with_suffix(self.output.suffix + '.state.json')
        if len({self.source, self.output, self.state}) != 3:
            raise ValueError('source, output and state must be different files')
        self.dedupe = dedupe

    def update(self):
        before = self.source.stat()
        stamp = (before.st_ino, before.st_size, before.st_mtime_ns)
        text = self.source.read_text(encoding='utf-8')
        after = self.source.stat()
        if stamp != (after.st_ino, after.st_size, after.st_mtime_ns):
            return {'changed': False, 'retry': True}
        fingerprint = digest(self.dedupe + '\0' + text)
        try:
            saved = json.loads(self.state.read_text(encoding='utf-8'))
            output_ok = self.output.is_file() and digest(self.output.read_text(encoding='utf-8')) == saved.get('output_digest')
        except (OSError, ValueError, AttributeError):
            saved, output_ok = {}, False
        if saved.get('fingerprint') == fingerprint and output_ok:
            return {'changed': False, 'fingerprint': fingerprint}
        compacted = compact_text(text, dedupe=self.dedupe)
        # Publish the output first. A failed write cannot mark unseen work saved.
        write_state_file(self.output, compacted)
        write_state_file(self.state, json.dumps({'fingerprint': fingerprint, 'output_digest': digest(compacted)}))
        return {'changed': True, 'fingerprint': fingerprint, 'input_characters': len(text), 'output_characters': len(compacted)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--output', required=True)
    parser.add_argument('--state')
    parser.add_argument('--interval', type=float, default=1.0)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--dedupe', choices=['off', 'runs'], default='runs')
    args = parser.parse_args(argv)
    if not math.isfinite(args.interval) or args.interval < 0.1:
        parser.error('--interval must be a finite number of at least 0.1 seconds')
    try:
        watcher = LiveWatcher(args.source, args.output, args.state, args.dedupe)
        while True:
            try:
                result = watcher.update()
                if result['changed'] or args.once:
                    print(json.dumps(result), flush=True)
            except (OSError, ValueError) as exc:
                print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr, flush=True)
                if args.once:
                    return 1
            if args.once:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    raise SystemExit(main())
