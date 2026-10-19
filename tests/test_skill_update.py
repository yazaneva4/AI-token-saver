import subprocess
import pytest
import update_skill


def git(root, *args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True,stderr=subprocess.PIPE).strip()


def commit(root, text):
    (root/'context.txt').write_text(text)
    git(root,'add','context.txt')
    git(root,'-c','user.name=Skill Test','-c','user.email=test@example.invalid','commit','-m',text)
    return git(root,'rev-parse','HEAD')


def test_clean_install_updates_but_dirty_or_diverged_install_is_preserved(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir();git(source,'init','-b','main')
    first=commit(source,'first')
    remote=tmp_path/'official.git';subprocess.check_call(['git','clone','--bare',str(source),str(remote)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    install=tmp_path/'install';subprocess.check_call(['git','clone',str(remote),str(install)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    monkeypatch.setattr(update_skill,'EXPECTED',str(remote).removesuffix('.git'))
    latest=commit(source,'second');git(source,'push',str(remote),'HEAD:main')
    result=update_skill.check(root=install);assert result['update_available'];assert git(install,'rev-parse','HEAD')==first
    (install/'context.txt').write_text('unsaved')
    with pytest.raises(ValueError,match='Local edits'):update_skill.check(True,root=install)
    assert (install/'context.txt').read_text()=='unsaved'
    git(install,'restore','context.txt')
    result=update_skill.check(True,root=install);assert result['updated'];assert result['current']==latest;assert (install/'context.txt').read_text()=='second'
    local=commit(install,'my local change');commit(source,'upstream change');git(source,'push',str(remote),'HEAD:main')
    with pytest.raises(subprocess.CalledProcessError):update_skill.check(True,root=install)
    assert git(install,'rev-parse','HEAD')==local;assert (install/'context.txt').read_text()=='my local change'


def test_freshness_check_rejects_an_unrelated_repository(tmp_path):
    repo=tmp_path/'other';repo.mkdir();git(repo,'init');git(repo,'remote','add','origin','https://example.invalid/other.git')
    with pytest.raises(ValueError,match='official'):update_skill.check(root=repo)
