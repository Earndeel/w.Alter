"""NordVPN exit of a managed session (2026-11-11): network=vpn + country -> `walter-wg-exit use nordvpn-<cc>`;
anything else, or an exit that cannot be opened, refuses the request (no fallback to another route)."""
from __future__ import annotations

import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

import universal_router as ur


def _session(network="vpn", country="jp"):
    return SimpleNamespace(network=network, country=country, id="s1")


def _run(code=0, out="", err=""):
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=out, stderr=err)


class SessionExit(unittest.TestCase):
    def test_vpn_session_gets_the_exit_of_its_country(self):
        with mock.patch("subprocess.run", return_value=_run(out="http://127.0.0.1:21108\n")) as run:
            self.assertEqual(ur._session_exit(_session()), "http://127.0.0.1:21108")
        self.assertEqual(run.call_args.args[0], ["walter-wg-exit", "use", "nordvpn-jp"])

    def test_an_exit_that_cannot_open_refuses_the_request(self):
        with mock.patch("subprocess.run", return_value=_run(code=1, err="nordvpn: access token unavailable")):
            with self.assertRaises(ur.SessionError) as e:
                ur._session_exit(_session())
        self.assertIn("no fallback", str(e.exception))

    def test_an_unexpected_answer_is_not_used_as_a_proxy(self):
        with mock.patch("subprocess.run", return_value=_run(out="socks5://0.0.0.0:9\n")):
            with self.assertRaises(ur.SessionError):
                ur._session_exit(_session())

    def test_vpn_without_a_valid_country_is_refused_not_sent_local(self):
        for c in (None, "", "japan", "j1"):
            with mock.patch("subprocess.run") as run, self.assertRaises(ur.SessionError):
                ur._session_exit(_session(country=c))
            run.assert_not_called()

    def test_other_network_modes_have_no_exit(self):
        with mock.patch("subprocess.run") as run, self.assertRaises(ur.SessionError):
            ur._session_exit(_session(network="proxy"))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
