"""Snapshot an HTML file with WKWebView (WebKit, as mosaic's app window draws)."""
import sys
import objc
from AppKit import NSApplication, NSBitmapImageRep, NSPNGFileType, NSMakeRect
from Foundation import NSURL, NSObject, NSRunLoop, NSDate
from WebKit import WKWebView, WKWebViewConfiguration, WKSnapshotConfiguration

html, out, w, h = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
app = NSApplication.sharedApplication()
state = {"loaded": False, "done": False}

class Nav(NSObject):
    def webView_didFinishNavigation_(self, wv, nav):
        state["loaded"] = True

wv = WKWebView.alloc().initWithFrame_configuration_(NSMakeRect(0, 0, w, h), WKWebViewConfiguration.alloc().init())
nav = Nav.alloc().init()
wv.setNavigationDelegate_(nav)
url = NSURL.fileURLWithPath_(html)
wv.loadFileURL_allowingReadAccessToURL_(url, url.URLByDeletingLastPathComponent())
rl = NSRunLoop.currentRunLoop()
while not state["loaded"]:
    rl.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))
for _ in range(20):
    rl.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))

def done(image, err):
    if image is not None:
        tiff = image.TIFFRepresentation()
        rep = NSBitmapImageRep.imageRepWithData_(tiff)
        rep.representationUsingType_properties_(NSPNGFileType, None).writeToFile_atomically_(out, True)
    else:
        print("error", err)
    state["done"] = True

cfg = WKSnapshotConfiguration.alloc().init()
wv.takeSnapshotWithConfiguration_completionHandler_(cfg, done)
while not state["done"]:
    rl.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))
