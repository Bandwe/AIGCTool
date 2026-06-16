# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import splitter


def test_is_video():
    assert splitter.is_video("a.mp4")
    assert splitter.is_video("A.MKV")
    assert not splitter.is_video("a.txt")
    assert not splitter.is_video("noext")


def test_natural_key_sorts_numerically():
    # 自然排序：10 排在 2 之后，而非字典序的 "10" < "2"
    names = ["v10.mp4", "v2.mp4", "v1.mp4", "v100.mp4"]
    ordered = sorted(names, key=splitter.natural_key)
    assert ordered == ["v1.mp4", "v2.mp4", "v10.mp4", "v100.mp4"]
    # 工具自己产出的零填充命名也正确
    padded = ["003.mp4", "001.mp4", "010.mp4", "002.mp4"]
    assert sorted(padded, key=splitter.natural_key) == \
        ["001.mp4", "002.mp4", "003.mp4", "010.mp4"]


def test_seg_time_for_count():
    assert splitter.seg_time_for_count(100.0, 4) == 25.0
    # 极短视频也有下限，不会得到 0
    assert splitter.seg_time_for_count(0.01, 10) == 0.05


def test_seg_time_for_count_invalid():
    for bad in (0, -3):
        try:
            splitter.seg_time_for_count(100.0, bad)
        except ValueError:
            pass
        else:
            assert False, "应对非正段数报错"


def test_default_out_dir():
    out = splitter.default_out_dir(os.path.join("X:", "v", "movie.mp4"))
    assert out.endswith("movie_片段")


def test_merge_requires_two():
    try:
        splitter.merge(["only_one.mp4"], "out.mp4")
    except ValueError:
        pass
    else:
        assert False, "合并少于 2 个应报错"
