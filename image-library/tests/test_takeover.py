"""更新後啟動：連接埠上還有舊的 Re'memor 時，請它讓位；同一份就直接打開，不重複啟動。"""

import unittest
from unittest import mock

from lumilib import server


class TakeoverTests(unittest.TestCase):
    def run_take(self, busy_seq, running, build="new"):
        busy = iter(busy_seq)
        with mock.patch.object(server, "_port_busy", side_effect=lambda port: next(busy)), \
                mock.patch.object(server, "_running", return_value=running), \
                mock.patch.object(server, "build_id", return_value=build), \
                mock.patch.object(server, "_stop_other") as stop, \
                mock.patch.object(server.time, "sleep"), \
                mock.patch("webbrowser.open") as browser, mock.patch("builtins.print"):
            ok = server._take_port(8766, "http://127.0.0.1:8766/", True)
        return ok, stop.called, browser.called

    def test_free_port_starts(self):
        self.assertEqual(self.run_take([False], None), (True, False, False))

    def test_same_build_just_opens_it(self):
        self.assertEqual(self.run_take([True], {"version": "0.19.2", "build": "new"}), (False, False, True))

    def test_older_build_is_asked_to_quit(self):
        self.assertEqual(self.run_take([True, False, False], {"version": "0.19.2", "build": "old"}), (True, True, False))
        self.assertEqual(self.run_take([True, False, False], {"version": "0.19.2"}), (True, True, False))  # 更舊的沒有建置代號

    def test_other_program_on_the_port_is_left_alone(self):
        self.assertEqual(self.run_take([True], None), (False, False, False))


if __name__ == "__main__":
    unittest.main()
