"""Interface themes: mosaic's own, a dozen RStudio favourites, and a few originals.

A theme colours the interface only. The page stays white paper in every theme, so a figure's
colours always look as they'll print.

Each theme sets the interface's colour variables (see the top of ui/css/app.css). The server
writes the chosen theme into the page as it loads (no flash of another theme), and the Settings
gallery swaps it live. "Match the system" uses a day theme and a night theme, switched by the
system's light or dark mode. Every theme keeps text readable: tests/test_themes.py checks each
against the WCAG contrast ratios. The RStudio favourites take their colours from the editor
themes of the same names (credited in THIRD_PARTY_NOTICES.md).
"""
from __future__ import annotations

# Variable name -> CSS custom property
VARS = {"bg": "--bg", "panel": "--panel", "panel2": "--panel-2", "text": "--text", "muted": "--muted",
        "line": "--line", "accent": "--accent", "accent_text": "--accent-text", "focus": "--focus", "sel": "--sel",
        "guide": "--guide", "warn": "--warn", "ok": "--ok", "danger": "--danger", "stage": "--stage",
        "hover": "--hover", "pressed": "--pressed", "ruler_bg": "--ruler-bg", "ruler_page": "--ruler-page",
        "ruler_tick": "--ruler-tick", "guide_line": "--guide-line", "page_edge": "--page-edge"}


def _t(id, name, group, dark, **c):
    return {"id": id, "name": name, "group": group, "dark": dark, "colors": c}


