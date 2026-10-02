const CONTROL_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON', 'A', 'AUDIO', 'VIDEO']);

export const acceptsPlaybackShortcuts = (target, { dialogOpen = false } = {}) => {
  // Space must open a select or activate its focused control. A modal also
  // owns keys on its backdrop; never restart the hidden player from there.
  if (dialogOpen) return false;
  for (let node = target; node; node = node.parentElement) {
    if (CONTROL_TAGS.has(node.tagName) || node.isContentEditable
        || node.getAttribute?.('role') === 'textbox') return false;
  }
  return true;
};
