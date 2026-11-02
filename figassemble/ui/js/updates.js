// Updates: a note in the status bar when a new version is ready, the Updates part of Preferences,
// What's new after updating, and signing in to GitHub while the repository is private. Looking,
// downloading and installing happen in Python (updates.py); this asks how it's going.

import { rpc } from "./api.js";
import { button, selectField } from "./inspector.js";
import { store } from "./store.js";
import { announce, h } from "./util.js";

const MODES = [["auto", "Install it automatically"], ["ask", "Ask me first"], ["off", "Don't check for updates"]];
const plain = (err) => String(err?.message || err).replace(/^\w+Error: /, "");

// What's new, as GitHub's release notes are written: "- " lines become a list, "#" lines headings
function notesView(text) {
  const out = [];
  let list = null;
  for (const raw of String(text || "").split(/\r?\n/)) {
    const line = raw.trim();
    if (/^[-*] /.test(line)) {
      if (!list) out.push(list = h("ul", { class: "release-notes" }));
      list.append(h("li", {}, line.slice(2)));
      continue;
    }
    list = null;
    if (line) out.push(/^#+ /.test(line) ? h("p", { class: "notes-heading" }, line.replace(/^#+ /, "")) : h("p", {}, line));
  }
  return out.length ? out : [h("p", { class: "hint" }, "No notes came with this version.")];
}

function since(t) {
  if (!t) return "";
  const min = Math.round((Date.now() / 1000 - t) / 60);
  return min < 1 ? "just now" : min < 60 ? `${min} min ago` : min < 60 * 36 ? `${Math.round(min / 60)} h ago`
    : `${Math.round(min / 60 / 24)} days ago`;
}

export const updates = {
  app: null, panels: null, status: null, chip: null, timer: null, view: null,
  restartDelay: 1800,   // ms to read that FigAssemble closes and opens again (the self-test needs less)

  init(app, panels) {
    this.app = app;
    this.panels = panels;
    // The status bar's note: shown only when there's something to do (or a sign-in is needed)
    this.chip = h("button", { type: "button", class: "btn small update-chip", hidden: true });
    this.chip.addEventListener("click", () => this.chipClicked());
    const bar = document.getElementById("status");
    bar.querySelector(".spacer")?.after(this.chip);
    this.poll(true);
    setInterval(() => this.poll(), 30000);
  },

  async poll(first = false) {
    clearTimeout(this.timer);
    try {
      this.status = await rpc("update_status");
    } catch {
      return;
    }
    this.render();
    if (first && this.status.updated) this.updatedDialog(this.status.updated);
    // Every second while a look, download or sign-in is under way
    if (this.status.busy || this.status.signin?.state === "waiting") this.timer = setTimeout(() => this.poll(), 1000);
  },

  // The version ready to install, the newer one there is (Ask me first), or a failed install
  pending(s = this.status) {
    if (!s || s.kind !== "installed") return null;
    if (s.failed && !s.installing && (!s.staged || s.staged.version === s.failed.version)) return { kind: "failed", ...s.failed };
    if (s.staged && !s.staged.go_back) return { kind: "ready", ...s.staged };
    if (s.update && s.mode === "ask") return { kind: "available", ...s.update };
    if (s.mode !== "off" && s.access === "sign_in" && s.configured) return { kind: "signin" };
    return null;
  },

  render() {
    const p = this.pending();
    const texts = {
      ready: () => [`FigAssemble ${p.version} is ready`, this.status.mode === "auto"
        ? `FigAssemble ${p.version} is downloaded and installs when you quit. Click to see what's new or restart now.`
        : `FigAssemble ${p.version} is downloaded. Click to see what's new and install it.`],
      available: () => [`FigAssemble ${p.version} is out`, `FigAssemble ${p.version} is out. Click to see what's new and update.`],
      failed: () => ["The update didn't install", `FigAssemble ${p.version} didn't install: ${p.error}. Click for more.`],
      signin: () => ["Sign in for updates", "FigAssemble's updates are private for now: sign in to GitHub once to get them."],
    };
    const [label, title] = p ? texts[p.kind]() : ["", ""];
    this.chip.hidden = !p;
    this.chip.textContent = label;
    this.chip.title = title;
    this.chip.setAttribute("aria-label", title);
    this.chip.classList.toggle("warn", p?.kind === "failed");
    if (this.view?.isConnected) this.renderView();
  },

  chipClicked() {
    const p = this.pending();
    if (!p) return;
    if (p.kind === "signin") return this.signInDialog();
    if (p.kind === "failed") return this.failedDialog(p);
    return this.newVersionDialog(p);
  },

  // Check for updates (the menu, the command search): look now and say what there is
  async checkNow() {
    const s = this.status = await rpc("update_check");
    this.render();
    const p = this.pending(s);
    if (s.kind === "source") return this.panels.dialog("Check for updates", h("p", {}, "This FigAssemble runs from its source folder, "
      + "so it doesn't update itself: use git pull."));
    if (s.kind !== "installed") return this.panels.dialog("Check for updates", h("p", {}, this.describe(s)));
    if (p?.kind === "ready" || p?.kind === "available") return this.newVersionDialog(p);
    if (s.access === "sign_in" && s.configured) return this.signInDialog();
    announce(this.describe(s));
    return this.panels.dialog("Check for updates", h("p", {}, this.describe(s)));
  },

  describe(s = this.status || {}) {
    if (s.kind === "source") return "This FigAssemble runs from its source folder, so it doesn't update itself (use git pull).";
    if (s.kind !== "installed") return "This copy of FigAssemble wasn't set up by its installer, so it can't update itself. "
      + "Install the newest version once, and it will from then on.";
    if (s.installing) return "An update is installing.";
    if (s.busy === "checking") return "Looking for a newer version…";
    if (s.busy === "downloading") return `Downloading FigAssemble ${s.update?.version || ""}… ${Math.round((s.progress || 0) * 100)}%`;
    if (s.failed && !(s.staged && s.staged.version !== s.failed.version)) return `FigAssemble ${s.failed.version} didn't install: ${s.failed.error}.`;
    if (s.staged && !s.staged.go_back) return `FigAssemble ${s.staged.version} is ready`
      + (s.mode === "auto" ? ": it installs when you quit FigAssemble, or restart now." : ".");
    if (s.update) return `FigAssemble ${s.update.version} is out${s.update.prerelease ? " (a test version)" : ""}.`;
    if (s.access === "sign_in") return s.configured ? "FigAssemble's updates are private for now: sign in to GitHub once to get them."
      : "Updates aren't set up yet.";
    if (s.access === "no_access") return `Your GitHub account (${s.signed_in}) can't see FigAssemble's releases. `
      + `Ask ${s.owner} to add you to the repository.`;
    if (s.error) return `Couldn't look for updates: ${s.error}.`;
    const skipping = s.skip && s.newest?.version === s.skip ? ` Skipping ${s.skip}.` : "";
    if (!s.checked) return s.mode === "off" ? `You have FigAssemble ${s.version}. It doesn't look for updates.`
      : `You have FigAssemble ${s.version}. It hasn't looked for updates yet.`;
    return `You have FigAssemble ${s.version}, the newest${s.channel === "test" ? ", test versions included" : ""}.${skipping} `
      + `Looked ${since(s.checked)}.`;
  },

  // Preferences > Updates: the setting, test versions, and what's going on with buttons for it
  settingsFieldset() {
    const p = this.app.prefs;
    const s = this.status || {};
    const fs = h("fieldset", { class: "updates" }, h("legend", {}, "Updates"));
    if (s.kind === "installed") {
      const testId = "pref-update-test";
      const test = h("input", { type: "checkbox", id: testId, checked: p.update_channel === "test" });
      test.addEventListener("change", () => this.setPrefs({ update_channel: test.checked ? "test" : "stable" }));
      fs.append(selectField("When a new version is out", p.updates || "auto", MODES, (v) => this.setPrefs({ updates: v })),
        h("label", { class: "check-line", for: testId }, test, h("span", {}, "Get test versions too: newer, but less tried")));
    }
    this.view = h("div", { class: "update-view" });
    fs.append(this.view);
    this.renderView();
    rpc("update_status").then((st) => { this.status = st; this.render(); }).catch(() => {});
    return fs;
  },
  async setPrefs(prefs) {
    await this.app.savePrefs(prefs);
    // A look straight away with the new setting (none when switched off)
    this.status = await rpc(this.app.prefs.updates === "off" ? "update_status" : "update_check");
    this.render();
  },
  renderView() {
    const s = this.status || {};
    const buttons = [];
    const add = (label, fn, cls = "") => buttons.push([label, fn, cls]);
    if (s.kind === "installed") {
      add("Check now", async () => {
        this.status = { ...s, busy: "checking" };
        this.renderView();
        this.status = await rpc("update_check");
        this.render();
      });
      const p = this.pending(s);
      if (p?.kind === "ready") add("Restart now", () => this.install("update"), "primary");
      if (p?.kind === "available") add(`Update to ${p.version}`, () => this.install("update"), "primary");
      if (s.failed) add("Show the log", () => rpc("update_log"));
      if (s.previous) add(`Go back to ${s.previous.version}`, () => this.goBack());
      if (s.skip && s.newest?.version === s.skip && !s.update) {
        add(`Install ${s.skip} after all`, async () => { this.status = await rpc("update_skip", null); this.render(); });
      }
      if (s.configured && !s.signed_in && s.access !== "public") add("Sign in to GitHub…", () => this.signInDialog());
      if (s.signed_in) add("Sign out of GitHub", async () => { this.status = await rpc("github_signout"); this.render(); });
    }
    const said = this.describe(s);
    const signed = s.signed_in ? `Signed in to GitHub as ${s.signed_in}, to download updates.` : "";
    // Redrawn only when something changed, keeping the focus on the button it was on
    const key = JSON.stringify([said, signed, buttons.map((b) => b[0])]);
    if (key === this.viewKey && this.view.childElementCount) return;
    this.viewKey = key;
    const focused = this.view.contains(document.activeElement) ? document.activeElement.textContent : null;
    const row = h("div", { class: "button-row" }, ...buttons.map(([label, fn, cls]) => button(label, fn, label, cls)));
    this.view.replaceChildren(h("p", { class: "update-status", role: "status" }, said),
      signed ? h("p", { class: "hint" }, signed) : null, row);
    if (focused) [...row.querySelectorAll("button")].find((b) => b.textContent === focused)?.focus();
  },

  // A new version: what's new, and installing it (Restart now, or Update now with Ask me first)
  newVersionDialog(v) {
    const ready = v.kind === "ready";
    const act = h("button", { type: "button", class: "btn primary" }, ready ? "Restart now" : "Update now");
    const skip = h("button", { type: "button", class: "btn" }, "Skip this version");
    const extra = [
      v.prerelease ? h("p", { class: "hint" }, "This is a test version: newer, but less tried.") : null,
      v.env_changed ? h("p", { class: "hint" }, "This update also brings new versions of the tools FigAssemble uses, so it takes a few minutes to install.") : null,
      ready && this.status.mode === "auto" ? h("p", { class: "hint" }, "If you don't restart now, it installs when you quit FigAssemble.") : null,
    ];
    const dlg = this.panels.dialog(`FigAssemble ${v.version}`, h("div", { class: "whats-new" }, ...notesView(v.notes), ...extra),
      [act, skip], "Later");
    act.addEventListener("click", () => { dlg.close(); this.install("update"); });
    skip.addEventListener("click", async () => {
      dlg.close();
      this.status = await rpc("update_skip", v.version);
      this.render();
      announce(`Skipping FigAssemble ${v.version}; a newer version will still come`);
    });
  },

  async goBack() {
    const prev = this.status?.previous;
    if (!prev) return;
    const ok = await this.panels.confirm(`Go back to FigAssemble ${prev.version}?`,
      `FigAssemble installs ${prev.version} instead of ${this.status.version} and opens again. Automatic updates skip `
      + `${this.status.version}; the version after it installs as usual. Documents saved with ${this.status.version} may `
      + "use things the older version doesn't know about.", `Go back to ${prev.version}`);
    if (ok) await this.install("previous");
  },

  // Download what's to install (if it isn't yet), then close, install and open again; unsaved
  // work is saved first, or kept as a copy that FigAssemble offers back when it opens
  async install(which) {
    if (store.dirty) {
      const choice = await this.unsavedChoice();
      if (!choice) return;
      if (choice === "save") {
        await this.app.save();
        if (store.dirty) return;
      } else {
        await rpc("autosave", store.doc, store.autosaveKey).catch(() => {});
      }
    }
    const message = h("p", { role: "status" }, "Downloading…");
    const dlg = this.panels.dialog("Updating FigAssemble", message, [], "Cancel");
    try {
      if (which === "previous" || !this.status?.staged || this.status.staged.go_back) this.status = await rpc("update_get", which);
    } catch (err) {
      message.textContent = `It couldn't be downloaded: ${plain(err)}.`;
      return;
    }
    if (!dlg.open) return;   // cancelled meanwhile
    const env = this.status?.staged?.env_changed;
    message.textContent = `FigAssemble closes now and opens again when ${this.status?.staged?.version || "the new version"} is installed, `
      + (env ? "in a few minutes (the tools it uses are updated too)." : "in about a minute.");
    dlg.querySelector("button[value=close]").textContent = "OK";
    await new Promise((r) => setTimeout(r, this.restartDelay));
    if (!(await rpc("update_restart"))) message.textContent = "There's nothing to install after all.";
  },

  unsavedChoice() {
    return new Promise((resolve) => {
      const save = h("button", { type: "button", class: "btn primary" }, "Save and restart");
      const keep = h("button", { type: "button", class: "btn" }, "Restart without saving");
      const dlg = this.panels.dialog("Unsaved changes", h("div", {},
        h("p", {}, "This document has unsaved changes."),
        h("p", { class: "hint" }, "Without saving, FigAssemble keeps a copy and offers it back when it opens again.")), [save, keep]);
      save.addEventListener("click", () => { resolve("save"); dlg.close(); });
      keep.addEventListener("click", () => { resolve("keep"); dlg.close(); });
      dlg.addEventListener("close", () => resolve(null));   // (a promise keeps its first answer)
    });
  },

  failedDialog(f) {
    const s = this.status;
    const again = h("button", { type: "button", class: "btn primary" }, "Try again now");
    const log = h("button", { type: "button", class: "btn" }, "Show the log");
    const dlg = this.panels.dialog("The update didn't install", h("div", {},
      h("p", {}, `FigAssemble ${f.version} didn't install: ${f.error}.`),
      h("p", { class: "hint" }, s.tries < s.max_tries && s.mode === "auto" ? "FigAssemble tries again when you next quit it."
        : "FigAssemble won't try again by itself. If it keeps failing, report a problem with the log attached.")), [again, log]);
    again.addEventListener("click", () => { dlg.close(); this.install("update"); });
    log.addEventListener("click", () => rpc("update_log"));
  },

  updatedDialog(u) {
    const title = u.go_back ? `Back to FigAssemble ${u.version}` : `Updated to FigAssemble ${u.version}`;
    const body = u.go_back
      ? [h("p", {}, `FigAssemble went back to ${u.version}. Automatic updates skip ${u.from}; the version after it installs as usual.`)]
      : notesView(u.notes);
    const dlg = this.panels.dialog(title, h("div", { class: "whats-new" }, ...body));
    dlg.addEventListener("close", () => { rpc("update_seen").catch(() => {}); });
  },

  // Signing in to GitHub with a code (GitHub's device flow), while the repository is private
  async signInDialog() {
    let s;
    try {
      s = await rpc("github_signin_start");
    } catch (err) {
      this.panels.dialog("Sign in to GitHub", h("p", {}, `Signing in couldn't start: ${plain(err)}.`));
      return;
    }
    const state = h("p", { role: "status" }, "Waiting for GitHub…");
    const open = h("button", { type: "button", class: "btn primary" }, "Copy the code and open GitHub");
    open.addEventListener("click", () => {
      navigator.clipboard?.writeText(s.user_code).catch(() => {});
      rpc("open_url", s.uri).catch(() => {});
      state.textContent = "On GitHub, paste the code, then click Continue and Authorize. Waiting…";
    });
    const dlg = this.panels.dialog("Sign in to GitHub", h("div", {},
      h("p", {}, "FigAssemble's updates are private for now, so it signs in to GitHub, once, to download them. "
        + "It can only read FigAssemble's repository."),
      h("p", {}, "Your code:"),
      h("p", { class: "signin-code", "aria-label": `Your code: ${s.user_code.split("").join(" ")}` }, s.user_code),
      state), [open], "Cancel");
    let done = false;
    dlg.addEventListener("close", () => { if (!done) rpc("github_signin_cancel").catch(() => {}); });
    while (dlg.open) {
      await new Promise((r) => setTimeout(r, 1000));
      const st = await rpc("github_signin_status").catch(() => null);
      if (!st || st.state === "waiting") continue;
      done = true;
      if (st.state === "done") {
        state.textContent = `Signed in as ${st.login || "you"}. FigAssemble looks for updates now.`;
        announce(state.textContent);
        open.hidden = true;
        dlg.querySelector("button[value=close]").textContent = "Close";
        this.poll();
      } else {
        state.textContent = { expired: "The code ran out before it was entered. Close this and try again.",
          denied: "GitHub says the sign-in was cancelled." }[st.state] || `It didn't work: ${st.error}.`;
      }
      break;
    }
  },

  // A document saved by a newer FigAssemble than this one
  newerDocument(version) {
    const check = h("button", { type: "button", class: "btn" }, "Check for updates");
    const dlg = this.panels.dialog("Saved by a newer FigAssemble", h("div", {},
      h("p", {}, `This document was last saved by FigAssemble ${version}; you have ${this.app.info.version}.`),
      h("p", {}, "Things this version doesn't know about may not show, and saving over the document could lose them. "
        + "To be safe, update FigAssemble first, or save your changes as a copy (Save As).")), [check], "OK");
    check.addEventListener("click", () => { dlg.close(); this.checkNow(); });
  },
};
