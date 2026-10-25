"""HTTP JSON API smoke tests against a real ThreadingHTTPServer on port 0.

The server is bound to 127.0.0.1 with the temporary ENSEMBLE_HOME configured by
``_support``, so no user data or real ``~/.ensemble`` directory is touched.
``serve.main()[init]`` is mirrored explicitly (module-level CONFIG/SETTINGS/
RUNS_DIR are empty until main() runs), and all provider-CLI probing and run
construction are patched out: these tests must never execute a model CLI.
"""

import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import _support  # noqa: F401  (must be imported before ensemble: isolates HOME)
import ensemble as E
import serve as S


class HttpApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="ensemble-http-api-"))

        # Save module state so the rest of the suite is unaffected.
        cls._saved_config = S.CONFIG
        cls._saved_settings = S.SETTINGS
        cls._saved_runs_dir = S.RUNS_DIR
        cls._saved_health_cache = dict(S.HEALTH_CACHE)

        # Mirror serve.main(): config/settings are only loaded there. Ignore any
        # real user config so provider assertions are deterministic.
        with mock.patch.object(E, "CONFIG_PATHS", []):
            S.CONFIG = E.load_config()
        S.SETTINGS = E.provider_settings(S.CONFIG)
        S.RUNS_DIR = cls.tmp / "runs"
        S.RUNS_DIR.mkdir(parents=True, exist_ok=True)
        S.HEALTH_CACHE.update({"at": 0.0, "data": None})

        # health() would run `codex login status` if a CLI happens to be
        # installed; pin every binary lookup to "not installed".
        cls._which_patch = mock.patch.object(E, "which", return_value=None)
        cls._which_patch.start()
        cls.addClassCleanup(cls._which_patch.stop)

        # Belt and braces: no POST in this module may construct a real run.
        cls._run_patch = mock.patch.object(S, "Run")
        cls._run_patch.start()
        cls.addClassCleanup(cls._run_patch.stop)

        cls.server = S.ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, name="ensemble-test-http", daemon=True
        )
        cls.thread.start()
        host, port = cls.server.server_address[:2]
        cls.base_url = f"http://{host}:{port}"
        # Never route loopback requests through a developer's proxy settings.
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
            cls.thread.join(timeout=10)
            if cls.thread.is_alive():
                raise AssertionError("HTTP server thread did not stop")
        finally:
            S.CONFIG = cls._saved_config
            S.SETTINGS = cls._saved_settings
            S.RUNS_DIR = cls._saved_runs_dir
            S.HEALTH_CACHE.clear()
            S.HEALTH_CACHE.update(cls._saved_health_cache)
            shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- helpers ---------------------------------------------------------- #

    def _request(self, method, path, payload=None, raw_body=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if raw_body is not None:
            data = raw_body
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with self.opener.open(request, timeout=10) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def _json_request(self, method, path, payload=None, raw_body=None):
        status, headers, raw = self._request(method, path, payload, raw_body)
        self.assertIn("application/json", headers.get("Content-Type", ""))
        return status, json.loads(raw.decode("utf-8"))

    # -- GET endpoints ---------------------------------------------------- #

    def test_get_health_returns_200_json(self):
        status, body = self._json_request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertIs(body["ok"], True)
        self.assertEqual(body["version"], E.VERSION)

    def test_get_health_has_security_headers(self):
        _, headers, _ = self._request("GET", "/api/health")
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("default-src 'self'", headers.get("Content-Security-Policy", ""))

    def test_get_providers_returns_200_json(self):
        status, body = self._json_request("GET", "/api/providers")
        self.assertEqual(status, 200)
        self.assertIn("providers", body)
        self.assertIsInstance(body["providers"], list)
        expected_keys = E.all_keys(S.SETTINGS)
        self.assertEqual([row["key"] for row in body["providers"]], expected_keys)
        self.assertEqual(len(expected_keys), 4)
        for row in body["providers"]:
            for field in ("key", "label", "accent", "model", "ready", "note"):
                self.assertIn(field, row)
        defaults = body["defaults"]
        self.assertIn(defaults["judge_provider"], expected_keys)
        self.assertEqual(defaults["context"], "temp")

    def test_get_runs_returns_200_json_list(self):
        status, body = self._json_request("GET", "/api/runs")
        self.assertEqual(status, 200)
        self.assertIn("runs", body)
        self.assertIsInstance(body["runs"], list)
        for row in body["runs"]:
            self.assertIn("id", row)
            self.assertIn("prompt", row)
            self.assertIn("status", row)

    def test_get_runs_includes_history_from_runs_dir(self):
        run_id = "2026-10-25_200000_seeded"
        run_dir = S.RUNS_DIR / run_id
        run_dir.mkdir(parents=True)
        try:
            meta = {
                "prompt": "hello from history",
                "created_at": "2026-10-25 20:00:00",
                "wall_seconds": 3.0,
                "results": [{"key": "kimi", "label": "Kimi", "status": "ok"}],
            }
            (run_dir / "meta.json").write_text(json.dumps(meta))
            (run_dir / "results.json").write_text("[]")

            status, body = self._json_request("GET", "/api/runs")
            self.assertEqual(status, 200)
            matching = [row for row in body["runs"] if row["id"] == run_id]
            self.assertEqual(len(matching), 1)
            row = matching[0]
            self.assertEqual(row["prompt"], "hello from history")
            self.assertEqual(row["status"], "done")
            self.assertEqual(row["total"], 1)
            self.assertEqual(row["answered"], 1)

            # And the per-run detail endpoint reads the same on-disk snapshot.
            status, detail = self._json_request("GET", f"/api/runs/{run_id}")
            self.assertEqual(status, 200)
            self.assertEqual(detail["id"], run_id)
            self.assertEqual(detail["prompt"], "hello from history")
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_get_unknown_run_returns_404_json(self):
        status, body = self._json_request("GET", "/api/runs/does-not-exist")
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    # -- POST /api/runs validation --------------------------------------- #

    def test_create_run_rejects_empty_prompt(self):
        status, body = self._json_request("POST", "/api/runs", {"prompt": "   "})
        self.assertEqual(status, 400)
        self.assertIn("prompt", body["error"].lower())

    def test_create_run_rejects_missing_prompt(self):
        status, body = self._json_request("POST", "/api/runs", {})
        self.assertEqual(status, 400)
        self.assertIn("prompt", body["error"].lower())

    def test_create_run_rejects_non_list_providers(self):
        status, body = self._json_request(
            "POST", "/api/runs", {"prompt": "hello", "providers": "kimi"}
        )
        self.assertEqual(status, 400)
        self.assertIn("list", body["error"].lower())

    def test_create_run_rejects_providers_dict(self):
        status, body = self._json_request(
            "POST", "/api/runs", {"prompt": "hello", "providers": {"kimi": True}}
        )
        self.assertEqual(status, 400)
        self.assertIn("list", body["error"].lower())

    def test_create_run_rejects_unknown_providers(self):
        status, body = self._json_request(
            "POST", "/api/runs", {"prompt": "hello", "providers": ["no-such-model"]}
        )
        self.assertEqual(status, 400)
        self.assertIn("at least one model", body["error"].lower())

    def test_create_run_rejects_invalid_context(self):
        status, body = self._json_request(
            "POST", "/api/runs", {"prompt": "hello", "providers": ["kimi"], "context": "bogus"}
        )
        self.assertEqual(status, 400)
        self.assertIn("context", body["error"].lower())

    def test_create_run_rejects_invalid_json(self):
        status, body = self._json_request(
            "POST", "/api/runs", raw_body=b"{not json"
        )
        self.assertEqual(status, 400)
        self.assertIn("invalid json", body["error"].lower())

    # -- isolation -------------------------------------------------------- #

    def test_server_uses_temporary_home_and_runs_dir(self):
        self.assertEqual(E.HOME, _support.TEST_HOME)
        self.assertEqual(S.RUNS_DIR, self.tmp / "runs")
        self.assertNotEqual(S.RUNS_DIR, Path.home() / ".ensemble" / "runs")
        self.assertFalse(str(S.RUNS_DIR).startswith(str(Path.home() / ".ensemble")))

    def test_server_is_listening_on_an_ephemeral_port(self):
        port = self.server.server_address[1]
        self.assertGreater(port, 0)
        self.assertEqual(self.base_url, f"http://127.0.0.1:{port}")


if __name__ == "__main__":
    unittest.main()
