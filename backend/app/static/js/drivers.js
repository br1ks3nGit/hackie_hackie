// After a sort/page/clear link swaps a list table, move focus to its live count.
const LIST_TABLES = { "drivers-table": "drivers-count", "incidents-table": "incidents-count" };
document.addEventListener("htmx:afterSwap", (evt) => {
  const detail = evt.detail;
  if (!detail.target || !(detail.target.id in LIST_TABLES)) return;
  if (!detail.requestConfig || !detail.requestConfig.elt || detail.requestConfig.elt.tagName !== "A") return;
  const count = document.getElementById(LIST_TABLES[detail.target.id]);
  if (count) count.focus();
});
