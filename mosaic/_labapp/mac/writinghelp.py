"""The Mac's own writing help in an app's windows (WebKit): off unless the app switches it on.

What it covers, as macOS 27 has it:
- the underlines macOS draws under words and phrases it would change (WebKit's Extended
  Proofreading, new in macOS 27, and grammar checking, which macOS 27 turns on by itself);
- spelling corrected as you type, the Mac's text replacements, and its smart quotes and dashes;
- inline predictions (grey words ahead of the cursor). These belong to the page: its
  writingsuggestions attribute, which the app's editor sets from the same switch.

The red spelling underlines and right-click Writing Tools stay as they are.

WebKit keeps the typing settings for the whole app. It reads them from the app's defaults when the
first window opens, and remembers changes made through Edit ▸ Spelling and Grammar or Substitutions
in them. start() puts the app's choice in the defaults' argument domain, which comes before
anything saved and lasts only for this run, so the choice holds at every start whatever was saved.
apply() changes them in a running app, through each window, as those menus would. Extended
Proofreading is a setting of each window (its WKPreferences): prepare() sets it for one.

    writinghelp.start(on)              # before the first window, on any thread
    writinghelp.prepare(webview, on)   # each window, once its WKWebView exists (main thread)
    writinghelp.apply(on)              # the switch changed (main thread): every window
    writinghelp.state(webview)         # what a window has now, for tests (main thread)
"""
from __future__ import annotations

# WebKit's names for its typing settings in an app's defaults, with NSSpellChecker's class method
# that says what System Settings ▸ Keyboard has for each (the Mac's own choice, used when the help is on)
SETTINGS = {
    "WebGrammarCheckingEnabled": "isAutomaticGrammarCheckingEnabled",
    "WebAutomaticSpellingCorrectionEnabled": "isAutomaticSpellingCorrectionEnabled",
    "WebAutomaticTextReplacementEnabled": "isAutomaticTextReplacementEnabled",
    "WebAutomaticQuoteSubstitutionEnabled": "isAutomaticQuoteSubstitutionEnabled",
    "WebAutomaticDashSubstitutionEnabled": "isAutomaticDashSubstitutionEnabled",
}
# Each setting's getter and setter on WKWebView (spelling correction has only a toggle and a menu
# item's tick: _live_get, _live_set)
_ACCESSORS = {
    "WebGrammarCheckingEnabled": ("isGrammarCheckingEnabled", "setGrammarCheckingEnabled_"),
    "WebAutomaticSpellingCorrectionEnabled": (None, None),
    "WebAutomaticTextReplacementEnabled": ("isAutomaticTextReplacementEnabled", "setAutomaticTextReplacementEnabled_"),
    "WebAutomaticQuoteSubstitutionEnabled": ("isAutomaticQuoteSubstitutionEnabled", "setAutomaticQuoteSubstitutionEnabled_"),
    "WebAutomaticDashSubstitutionEnabled": ("isAutomaticDashSubstitutionEnabled", "setAutomaticDashSubstitutionEnabled_"),
}
PROOFREADING = "ExtendedProofreadingEnabled"   # (WebKit's feature: the underlines under words, macOS 27)

_state: dict = {}   # "on": the app's choice as last started or applied


def values(on: bool, system: dict | None = None) -> dict:
    """{WebKit default: bool} for the choice: all off, or (on) what System Settings has for each.
    system: {NSSpellChecker method: bool}; a method missing from it (an older macOS) counts as off."""
    system = system or {}
    return {key: bool(on and system.get(method, False)) for key, method in SETTINGS.items()}


def system_values() -> dict:
    """{NSSpellChecker method: bool}: what System Settings ▸ Keyboard has now."""
    import AppKit
    out = {}
    for method in SETTINGS.values():
        fn = getattr(AppKit.NSSpellChecker, method, None)
        if fn is not None:
            try:
                out[method] = bool(fn())
            except Exception:   # noqa: BLE001 (not on this macOS: off)
                pass
    return out


def _put_in_arguments(vals: dict) -> None:
    """The settings in the defaults' argument domain (this run only; before anything saved)."""
    import Foundation
    ud = Foundation.NSUserDefaults.standardUserDefaults()
    domain = dict(ud.volatileDomainForName_(Foundation.NSArgumentDomain) or {})
    domain.update(vals)
    ud.setVolatileDomain_forName_(domain, Foundation.NSArgumentDomain)


def start(on: bool) -> dict:
    """The app's choice, before its first window opens (WebKit reads it then). Returns the settings."""
    vals = values(on, system_values())
    _put_in_arguments(vals)
    _state["on"] = bool(on)
    return vals


def _feature(name: str):
    import WebKit
    for f in WebKit.WKPreferences._features() or []:
        if str(f.key()) == name:
            return f
    return None


def _spelling_item():
    import AppKit
    return AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", "toggleAutomaticSpellingCorrection:", "")


def _live_get(webview, key: str) -> bool | None:
    getter = _ACCESSORS[key][0]
    if key == "WebAutomaticSpellingCorrectionEnabled":   # (the tick Edit ▸ Spelling and Grammar would show)
        item = _spelling_item()
        webview.validateUserInterfaceItem_(item)
        return bool(item.state())
    fn = getattr(webview, getter, None)
    return bool(fn()) if fn is not None else None


def _live_set(webview, key: str, value: bool) -> None:
    if _live_get(webview, key) in (None, value):
        return
    setter = _ACCESSORS[key][1]
    if key == "WebAutomaticSpellingCorrectionEnabled":
        webview.toggleAutomaticSpellingCorrection_(None)
    else:
        getattr(webview, setter)(value)


def prepare(webview, on: bool | None = None) -> None:
    """One window's WKWebView (main thread): its Extended Proofreading, and the app's typing
    settings (shared by every window) if they differ from the choice."""
    on = _state.get("on", False) if on is None else bool(on)
    feature = _feature(PROOFREADING)
    if feature is not None:
        prefs = webview.configuration().preferences()   # (the window's own, live)
        if bool(prefs._isEnabledForFeature_(feature)) != on:
            prefs._setEnabled_forFeature_(on, feature)
    for key, value in values(on, system_values()).items():
        try:
            _live_set(webview, key, value)
        except Exception:   # noqa: BLE001 (that setting isn't on this macOS)
            pass


def _webviews() -> list:
    """Every window's WKWebView (pywebview's windows)."""
    try:
        from webview.platforms.cocoa import BrowserView
    except ImportError:
        return []
    return [i.webview for i in list(BrowserView.instances.values()) if getattr(i, "webview", None) is not None]


def apply(on: bool) -> dict:
    """The switch changed (main thread): the choice for the next start and for every window now."""
    vals = values(on, system_values())
    _put_in_arguments(vals)
    _state["on"] = bool(on)
    for webview in _webviews():
        prepare(webview, on)
    return vals


def state(webview) -> dict:
    """What a window has now (main thread): {"proofreading": bool, WebKit default: bool, ...}."""
    out = {}
    feature = _feature(PROOFREADING)
    if feature is not None:
        out["proofreading"] = bool(webview.configuration().preferences()._isEnabledForFeature_(feature))
    for key in SETTINGS:
        try:
            out[key] = _live_get(webview, key)
        except Exception:   # noqa: BLE001 (not on this macOS)
            out[key] = None
    return out
