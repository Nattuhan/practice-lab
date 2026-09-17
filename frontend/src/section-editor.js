export const mutateSectionDraft = (draft, index, action) => {
  const next = draft.map(section => ({ ...section }));
  const section = next[index];
  if (!section) return next;

  if (action === "split" && section.startBar < section.endBar) {
    const midpoint = Math.floor((section.startBar + section.endBar) / 2);
    next.splice(index, 1,
      { ...section, endBar: midpoint },
      { ...section, startBar: midpoint + 1 },
    );
  } else if (action === "merge" && next[index + 1]) {
    next.splice(index, 2, { ...section, endBar: next[index + 1].endBar });
  } else if (action === "delete" && next.length > 1) {
    if (index > 0) next[index - 1].endBar = section.endBar;
    else next[index + 1].startBar = section.startBar;
    next.splice(index, 1);
  }
  return next;
};

export const normalizeSectionDraft = (draft, totalBars) => {
  const limit = Math.max(0, Math.round(Number(totalBars) || 0));
  if (!draft.length || limit < 1 || draft.length > limit) return draft.map(section => ({ ...section }));

  let nextStart = 1;
  return draft.map((section, index) => {
    const remaining = draft.length - index - 1;
    const maxEnd = limit - remaining;
    const rawEnd = Math.round(Number(section.endBar) || nextStart);
    const endBar = index === draft.length - 1 ? limit : Math.max(nextStart, Math.min(maxEnd, rawEnd));
    const normalized = { ...section, startBar: nextStart, endBar };
    nextStart = endBar + 1;
    return normalized;
  });
};

// A bar label is not an elapsed-time coordinate (pickups, rests and meter
// changes have different lengths). Keep the source section times as anchors.
export const sectionBoundaryTimes = data => {
  const total = Math.max(0, Math.round(Number(data.total_bars) || 0));
  if (data.sectionBoundaryTimes?.length === total + 1) return data.sectionBoundaryTimes;
  const source = data.sections || [];
  const normalized = normalizeSectionDraft(source.map(section => ({
    startBar: section.start_bar, endBar: section.end_bar,
  })), total);
  const times = Array.from({ length: total + 1 }, (_, i) => (data.duration || 0) * i / Math.max(1, total));
  normalized.forEach((section, index) => {
    const start = Number(source[index].start_time);
    const end = Number(source[index].end_time);
    const count = section.endBar - section.startBar + 1;
    for (let i = 0; i <= count; i++) times[section.startBar - 1 + i] = start + (end - start) * i / count;
  });
  return times;
};

export const nearestSectionBoundary = (times, time) => times.reduce(
  (best, value, index) => Math.abs(value - time) < Math.abs(times[best] - time) ? index : best, 0,
);
