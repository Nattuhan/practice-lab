const test = require('node:test');
const assert = require('node:assert/strict');
const { parseMacAudioOutput, createAudioOutputReader } = require('../audio-output.cjs');

const data = active => ({ SPAudioDataType: [{ _items: [
  { _name: 'Connected BT', coreaudio_device_transport: 'coreaudio_device_type_bluetooth',
    coreaudio_default_audio_output_device: active === 'bluetooth' ? 'spaudio_yes' : undefined },
  { _name: 'Internal', coreaudio_device_transport: 'coreaudio_device_type_builtin',
    coreaudio_default_audio_system_device: 'spaudio_yes',
    coreaudio_default_audio_output_device: active === 'builtin' ? 'spaudio_yes' : undefined },
] }] });

test('only the active media output is classified, not a connected headset or alert output', () => {
  assert.deepEqual(parseMacAudioOutput(data('builtin')), { transport: 'builtin', name: 'Internal' });
  assert.deepEqual(parseMacAudioOutput(data('bluetooth')), { transport: 'bluetooth', name: 'Connected BT' });
  assert.equal(parseMacAudioOutput(data('none')).transport, 'unknown');
});

test('probe is cached and fails closed instead of keeping a disconnected Bluetooth device', async () => {
  let now = 0, calls = 0;
  const reader = createAudioOutputReader({ platform: 'darwin', now: () => now, execute: async () => {
    calls++;
    if (calls > 1) throw new Error('probe failed');
    return { stdout: JSON.stringify(data('bluetooth')) };
  } });
  assert.equal((await reader()).transport, 'bluetooth');
  assert.equal((await reader()).transport, 'bluetooth');
  assert.equal(calls, 1);
  now = 2000;
  assert.equal((await reader()).transport, 'unknown');
  assert.equal((await createAudioOutputReader({ platform: 'win32' })()).transport, 'unknown');
});
