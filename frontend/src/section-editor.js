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
