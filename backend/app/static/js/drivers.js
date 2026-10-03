// After a sort/page/clear link swaps the drivers table, move focus to the live count.
document.addEventListener("htmx:afterSwap", (evt) => {
  const detail = evt.detail;
  if (!detail.target || detail.target.id !== "drivers-table") return;
  if (!detail.requestConfig || !detail.requestConfig.elt || detail.requestConfig.elt.tagName !== "A") return;
  const count = document.getElementById("drivers-count");
  if (count) count.focus();
});
