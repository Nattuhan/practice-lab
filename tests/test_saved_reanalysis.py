import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from practice_lab import services, app as app_module


class SavedReanalysisTests(unittest.TestCase):
    def test_saved_analysis_preserves_media_and_metadata_without_network(self):
        for source_type in ('youtube', 'local_audio'):
            with self.subTest(source_type=source_type), tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
                root = Path(tmp)
                for name in ('DATA_RESULTS_DIR', 'DATA_AUDIO_DIR', 'DATA_WORK_DIR'):
                    path = root / name
                    path.mkdir()
                    stack.enter_context(patch.object(services, name, path))
                result = services.DATA_RESULTS_DIR / 'sample.json'
                old = dict(id='sample', title='Edited title', sourceType=source_type,
                           tags=['rock'], analysisStartSec=30, analysisEndSec=90,
                           bpm=81, beats=[1, 2], audioTimingRepair={'old': True})
                result.write_text(json.dumps(old))
                audio = services.DATA_AUDIO_DIR / 'sample.wav'
                audio.write_bytes(b'original audio')
                fresh = dict(bpm=162, total_bars=1, duration=60, beats=[0, .37], downbeats=[0], sections=[])
                analyzer = stack.enter_context(patch.object(services, 'run_analyzer', return_value=fresh))
                for name in ('set_job_status', 'update_manifest', 'export_static_assets'):
                    stack.enter_context(patch.object(services, name))
                forbidden = [stack.enter_context(patch.object(services, name, side_effect=AssertionError(name)))
                             for name in ('download_video', 'get_title', 'convert_wav_to_mp3', 'publish_video', 'create_stems', 'publish_session_to_cloud')]
                updated = services.reanalyze_saved_audio('sample')
                self.assertEqual(updated['bpm'], 162)
                self.assertEqual(updated['title'], old['title'])
                self.assertEqual(updated['tags'], old['tags'])
                self.assertEqual(updated['analysisStartSec'], 30)
                self.assertNotIn('audioTimingRepair', updated)
                self.assertEqual(audio.read_bytes(), b'original audio')
                analyzer.assert_called_once_with(audio, 'sample', job_id='sample')
                for mock in forbidden:
                    mock.assert_not_called()
                # A failed analysis must leave the prior successful result available.
                before = result.read_bytes()
                analyzer.side_effect = RuntimeError('inference failed')
                with self.assertRaises(RuntimeError):
                    services.reanalyze_saved_audio('sample')
                self.assertEqual(result.read_bytes(), before)
                audio.unlink()
                with self.assertRaisesRegex(ValueError, '元音声'):
                    services.reanalyze_saved_audio('sample')
                self.assertEqual(result.read_bytes(), before)

    def test_saved_job_can_be_resubmitted_and_cancel_does_not_delete_result(self):
        with patch.object(app_module, 'validate_saved_analysis'), patch.object(app_module, 'submit_queued_job') as submit, patch.object(app_module, 'reanalyze_saved_audio') as analyze:
            spec = {'type': 'reanalyze_saved', 'jobId': 'sample'}
            app_module.submit_job_spec(spec)
            submit.call_args.args[2]()
            analyze.assert_called_once_with('sample')
            self.assertEqual(submit.call_args.kwargs['spec'], spec)

    def test_http_route_queues_saved_analysis_and_reports_missing_audio(self):
        from fastapi.testclient import TestClient
        client = TestClient(app_module.create_app())
        with patch.object(app_module, 'validate_saved_analysis'), patch.object(app_module, 'submit_queued_job', return_value={'jobId': 'sample', 'stage': 'queued', 'message': 'Queued'}) as submit:
            response = client.post('/reanalyze/sample')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(submit.call_args.kwargs['spec']['type'], 'reanalyze_saved')
        with patch.object(app_module, 'validate_saved_analysis', side_effect=ValueError('保存済みの元音声がありません')):
            response = client.post('/reanalyze/sample')
            self.assertEqual(response.status_code, 400)
            self.assertIn('元音声', response.json()['detail'])

    def test_rejects_path_traversal(self):
        with self.assertRaisesRegex(ValueError, '曲ID'):
            services.validate_saved_analysis('../outside')
