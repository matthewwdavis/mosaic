"""Settings: saved and read from several requests at once without one undoing another."""
import threading

from figassemble.app.api import Api


def test_settings_hold_with_requests_at_once():
    # The editor saves settings on several threads at once (a remembered tab while a toggle
    # saves); a read in the middle of a write used to see an empty file and hand back the
    # defaults, undoing the toggle
    api = Api()
    wrong = []

    def saver(n):
        for i in range(30):
            got = api.prefs_set({f"test_setting_{n}": i})
            if got.get(f"test_setting_{n}") != i:
                wrong.append((n, i, got.get(f"test_setting_{n}")))

    def reader():
        for _ in range(150):
            if api.prefs_get().get("units") is None:
                wrong.append("a read came back without the defaults")

    threads = [threading.Thread(target=saver, args=(n,)) for n in range(4)] + [threading.Thread(target=reader) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert wrong == []
    final = api.prefs_get()
    assert all(final[f"test_setting_{n}"] == 29 for n in range(4))
