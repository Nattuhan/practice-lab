import subprocess
import unittest
from unittest.mock import patch

from practice_lab.source_media import extract_video_id, get_thumbnail_url
from practice_lab.storage import build_manifest_entry


class YoutubeMusicTests(unittest.TestCase):
    def test_music_and_regular_links_share_source_id(self):
        for url in (
            'https://music.youtube.com/watch?v=TXO9p00KY2o&list=album',
            'https://www.youtube.com/watch?v=TXO9p00KY2o',
            'https://m.youtube.com/watch?v=TXO9p00KY2o',
            'https://youtu.be/TXO9p00KY2o',
        ):
            with self.subTest(url=url):
                self.assertEqual(extract_video_id(url), 'TXO9p00KY2o')
        for url in ('https://music.youtube.com/', 'https://music.youtube.com.evil.test/watch?v=x'):
            self.assertIsNone(extract_video_id(url))

    def test_artwork_survives_manifest_export(self):
        url = 'https://music.youtube.com/watch?v=example'
        artwork = 'https://i.ytimg.com/vi/example/maxresdefault.jpg'
        with patch('practice_lab.source_media.run_yt_dlp', return_value=subprocess.CompletedProcess([], 0, artwork + '\n', '')) as run:
            thumbnail = get_thumbnail_url(url)
        self.assertEqual(run.call_args.args[-1], url)
        entry = build_manifest_entry({'id': 'example', 'title': 'Song', 'bpm': 120, 'thumbnailUrl': thumbnail}, entry_date='2026-10-10')
        self.assertEqual(entry['thumbnailUrl'], artwork)

    def test_artwork_failure_is_optional(self):
        for result in (subprocess.CompletedProcess([], 1, '', 'failed'), subprocess.CompletedProcess([], 0, 'NA\n', '')):
            with patch('practice_lab.source_media.run_yt_dlp', return_value=result):
                self.assertIsNone(get_thumbnail_url('https://music.youtube.com/watch?v=example'))
        with patch('practice_lab.source_media.run_yt_dlp', side_effect=subprocess.TimeoutExpired([], 10)):
            self.assertIsNone(get_thumbnail_url('https://music.youtube.com/watch?v=example'))
