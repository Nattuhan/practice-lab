import json
from unittest.mock import patch

from practice_lab import services
from practice_lab.timing import section_boundary_times


def test_editor_noop_rename_split_and_repeat_preserve_source_times(tmp_path):
    data = dict(id='example', title='Example', bpm=160, total_bars=6, duration=20,
                downbeats=[8, 10, 12, 14, 16, 18], sections=[
        dict(label='start', start_bar=1, end_bar=1, start_time=0, end_time=.4),
        dict(label='intro', start_bar=2, end_bar=3, start_time=.4, end_time=12),
        dict(label='verse', start_bar=4, end_bar=6, start_time=12, end_time=20),
    ])
    path = tmp_path / 'example.json'
    path.write_text(json.dumps(data))
    draft = [dict(label=s['label'], startBar=s['start_bar'], endBar=s['end_bar']) for s in data['sections']]
    with patch.object(services, 'DATA_RESULTS_DIR', tmp_path), patch.object(services, 'load_manifest', return_value=[]), patch.object(services, 'replace_manifest_entry_preserving_order'), patch.object(services, 'export_static_assets'):
        for _ in range(2):
            saved = services.save_sections('example', draft)
            assert [(s['start_time'], s['end_time']) for s in saved['sections']] == [(0, .4), (.4, 12), (12, 20)]
        draft[1]['label'] = 'rename'
        saved = services.save_sections('example', draft)
        assert saved['sections'][1]['end_time'] == 12
        times = section_boundary_times(saved)
        draft[1]['endBar'] = 2
        draft[2]['startBar'] = 3
        moved = services.save_sections('example', draft)
        assert moved['sections'][1]['end_time'] == round(times[2], 2)
        assert moved['sections'][2]['start_time'] == round(times[2], 2)
        assert section_boundary_times(moved) == times
        restored = services.save_sections('example', [], restore_automatic=True)
        assert restored['sections'] == data['sections']
        assert 'sectionBoundaryTimes' not in restored
