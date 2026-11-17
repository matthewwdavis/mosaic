// Size > Find a Journal…: every journal mosaic knows, your own, and the journal library's (the one
// prose uses too), found by name, ISSN or abbreviation. A journal from the library is fetched the
// first time it's chosen (its checksum checked) and kept on this computer, where prose sees it too.
//
// Badges: Verified (a maintainer checked it against the journal's guidelines), Community (shared by
// someone, passed every automatic check, not yet checked by a maintainer).

export const BADGES = {
  verified: { label: "Verified", title: "A maintainer checked it against the journal's own guidelines", colour: "#2e7d32" },
  community: { label: "Community", title: "Shared by someone; passed every automatic check, not yet checked by a maintainer", colour: "#8a8a8a" },
  unverified: { label: "Not checked", title: "Not checked against the journal's guidelines", colour: "#8a8a8a" },
};

const WHERE = { built_in: "in mosaic", fetched: "on this computer (from the library)", mine: "one of your own", library: "from the library" };

// One result in words: [name, its badge (or null), the line under it]
export function describeResult(r) {
  const issn = r.issn && r.issn.length ? ` · ISSN ${r.issn.join(", ")}` : "";
  return [r.name, BADGES[r.verified] || null, `${r.publisher || r.group || ""}${issn} · ${WHERE[r.where] || ""}`];
}

// The figure types a journal's page can take, as buttons say them
export function typeLabels(journal, len = (mm) => `${mm} mm`) {
  const out = [];
  if (journal.any_width) out.push({ type: null, label: `Any size up to ${len(Math.max(...journal.types.map((t) => t.width_mm)))} × ${len(journal.depth_mm)}` });
  for (const t of journal.types || []) out.push({ type: t.name, label: `${t.name} (${len(t.width_mm)} × ${len(journal.depth_mm)})` });
  return out;
}