THEMES = [
    # mosaic's own
    _t("light", "Light", "mosaic", False,
       bg="#f1f1ee", panel="#ffffff", panel2="#f7f7f5", text="#1b1b19", muted="#55554f", line="#d6d6d0",
       accent="#0b5fcc", accent_text="#ffffff", focus="#0b5fcc", sel="#0a63d6", guide="#d1007a", warn="#8a4b00",
       ok="#1f6d2c", danger="#b3261e", stage="#dcdcd7", hover="#ececea", pressed="#dbe7fa", ruler_bg="#ecece8",
       ruler_page="#ffffff", ruler_tick="#888881", guide_line="#0086b4", page_edge="#e53500"),
    _t("dark", "Dark", "mosaic", True,
       bg="#1d1e20", panel="#26272a", panel2="#2d2e31", text="#ececea", muted="#b4b4ae", line="#43444a",
       accent="#5b9dff", accent_text="#0b0c0e", focus="#8fbaff", sel="#3d86e8", guide="#ef37a6", warn="#ffbf66",
       ok="#7fd18b", danger="#ff8a80", stage="#3a3b3e", hover="#34353a", pressed="#23344f", ruler_bg="#202124",
       ruler_page="#34353a", ruler_tick="#7c7d83", guide_line="#1a92c2", page_edge="#ff4b15"),
    _t("contrast", "High contrast", "mosaic", True,
       bg="#000000", panel="#000000", panel2="#000000", text="#ffffff", muted="#ffffff", line="#ffffff",
       accent="#ffd400", accent_text="#000000", focus="#ffd400", sel="#d4007f", guide="#d4007f", warn="#ffd400",
       ok="#7dff8a", danger="#ff7070", stage="#000000", hover="#333333", pressed="#4a4100", ruler_bg="#000000",
       ruler_page="#2a2a2a", ruler_tick="#ffffff", guide_line="#0a84c9", page_edge="#dd3400"),

    # RStudio favourites, light
    _t("textmate", "Textmate", "RStudio", False,
       bg="#eef0f2", panel="#ffffff", panel2="#f5f6f7", text="#000000", muted="#4c5a66", line="#d3d7db",
       accent="#0000cd", accent_text="#ffffff", focus="#0000cd", sel="#0a63d6", guide="#d1007a", warn="#8a4b00",
       ok="#036a07", danger="#b3261e", stage="#e2e5e8", hover="#eceef0", pressed="#dde3fb", ruler_bg="#eceef0",
       ruler_page="#ffffff", ruler_tick="#838993", guide_line="#0089b8", page_edge="#f03800"),
    _t("tomorrow", "Tomorrow", "RStudio", False,
       bg="#efefef", panel="#ffffff", panel2="#f6f6f6", text="#4d4d4c", muted="#686a66", line="#d6d6d6",
       accent="#4271ae", accent_text="#ffffff", focus="#8959a8", sel="#4271ae", guide="#c82829", warn="#9a5a00",
       ok="#5a7000", danger="#c82829", stage="#e0e0e0", hover="#efefef", pressed="#dfe7f2", ruler_bg="#ececec",
       ruler_page="#ffffff", ruler_tick="#868884", guide_line="#388b91", page_edge="#ea3700"),
    _t("solarized-light", "Solarized Light", "RStudio", False,
       bg="#eee8d5", panel="#fdf6e3", panel2="#f6f0dc", text="#073642", muted="#4f646b", line="#ddd6c1",
       accent="#1f6fae", accent_text="#fdf6e3", focus="#6c71c4", sel="#2482c5", guide="#d33682", warn="#7e5f00",
       ok="#5c6a00", danger="#c42b28", stage="#e3dcc7", hover="#f2ebd6", pressed="#e4e4d9", ruler_bg="#f2ebd6",
       ruler_page="#fdf6e3", ruler_tick="#798a8a", guide_line="#248b83", page_edge="#e53600"),
    _t("dawn", "Dawn", "RStudio", False,
       bg="#ebe9eb", panel="#f9f9f9", panel2="#f2f1f2", text="#080808", muted="#5a525f", line="#d9d6d9",
       accent="#794938", accent_text="#ffffff", focus="#691c97", sel="#794938", guide="#a71d5d", warn="#8a4b00",
       ok="#0b6125", danger="#811f24", stage="#dfdddf", hover="#efedef", pressed="#eddfd9", ruler_bg="#efedef",
       ruler_page="#f9f9f9", ruler_tick="#8e8694", guide_line="#691c97", page_edge="#e73600"),
    _t("xcode", "Xcode", "RStudio", False,
       bg="#ececec", panel="#ffffff", panel2="#f5f5f5", text="#000000", muted="#5c5c5c", line="#d5d5d5",
       accent="#c800a4", accent_text="#ffffff", focus="#3a00dc", sel="#3a00dc", guide="#c800a4", warn="#8a4b00",
       ok="#007a00", danger="#d00002", stage="#dedede", hover="#eeeeee", pressed="#f3dcef", ruler_bg="#eeeeee",
       ruler_page="#ffffff", ruler_tick="#898989", guide_line="#3a00dc", page_edge="#e73600"),

    # RStudio favourites, dark
    _t("tomorrow-night", "Tomorrow Night", "RStudio", True,
       bg="#17181a", panel="#1d1f21", panel2="#282a2e", text="#c5c8c6", muted="#a0a3a1", line="#373b41",
       accent="#81a2be", accent_text="#1d1f21", focus="#b294bb", sel="#628ab3", guide="#ce6868", warn="#f0c674",
       ok="#b5bd68", danger="#d97a7a", stage="#3a3c3d", hover="#282a2e", pressed="#2f3b48", ruler_bg="#1a1b1d",
       ruler_page="#282a2e", ruler_tick="#808382", guide_line="#5f9e98", page_edge="#ff4c16"),
    _t("solarized-dark", "Solarized Dark", "RStudio", True,
       bg="#00212b", panel="#002b36", panel2="#073642", text="#d5d9d4", muted="#9fadad", line="#164552",
       accent="#268bd2", accent_text="#001b23", focus="#6c71c4", sel="#368ccd", guide="#e74a93", warn="#c9a227",
       ok="#a3b200", danger="#ec6a67", stage="#293f46", hover="#073642", pressed="#0b4256", ruler_bg="#00252f",
       ruler_page="#073642", ruler_tick="#658087", guide_line="#2a9d94", page_edge="#ff4c16"),
    _t("monokai", "Monokai", "RStudio", True,
       bg="#1e1f1c", panel="#272822", panel2="#3e3d32", text="#f8f8f2", muted="#b4ae94", line="#49483e",
       accent="#f92672", accent_text="#000000", focus="#66d9ef", sel="#f0407e", guide="#f0407e", warn="#e6db74",
       ok="#a6e22e", danger="#ff6b9d", stage="#3a3c37", hover="#3e3d32", pressed="#4a3340", ruler_bg="#22231e",
       ruler_page="#3e3d32", ruler_tick="#8f8a73", guide_line="#3d9fb3", page_edge="#ff4b15"),
    _t("dracula", "Dracula", "RStudio", True,
       bg="#21222c", panel="#282a36", panel2="#343746", text="#f8f8f2", muted="#b4bad8", line="#44475a",
       accent="#bd93f9", accent_text="#21222c", focus="#ff79c6", sel="#9d6ce8", guide="#e05aa8", warn="#ffb86c",
       ok="#50fa7b", danger="#ff6e6e", stage="#393b42", hover="#343746", pressed="#44406a", ruler_bg="#242530",
       ruler_page="#343746", ruler_tick="#7d82a3", guide_line="#33a2b5", page_edge="#ff4b15"),
    _t("cobalt", "Cobalt", "RStudio", True,
       bg="#001a33", panel="#002240", panel2="#00305a", text="#ffffff", muted="#a8c5e0", line="#0b3e6b",
       accent="#ff9d00", accent_text="#002240", focus="#ffdd00", sel="#dc7d00", guide="#ff5885", warn="#ffdd00",
       ok="#3ad900", danger="#ff7d9d", stage="#2f3d4a", hover="#00305a", pressed="#003f75", ruler_bg="#001e3a",
       ruler_page="#00305a", ruler_tick="#4a7aa6", guide_line="#1f8fe0", page_edge="#ff4b15"),
    _t("material", "Material", "RStudio", True,
       bg="#1e272c", panel="#263238", panel2="#2e3c43", text="#eeffff", muted="#b0bec5", line="#37474f",
       accent="#80cbc4", accent_text="#1e272c", focus="#c792ea", sel="#3f9a92", guide="#e3537c", warn="#ffcb6b",
       ok="#c3e88d", danger="#ff6f87", stage="#343d41", hover="#2e3c43", pressed="#30474d", ruler_bg="#222c31",
       ruler_page="#2e3c43", ruler_tick="#6c8591", guide_line="#4f8fd6", page_edge="#ff4c16"),
    _t("twilight", "Twilight", "RStudio", True,
       bg="#121212", panel="#1a1a1a", panel2="#242424", text="#f8f8f8", muted="#b0aab1", line="#363636",
       accent="#cda869", accent_text="#141414", focus="#7587a6", sel="#a8814a", guide="#cf6a4c", warn="#cda869",
       ok="#a2b06e", danger="#e0805f", stage="#3c3c3c", hover="#242424", pressed="#3a3226", ruler_bg="#161616",
       ruler_page="#242424", ruler_tick="#7a747b", guide_line="#7688a7", page_edge="#ff4c16"),

    # Originals: your crops
    _t("pistachio", "Pistachio", "Crops", False,
       bg="#e8eed8", panel="#fbfaf2", panel2="#f2f5e6", text="#25331b", muted="#4f5f3c", line="#cfdbb6",
       accent="#4f7a2e", accent_text="#ffffff", focus="#8b4a6b", sel="#4f7a2e", guide="#8b4a6b", warn="#855700",
       ok="#33702a", danger="#a3343b", stage="#dce6c8", hover="#eef3e2", pressed="#dcebc9", ruler_bg="#eef3e2",
       ruler_page="#fbfaf2", ruler_tick="#83906c", guide_line="#3f8e79", page_edge="#ec3700"),
    _t("walnut", "Walnut", "Crops", True,
       bg="#2a1d14", panel="#3a2a1e", panel2="#46332a", text="#f3e6d3", muted="#cdb89e", line="#5a4231",
       accent="#d9a066", accent_text="#2a1d14", focus="#e8c39e", sel="#b5793f", guide="#d85e72", warn="#e8b04b",
       ok="#b1cc85", danger="#f08a72", stage="#453930", hover="#46332a", pressed="#5a4231", ruler_bg="#32241a",
       ruler_page="#46332a", ruler_tick="#9a8068", guide_line="#4b9e8c", page_edge="#ff4b15"),
    _t("alfalfa", "Alfalfa", "Crops", False,
       bg="#ebe5f4", panel="#fbf9fd", panel2="#f3eff9", text="#2b2140", muted="#584c70", line="#d8cee8",
       accent="#6b3fa0", accent_text="#ffffff", focus="#3f7f3a", sel="#6b3fa0", guide="#3f7f3a", warn="#855700",
       ok="#3a7535", danger="#a3343b", stage="#e1d9ee", hover="#f0ebf8", pressed="#e4d8f5", ruler_bg="#f0ebf8",
       ruler_page="#fbf9fd", ruler_tick="#9083a5", guide_line="#3f7f3a", page_edge="#e53600"),

    # Originals: science
    _t("lab-notebook", "Lab notebook", "Science", False,
       bg="#efeadb", panel="#fdfcf6", panel2="#f7f4ea", text="#14235a", muted="#435189", line="#c9d3ea",
       accent="#1b3fa0", accent_text="#ffffff", focus="#c0392b", sel="#1b3fa0", guide="#c0392b", warn="#855700",
       ok="#2e6b30", danger="#b03224", stage="#e4dece", hover="#f3f0e5", pressed="#dfe6f7", ruler_bg="#f3f0e5",
       ruler_page="#fdfcf6", ruler_tick="#7b89b4", guide_line="#c0392b", page_edge="#008b78"),
    _t("blueprint", "Blueprint", "Science", True,
       bg="#12335f", panel="#163c6f", panel2="#1b477f", text="#ffffff", muted="#d5e4f7", line="#5c8fd0",
       accent="#ffffff", accent_text="#1d4f91", focus="#ffe066", sel="#e8590c", guide="#e8590c", warn="#ffe066",
       ok="#c3f7d3", danger="#ffc9c9", stage="#313c4a", hover="#22528f", pressed="#2a5c9c", ruler_bg="#14386a",
       ruler_page="#1b477f", ruler_tick="#9cc0ea", guide_line="#eb497d", page_edge="#009baa"),
    _t("chalkboard", "Chalkboard", "Science", True,
       bg="#26302b", panel="#2f3b35", panel2="#36443d", text="#f2f2ea", muted="#c3cbc0", line="#4a5a51",
       accent="#f7e27c", accent_text="#26302b", focus="#9fd6f5", sel="#b39023", guide="#de7395", warn="#f7e27c",
       ok="#b5e3a1", danger="#f4a3a3", stage="#343e38", hover="#36443d", pressed="#4a5a51", ruler_bg="#2a352f",
       ruler_page="#36443d", ruler_tick="#8a9a90", guide_line="#449dd0", page_edge="#ff4c16"),
    _t("terminal", "Terminal", "Science", True,
       bg="#000000", panel="#0b0f0b", panel2="#101810", text="#33ff66", muted="#2fd65a", line="#145c2a",
       accent="#33ff66", accent_text="#000000", focus="#ffcc00", sel="#22a03a", guide="#f33798", warn="#ffcc00",
       ok="#33ff66", danger="#ff5c5c", stage="#3c3c3c", hover="#0d1f12", pressed="#0f3d1c", ruler_bg="#050805",
       ruler_page="#101810", ruler_tick="#1f9e45", guide_line="#1f90c0", page_edge="#ff4c16"),
]
BY_ID = {t["id"]: t for t in THEMES}
GROUPS = ["mosaic", "RStudio", "Crops", "Science"]


