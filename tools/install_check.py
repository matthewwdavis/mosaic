#!/usr/bin/env python3
"""mosaic as an installer leaves it, opened (the window open with the editor ready in it, as in GitHub's check on a Mac): labapp's installcheck. The pre-push hook runs it
(tools/githooks/pre-push; git config core.hooksPath tools/githooks), so a push whose package won't
start is stopped before GitHub's installer check would fail (27 Nov 2026). git push --no-verify skips it."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from mosaic._labapp import installcheck  # noqa: E402

sys.exit(installcheck.main("mosaic", ROOT, smoke={"MOSAIC_SMOKETEST": "launch", "MOSAIC_NO_UPDATES": "1"},
                           expect=['SMOKE launch: {"ready": true'], stdin=sys.stdin))
