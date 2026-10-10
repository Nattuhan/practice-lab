const STORAGE_KEY = 'practice_lab_column_widths_v1';

export const initColumnResize = () => {
  let widths = {};
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved && typeof saved === 'object') widths = saved;
  } catch {}
  const root = document.documentElement;
  const workspace = document.getElementById('structure-workspace');
  const columns = [
    { key: 'library', id: 'sidebar', handle: 'library-column-resize', variable: '--library-column-width', direction: 1, breakpoint: 680,
      bounds: () => [200, Math.max(200, Math.min(520, window.innerWidth - 460))] },
    { key: 'mixer', id: 'stem-panel', handle: 'mixer-column-resize', variable: '--mixer-column-width', direction: -1, breakpoint: 900,
      bounds: () => [220, Math.max(220, Math.min(480, workspace.getBoundingClientRect().width - 336))] },
  ];
  const save = () => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(widths)); } catch {}
  };
  const update = () => {
    for (const column of columns) {
      const element = document.getElementById(column.id);
      const handle = document.getElementById(column.handle);
      const [min, max] = column.bounds();
      // Keep the preferred width when the window shrinks, but reserve room for
      // the player. Mobile uses its existing drawer/stacked layout instead.
      if (Number.isFinite(widths[column.key])) {
        root.style.setProperty(column.variable, `${Math.max(min, Math.min(max, widths[column.key]))}px`);
      } else {
        root.style.removeProperty(column.variable);
      }
      handle.setAttribute('aria-valuemin', min);
      handle.setAttribute('aria-valuemax', max);
      handle.setAttribute('aria-valuenow', Math.round(element.getBoundingClientRect().width));
    }
  };
  for (const column of columns) {
    const element = document.getElementById(column.id);
    const handle = document.getElementById(column.handle);
    let drag = null;
    handle.addEventListener('pointerdown', event => {
      if (event.button !== 0 || window.innerWidth <= column.breakpoint) return;
      event.preventDefault();
      handle.focus({ preventScroll: true });
      drag = { id: event.pointerId, x: event.clientX, width: element.getBoundingClientRect().width };
      handle.setPointerCapture(event.pointerId);
      document.body.classList.add('column-resizing');
    });
    handle.addEventListener('pointermove', event => {
      if (!drag || event.pointerId !== drag.id) return;
      const [min, max] = column.bounds();
      widths[column.key] = Math.max(min, Math.min(max, drag.width + column.direction * (event.clientX - drag.x)));
      update();
    });
    const finish = () => {
      if (!drag) return;
      drag = null;
      document.body.classList.remove('column-resizing');
      save();
    };
    handle.addEventListener('pointerup', event => {
      if (drag?.id !== event.pointerId) return;
      handle.releasePointerCapture(event.pointerId);
      finish();
    });
    handle.addEventListener('pointercancel', finish);
    handle.addEventListener('lostpointercapture', finish);
    const reset = () => {
      delete widths[column.key];
      update();
      save();
    };
    handle.addEventListener('dblclick', reset);
    handle.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return;
      event.preventDefault();
      if (event.key === 'Home') return reset();
      const [min, max] = column.bounds();
      const delta = (event.key === 'ArrowRight' ? 10 : -10) * column.direction;
      widths[column.key] = Math.max(min, Math.min(max, element.getBoundingClientRect().width + delta));
      update();
      save();
    });
  }
  window.addEventListener('resize', update);
  // A library resize also changes the room available to the mixer column.
  new ResizeObserver(update).observe(workspace);
  update();
};
