# -*- coding: utf-8 -*-
"""
test_youtube_scraper.py — Unit Tests for YouTube Video Extractor (Zero-Quota Innertube)
"""
import pytest
from unittest.mock import patch, MagicMock

from buff_sub.youtube_scraper import (
    normalize_channel_url,
    get_channel_latest_videos,
    _VIDEO_CACHE,
)


def test_normalize_channel_url():
    """Verify channel URL normalization across multiple input formats."""
    assert normalize_channel_url("@BenjaminTran") == "https://www.youtube.com/@BenjaminTran/videos"
    assert normalize_channel_url("https://www.youtube.com/@BenjaminTran") == "https://www.youtube.com/@BenjaminTran/videos"
    assert normalize_channel_url("https://www.youtube.com/@BenjaminTran/shorts") == "https://www.youtube.com/@BenjaminTran/videos"
    assert normalize_channel_url("https://www.youtube.com/@BenjaminTran/featured") == "https://www.youtube.com/@BenjaminTran/videos"
    assert normalize_channel_url("https://www.youtube.com/channel/UC123456789") == "https://www.youtube.com/channel/UC123456789/videos"
    assert normalize_channel_url("") == ""
    assert normalize_channel_url("   ") == ""


def test_get_channel_latest_videos_lockup_view_model():
    """Test extracting videos from modern 2024-2026 lockupViewModel schema."""
    sample_html = """
    <html>
    <body>
    <script>
    var ytInitialData = {
        "contents": {
            "twoColumnBrowseResultsRenderer": {
                "tabs": [{
                    "tabRenderer": {
                        "content": {
                            "sectionListRenderer": {
                                "contents": [{
                                    "itemSectionRenderer": {
                                        "contents": [{
                                            "gridRenderer": {
                                                "items": [
                                                    {
                                                        "lockupViewModel": {
                                                            "contentId": "VID_LOCKUP_001",
                                                            "metadata": {
                                                                "lockupMetadataViewModel": {
                                                                    "title": {"content": "Modern AI Tutorial"}
                                                                }
                                                            }
                                                        }
                                                    },
                                                    {
                                                        "lockupViewModel": {
                                                            "contentId": "VID_LOCKUP_002",
                                                            "metadata": {
                                                                "lockupMetadataViewModel": {
                                                                    "title": {"content": "Python Deep Dive"}
                                                                }
                                                            }
                                                        }
                                                    }
                                                ]
                                            }
                                        }]
                                    }
                                }]
                            }
                        }
                    }
                }]
            }
        }
    };
    </script>
    </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = sample_html

    with patch("requests.Session.get", return_value=mock_resp):
        videos = get_channel_latest_videos("https://www.youtube.com/@MockChannel", limit=5, force_refresh=True)
        assert len(videos) == 2
        assert videos[0]["video_id"] == "VID_LOCKUP_001"
        assert videos[0]["title"] == "Modern AI Tutorial"
        assert videos[0]["url"] == "https://www.youtube.com/watch?v=VID_LOCKUP_001"
        assert videos[1]["video_id"] == "VID_LOCKUP_002"


def test_get_channel_latest_videos_legacy_video_renderer():
    """Test extracting videos from legacy videoRenderer schema."""
    sample_html = """
    <html>
    <body>
    <script>
    var ytInitialData = {
        "contents": {
            "twoColumnBrowseResultsRenderer": {
                "tabs": [{
                    "tabRenderer": {
                        "content": {
                            "richGridRenderer": {
                                "contents": [
                                    {
                                        "richItemRenderer": {
                                            "content": {
                                                "videoRenderer": {
                                                    "videoId": "LEGACY_VID_999",
                                                    "title": {
                                                        "runs": [{"text": "Classic Coding Stream"}]
                                                    }
                                                }
                                            }
                                        }
                                    }
                                ]
                            }
                        }
                    }
                }]
            }
        }
    };
    </script>
    </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = sample_html

    with patch("requests.Session.get", return_value=mock_resp):
        videos = get_channel_latest_videos("https://www.youtube.com/@LegacyChannel", limit=5, force_refresh=True)
        assert len(videos) == 1
        assert videos[0]["video_id"] == "LEGACY_VID_999"
        assert videos[0]["title"] == "Classic Coding Stream"


def test_get_channel_latest_videos_error_handling():
    """Test graceful handling of HTTP 404 or network timeout without raising exceptions."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"

    with patch("requests.Session.get", return_value=mock_resp):
        videos = get_channel_latest_videos("https://www.youtube.com/@NonExistent", limit=5, force_refresh=True)
        assert videos == []

    # Network Exception
    with patch("requests.Session.get", side_effect=Exception("Connection timed out")):
        videos = get_channel_latest_videos("https://www.youtube.com/@TimeoutChannel", limit=5, force_refresh=True)
        assert videos == []


def test_get_channel_latest_videos_caching():
    """Verify in-memory cache avoids duplicate network requests."""
    channel_url = "https://www.youtube.com/@CacheTest"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = """
    <script>
    var ytInitialData = {
        "dummy": {
            "lockupViewModel": {
                "contentId": "CACHED_VID_123",
                "metadata": {"lockupMetadataViewModel": {"title": {"content": "Cached Video"}}}
            }
        }
    };
    </script>
    """

    with patch("requests.Session.get", return_value=mock_resp) as mock_get:
        # First call: makes request
        res1 = get_channel_latest_videos(channel_url, limit=2, force_refresh=True)
        assert len(res1) == 1
        assert mock_get.call_count == 1

        # Second call: uses cache, no extra request
        res2 = get_channel_latest_videos(channel_url, limit=2, force_refresh=False)
        assert len(res2) == 1
        assert res2[0]["video_id"] == "CACHED_VID_123"
        assert mock_get.call_count == 1
