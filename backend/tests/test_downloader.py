from downloader import clip_basename, safe_title


def test_safe_title_strips_unsafe_chars():
    assert safe_title('a/b\\c:d*e?"f<g>h|i') == "abcdefghi"


def test_safe_title_empty_falls_back():
    assert safe_title("") == "clip"
    assert safe_title("   ") == "clip"


def test_safe_title_all_symbols_falls_back():
    assert safe_title("🔥🔥🔥") == "clip"


def test_safe_title_keeps_unicode_letters():
    assert safe_title("café ключ") == "café ключ"


def test_safe_title_truncates():
    assert len(safe_title("a" * 200)) == 60


def test_clip_basename_format():
    assert clip_basename(1, 1234, "Big Play") == "01_1234views_Big Play"
    assert clip_basename(12, 5, "") == "12_5views_clip"
