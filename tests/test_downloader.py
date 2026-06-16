# -*- coding: utf-8 -*-
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import downloader


def test_detect_platform():
    assert downloader.detect_platform("https://www.bilibili.com/video/BV1xx") == "bilibili"
    assert downloader.detect_platform("https://b23.tv/abc") == "bilibili"
    assert downloader.detect_platform("https://www.youtube.com/watch?v=x") == "youtube"
    assert downloader.detect_platform("https://youtu.be/x") == "youtube"
    assert downloader.detect_platform("https://example.com/v") == "other"


def test_build_args_bilibili_with_cookie():
    args = downloader.build_args("https://b.com/v", "D:\\out", "bilibili",
                                 cookie="c.txt", has_ffmpeg_flag=True)
    assert "yt-dlp" in args[0].lower() or args[0].endswith("yt-dlp.exe")
    assert "--cookies" in args and "c.txt" in args
    # B站不强制指定 -f
    assert "-f" not in args


def test_build_args_youtube_sets_format():
    args = downloader.build_args("https://youtu.be/x", "D:\\out", "youtube",
                                 cookie="", has_ffmpeg_flag=True)
    assert "-f" in args and "bv*+ba/b" in args
    assert "--cookies" not in args


def test_build_args_no_ffmpeg_skips_merge():
    args = downloader.build_args("https://b.com/v", "D:\\out", "bilibili",
                                 cookie="", has_ffmpeg_flag=False)
    assert "--merge-output-format" not in args
    assert "--ffmpeg-location" not in args


def test_find_cookie_explicit():
    d = tempfile.mkdtemp()
    cookie = os.path.join(d, "my_cookies.txt")
    with open(cookie, "w") as f:
        f.write("# cookie")
    assert downloader.find_cookie("youtube", explicit=cookie) == os.path.abspath(cookie)


def test_cookie_candidate_order():
    cands = downloader._cookie_candidates("bilibili", "X:\\my.txt", "S:\\dir")
    cands = [c for c in cands if c]
    assert cands[0] == "X:\\my.txt"
    assert any("www.bilibili.com_cookies.txt" in c for c in cands)
    assert os.path.join("S:\\dir", "cookies.txt") in cands
