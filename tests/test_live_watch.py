import json
import zipfile
import pytest
from live_watch import LiveWatcher, main
from build_skill import build


def test_live_changes_and_restart_do_not_rewrite_unchanged_input(tmp_path):
    source=tmp_path/'in.txt'; output=tmp_path/'out.txt'
    source.write_text('First fact.\n')
    watcher=LiveWatcher(source,output)
    assert watcher.update()['changed']
    stamp=output.stat().st_mtime_ns
    assert not watcher.update()['changed']
    assert not LiveWatcher(source,output).update()['changed']
    assert output.stat().st_mtime_ns==stamp
    source.write_text('New exact fact: 123.\n')
    assert watcher.update()['changed']; assert output.read_text()=='New exact fact: 123.\n'
    output.write_text('corrupt')
    assert watcher.update()['changed']; assert output.read_text()=='New exact fact: 123.\n'


def test_failed_output_does_not_advance_saved_fingerprint(tmp_path,monkeypatch):
    source=tmp_path/'in.txt'; source.write_text('fact'); output=tmp_path/'out.txt'; watcher=LiveWatcher(source,output)
    import live_watch
    monkeypatch.setattr(live_watch,'write_state_file',lambda *a: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError):watcher.update()
    assert not watcher.state.exists()


def test_watch_rejects_overwriting_input_and_invalid_interval(tmp_path):
    with pytest.raises(ValueError):LiveWatcher(tmp_path/'same',tmp_path/'same')
    with pytest.raises(SystemExit):main(['in','--output','out','--interval','nan'])


def test_packaged_skill_includes_live_modules_and_latest_instructions(tmp_path):
    with zipfile.ZipFile(build(tmp_path/'skill.zip')) as archive:
        assert 'ai-token-saver/live_watch.py' in archive.namelist()
        assert 'ai-token-saver/update_skill.py' in archive.namelist()
        assert 'ai-token-saver/references/live-updates.md' in archive.namelist()
        assert b'Live context and updates' in archive.read('ai-token-saver/SKILL.md')
