export const filterLibraryItems = (items, { query = "", filter = "all" } = {}) => {
  const normalizedQuery = query.trim().toLocaleLowerCase("ja");
  return items.filter(item => {
    if (filter === "unpracticed" && item.lastPracticedAt) return false;
    if (!normalizedQuery) return true;
    const haystack = [item.title, ...(item.tags || [])].join(" ").toLocaleLowerCase("ja");
    return haystack.includes(normalizedQuery);
  });
};

export const sortLibraryItems = (items, mode = "manual") => {
  if (mode === "manual") return items;
  const sorted = [...items];
  if (mode === "recent") {
    sorted.sort((left, right) => String(right.lastPracticedAt || "").localeCompare(String(left.lastPracticedAt || "")));
  } else if (mode === "added") {
    sorted.sort((left, right) => String(right.date || "").localeCompare(String(left.date || "")));
  } else if (mode === "title") {
    sorted.sort((left, right) => String(left.title || "").localeCompare(String(right.title || ""), "ja"));
  }
  return sorted;
};
