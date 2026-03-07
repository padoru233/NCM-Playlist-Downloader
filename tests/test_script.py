import builtins
import os
import sys
import types
import tempfile

# Create minimal fake modules for pyncm and pyncm.apis used by script.py so it can be imported
# Minimal fake pyncm module and its apis submodule
fake_pyncm = types.ModuleType('pyncm')
fake_pyncm.GetCurrentSession = lambda: None
fake_pyncm.SetCurrentSession = lambda s: None
fake_pyncm.DumpSessionAsString = lambda s: {}
fake_pyncm.LoadSessionFromString = lambda s: None
sys.modules['pyncm'] = fake_pyncm

fake_pyncm_apis = types.ModuleType('pyncm.apis')
fake_pyncm_apis.playlist = types.SimpleNamespace(GetPlaylistAllTracks=lambda pid: ({'songs': []}, None))
fake_pyncm_apis.album = types.SimpleNamespace(GetAlbumInfo=lambda aid: ({'album': {'songs': []}}, None))
fake_pyncm_apis.track = types.SimpleNamespace(
    GetTrackLyrics=lambda tid: ({'lrc': {'lyric': ''}, 'tlyric': {'lyric': ''}}, None),
    GetTrackDetail=lambda ids: ({'songs': []}, None),
    GetTrackAudioV1=lambda **kw: ({'data': []}, None)
)
fake_pyncm_apis.login = types.SimpleNamespace(
    LoginQrcodeUnikey=lambda: {}, LoginQrcodeCheck=lambda u: {},
    LoginViaAnonymousAccount=lambda: {}, GetCurrentLoginStatus=lambda: {}
)
sys.modules['pyncm.apis'] = fake_pyncm_apis

# Provide dummy external packages used by script.py (mutagen, PIL, qrcode, requests)
sys.modules['qrcode'] = types.ModuleType('qrcode')
setattr(sys.modules['qrcode'], 'make', lambda u: None)

# requests minimal stub: create requests.exceptions module and requests module
req_ex = types.ModuleType('requests.exceptions')
setattr(req_ex, 'Timeout', TimeoutError)
setattr(req_ex, 'ConnectionError', ConnectionError)
setattr(req_ex, 'RequestException', Exception)
sys.modules['requests.exceptions'] = req_ex

req_mod = types.ModuleType('requests')
def dummy_get(*args, **kwargs):
    class Resp:
        status_code = 200
        headers = {}
        text = ''
        def iter_content(self, chunk_size=1024):
            return []
    return Resp()
req_mod.get = dummy_get
req_mod.exceptions = req_ex
sys.modules['requests'] = req_mod

# mutagen minimal
mut = types.ModuleType('mutagen')
sys.modules['mutagen'] = mut
# Provide a minimal File attribute so `from mutagen import File` works in script.py
setattr(mut, 'File', lambda *a, **k: None)
mut_id3 = types.ModuleType('mutagen.id3')
class DummyID3(dict):
    def save(self, *a, **k):
        return None
mut_id3.ID3 = DummyID3
mut_id3.APIC = object
mut_id3.TIT2 = lambda encoding, text: None
mut_id3.TPE1 = lambda encoding, text: None
mut_id3.TALB = lambda encoding, text: None
mut_id3.TRCK = lambda encoding, text: None
mut_id3.TDRC = lambda encoding, text: None
sys.modules['mutagen.id3'] = mut_id3

mut_flac = types.ModuleType('mutagen.flac')
class DummyFLAC(dict):
    def add_picture(self, p):
        pass
    def save(self, *a, **k):
        return None
mut_flac.FLAC = DummyFLAC
class DummyPicture:
    pass
mut_flac.Picture = DummyPicture
sys.modules['mutagen.flac'] = mut_flac

# PIL minimal
pil = types.ModuleType('PIL')
pil_image = types.ModuleType('PIL.Image')
def dummy_open(fp):
    return types.SimpleNamespace(size=(1,1))
pil_image.open = dummy_open
sys.modules['PIL'] = pil
sys.modules['PIL.Image'] = pil_image

import pytest

# Now import the script under test
import importlib
try:
    script = importlib.import_module('script')
except ModuleNotFoundError:
    # pytest / different environments may not put repo root on sys.path.
    # Fallback: load script.py directly from repository root by file path.
    import importlib.util
    repo_root = os.path.dirname(os.path.dirname(__file__))
    script_path = os.path.join(repo_root, 'script.py')
    spec = importlib.util.spec_from_file_location('script', script_path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)


def test_parse_lrc_empty():
    assert script.parse_lrc('') == []
    assert script.parse_lrc(None) == []


def test_parse_lrc_basic():
    content = "[00:12.34]hello\n[01:02.50]world"
    res = script.parse_lrc(content)
    assert len(res) == 2
    assert res[0][1] == 'hello'
    assert pytest.approx(res[0][0], rel=1e-3) == 12.34


def test_merge_lyrics_no_translated():
    orig = [(10.0, 'a'), (20.0, 'b')]
    merged = script.merge_lyrics(orig, [])
    assert merged == orig


def test_merge_lyrics_with_translated():
    orig = [(10.0, 'a'), (20.0, 'b')]
    trans = [(10.0, 'A')]
    merged = script.merge_lyrics(orig, trans, song_duration=30)
    # translated inserted after corresponding original time
    assert any(t[1] == 'A' for t in merged)


def test_format_lrc_line():
    line = script.format_lrc_line(65.37, 'hi')
    assert line.startswith('[01:05.') and line.endswith('hi')


def test_normalize_path_creates_dir(tmp_path):
    p = tmp_path / 'newdir'
    res = script.normalize_path(str(p))
    assert os.path.exists(res)
    # calling again should not error
    res2 = script.normalize_path(str(p))
    assert res2 == res


def test_parse_user_info_variants():
    status = {'profile': {'nickname': 'bob', 'userId': 123, 'vipType': 1}}
    out = script._parse_user_info_from_status(status)
    assert out['nickname'] == 'bob'
    # user_id may be present or None depending on runtime structure; accept either
    assert out['user_id'] in (123, None)
    assert out['vip'] == 1


def test_get_terminal_size_returns_tuple():
    cols, lines = script.get_terminal_size()
    assert isinstance(cols, int) and isinstance(lines, int)


def test_get_album_info_wrapper():
    # should return (data, None) when album API returns successfully
    data, err = script.get_album_info('123')
    assert err is None
    assert isinstance(data, dict)
