export function dispatch(items: string[], sent: string[], limit: number): { status: string; count: number } {
  if (limit < 0) {
    throw new Error("limit must be nonnegative");
  }
  if (items.length === 0) {
    return { status: "empty", count: 0 };
  }
  const selected = items.slice(0, Math.min(limit, items.length));
  sent.push(...selected);
  return { status: "sent", count: selected.length };
}
