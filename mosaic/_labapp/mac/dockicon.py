"""The app's Dock icon following the system's appearance while the app runs: its light icon in
Light mode, its dark one in Dark mode, changed as the system changes.

    dockicon.follow(light_png_bytes, dark_png_bytes)      # once the app has started; any thread

This is the icon of the running app (the Dock, the app switcher). The icon the Finder and the Dock
show for an app that isn't running is the one in its bundle: on macOS 26 and later a bundle made
with an Assets.car (packaging.AppSpec.icon_assets) follows the system by itself, and this then
leaves the icon to macOS.
"""
from __future__ import annotations

_state: dict = {}


def is_dark() -> bool:
    """Whether the system is in Dark mode now (on the main thread)."""
    import AppKit
    app = AppKit.NSApp or AppKit.NSApplication.sharedApplication()
    names = [AppKit.NSAppearanceNameAqua, AppKit.NSAppearanceNameDarkAqua]
    return str(app.effectiveAppearance().bestMatchFromAppearancesWithNames_(names)) == str(AppKit.NSAppearanceNameDarkAqua)


def _image(data: bytes):
    import AppKit
    import Foundation
    return AppKit.NSImage.alloc().initWithData_(Foundation.NSData.dataWithBytes_length_(data, len(data)))


def apply() -> str | None:
    """Set the Dock icon for the appearance there is now (on the main thread); "light" or "dark"."""
    import AppKit
    if "light" not in _state:
        return None
    which = "dark" if is_dark() else "light"
    if _state.get("shown") != which:
        image = _image(_state[which])
        if image is not None:
            AppKit.NSApp.setApplicationIconImage_(image)
            _state["shown"] = which
    return which


def system_follows() -> bool:
    """Whether macOS draws this app's icon in the system's appearance by itself: an app bundle that
    names an icon in its Assets.car (packaging.mac_app's CFBundleIconName), on macOS 26 or later."""
    import platform

    import Foundation
    try:
        major = int(platform.mac_ver()[0].split(".")[0])
    except (ValueError, IndexError):
        return False
    info = Foundation.NSBundle.mainBundle().infoDictionary() or {}
    return major >= 26 and bool(info.get("CFBundleIconName"))


def follow(light: bytes, dark: bytes) -> None:
    """Show the icon for the system's appearance, and change it when the system's changes; left
    to macOS where it does that itself (system_follows), so its tinted and clear icons work too."""
    import Foundation
    from PyObjCTools import AppHelper
    if system_follows():
        return
    _state.update(light=light, dark=dark)
    _state.pop("shown", None)

    def start():
        if "observer" not in _state:
            class LabappAppearanceWatcher(Foundation.NSObject):
                def themeChanged_(self, note):
                    # (the app's own appearance follows a moment after the system says it changed)
                    AppHelper.callLater(0.3, apply)
            _state["observer"] = LabappAppearanceWatcher.alloc().init()
            Foundation.NSDistributedNotificationCenter.defaultCenter().addObserver_selector_name_object_(
                _state["observer"], b"themeChanged:", "AppleInterfaceThemeChangedNotification", None)
        apply()
    AppHelper.callAfter(start)
