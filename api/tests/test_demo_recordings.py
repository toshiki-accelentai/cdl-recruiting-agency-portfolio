"""C4 step 2b: the demo server plays two sample recordings from local files, and never asks VAPI.

With DEMO_RECORDINGS_DIR set, GET /api/calls/{id}/recording serves a file whose name comes from a fixed table keyed by
the call's stored id. The request never supplies a path. Written before the code.
"""
import psycopg
import pytest

from app import recordings
from tests.conftest import TEST_URL
from tests.test_calls_api import add_call, web  # noqa: F401  (web is a pytest fixture)

AUDIO = b"RIFF$\x00\x00\x00WAVEfmt " + b"\x00" * 40  # a stand-in; the endpoint never inspects the audio


@pytest.fixture
def sample_dir(tmp_path, monkeypatch):
    for name in recordings.DEMO_RECORDING_FILES.values():
        (tmp_path / name).write_bytes(AUDIO)
    monkeypatch.setenv("DEMO_RECORDINGS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def no_vapi(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("the demo must never ask VAPI")
    monkeypatch.setattr(recordings, "signed_recording_url", boom)
    monkeypatch.setattr(recordings, "_open_without_redirect", boom)


def sample_call(vapi_id):
    call_id = add_call(vapi_id=vapi_id)
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("UPDATE calls SET has_recording = true WHERE id = %s", (call_id,))
    return call_id


def test_there_are_exactly_two_sample_files_with_fixed_plain_names():
    names = recordings.DEMO_RECORDING_FILES
    assert len(names) == 2
    assert all(name == name.strip() and "/" not in name and "\\" not in name and ".." not in name
               for name in names.values())


def test_a_sample_call_plays_its_own_file(web, sample_dir, no_vapi):
    vapi_id, name = next(iter(recordings.DEMO_RECORDING_FILES.items()))
    r = web.get(f"/api/calls/{sample_call(vapi_id)}/recording", follow_redirects=False)
    assert r.status_code == 200 and r.content == AUDIO
    assert r.headers["content-type"].startswith("audio/")
    assert r.headers["cache-control"] == "no-store"


def test_seeking_works_so_the_transcript_can_jump_the_audio(web, sample_dir, no_vapi):
    vapi_id = next(iter(recordings.DEMO_RECORDING_FILES))
    r = web.get(f"/api/calls/{sample_call(vapi_id)}/recording", headers={"Range": "bytes=0-3"}, follow_redirects=False)
    assert r.status_code == 206 and r.content == AUDIO[:4]


def test_a_call_that_is_not_a_sample_has_no_recording_and_vapi_is_not_asked(web, sample_dir, no_vapi):
    assert web.get(f"/api/calls/{sample_call('demo-call-1')}/recording", follow_redirects=False).status_code == 404


def test_a_missing_file_is_404_not_a_crash(web, sample_dir, no_vapi):
    vapi_id, name = next(iter(recordings.DEMO_RECORDING_FILES.items()))
    (sample_dir / name).unlink()
    assert web.get(f"/api/calls/{sample_call(vapi_id)}/recording", follow_redirects=False).status_code == 404


def test_a_call_without_the_recording_flag_is_404(web, sample_dir, no_vapi):
    vapi_id = next(iter(recordings.DEMO_RECORDING_FILES))
    call_id = add_call(vapi_id=vapi_id)  # has_recording stays false
    assert web.get(f"/api/calls/{call_id}/recording", follow_redirects=False).status_code == 404


def test_without_the_setting_the_normal_vapi_path_is_used(web, monkeypatch):
    monkeypatch.delenv("DEMO_RECORDINGS_DIR", raising=False)
    vapi_id = next(iter(recordings.DEMO_RECORDING_FILES))
    seen = []
    monkeypatch.setattr(recordings, "signed_recording_url", lambda vid: seen.append(vid) or "https://x.invalid/a.wav")
    r = web.get(f"/api/calls/{sample_call(vapi_id)}/recording", follow_redirects=False)
    assert r.status_code == 302 and seen == [vapi_id]