def _block(theme: dict) -> str:
    c = theme["colors"]
    body = "; ".join(f"{VARS[k]}: {v}" for k, v in c.items())
    return f"{body}; color-scheme: {'dark' if theme['dark'] else 'light'}"


def css(theme: str = "system", day: str = "light", night: str = "dark") -> str:
    """The interface's colours for a theme id, or "system" (day and night themes by the system's mode)."""
    if theme == "system":
        d, n = BY_ID.get(day, BY_ID["light"]), BY_ID.get(night, BY_ID["dark"])
        out = f":root {{ {_block(d)} }}\n@media (prefers-color-scheme: dark) {{ :root {{ {_block(n)} }} }}"
    else:
        out = f":root {{ {_block(BY_ID.get(theme, BY_ID['light']))} }}"
    # Asked for more contrast in the system settings: hints as strong as the text
    return out + "\n@media (prefers-contrast: more) { :root { --muted: var(--text); } }"


def catalog() -> list[dict]:
    """The themes for the Settings gallery: id, name, group, dark, colours."""
    return [{"id": t["id"], "name": t["name"], "group": t["group"], "dark": t["dark"], "colors": t["colors"]} for t in THEMES]


# Contrast (WCAG 2) ---------------------------------------------------------------------------

def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (foreground, background, minimum ratio): text 4.5:1; marks on the page and the stage 3:1
RULES = [(f, b, 4.5) for f in ("text", "muted") for b in ("panel", "panel2", "hover")] + [
    ("text", "pressed", 4.5), ("text", "bg", 4.5), ("muted", "ruler_bg", 4.5), ("muted", "ruler_page", 4.5),
    ("accent_text", "accent", 4.5), ("warn", "panel", 4.5), ("ok", "panel", 4.5), ("danger", "panel", 4.5),
    ("focus", "panel", 3), ("sel", "panel", 3), ("ruler_tick", "ruler_bg", 3),
    ("sel", "#ffffff", 3), ("sel", "stage", 3), ("guide", "#ffffff", 3), ("guide", "stage", 3),
    ("guide_line", "#ffffff", 3), ("guide_line", "stage", 3), ("page_edge", "#ffffff", 3), ("page_edge", "stage", 3)]


def check(theme: dict) -> list[str]:
    """The contrast rules a theme breaks, as readable lines (empty if none)."""
    c = theme["colors"]
    bad = []
    for fg, bg, need in RULES:
        a, b = c[fg], c.get(bg, bg)
        r = contrast(a, b)
        if r < need:
            bad.append(f"{theme['id']}: {fg} {a} on {bg} {b} is {r:.2f}:1, needs {need}:1")
    return bad
