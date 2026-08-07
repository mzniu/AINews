"""Tests for ingestion image downloader."""
from __future__ import annotations

from services.ingestion.asset_downloader import (
    _referer_candidates,
    is_wechat_cdn_url,
    is_wechat_hotlink_placeholder,
)


def test_is_wechat_cdn_url():
    assert is_wechat_cdn_url("https://mmbiz.qpic.cn/sz_mmbiz_jpg/abc/0?wx_fmt=jpeg")
    assert not is_wechat_cdn_url("https://static.leiphone.com/uploads/new/images/foo.jpg")


def test_referer_candidates_prefers_wechat_for_mmbiz():
    refs = _referer_candidates(
        "https://mmbiz.qpic.cn/sz_mmbiz_jpg/abc/0?wx_fmt=jpeg",
        "https://www.qbitai.com/article/1",
    )
    assert refs[0] == "https://mp.weixin.qq.com/"
    assert "https://www.qbitai.com/article/1" in refs


def test_placeholder_detection_by_utf8_marker():
    content = "此图片来自微信公众平台".encode("utf-8") + b"\x00" * 100
    assert is_wechat_hotlink_placeholder(content)
