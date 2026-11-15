"""Closing a window with unsaved changes asks first, naming its figure: Save, Don't Save or
Cancel; a figure with AutoSave on is saved without asking. On a Mac the question is a sheet on
the window (which also asks about each unsaved figure in turn when mosaic quits); on Windows a
message box, Yes saving; on Linux pywebview's own question (Close without saving or Cancel), the
recovery copy the editor keeps as it goes being what's offered back.

The asking and what the answers do are the shared library's (_labapp/closing.py, `shared` here);
this says what is mosaic's: its name, "figure", and the editor's own save and keep-a-copy.
"""
from __future__ import annotations

from .._labapp import closing as shared
from .._labapp.closing import answer, ask, close, on_closing, question   # noqa: F401

shared.configure(name="mosaic", thing="figure", save_js="window.FA.app.saveToClose()", keep_js="window.FA.app.keepCopy()")
