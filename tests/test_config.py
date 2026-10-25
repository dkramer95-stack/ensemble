"""Config layering: deep_merge(), load_config() and provider_settings()."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

import _support  # noqa: F401  (must be imported before ensemble: isolates HOME)
import ensemble as E


class DeepMergeTest(unittest.TestCase):
    def test_overlays_scalar_values(self):
        merged = E.deep_merge({"a": 1, "b": 2}, {"b": 3, "c": 4})
        self.assertEqual(merged, {"a": 1, "b": 3, "c": 4})

    def test_merges_nested_dicts_recursively(self):
        base = {"providers": {"kimi": {"model": "a", "timeout": 300}}}
        extra = {"providers": {"kimi": {"model": "b"}}}
        merged = E.deep_merge(base, extra)
        self.assertEqual(
            merged, {"providers": {"kimi": {"model": "b", "timeout": 300}}}
        )

    def test_extra_dict_replaces_non_dict_base_value(self):
        merged = E.deep_merge({"providers": None}, {"providers": {"kimi": {"model": "x"}}})
        self.assertEqual(merged["providers"], {"kimi": {"model": "x"}})

    def test_extra_scalar_replaces_dict(self):
        merged = E.deep_merge({"providers": {"kimi": {}}}, {"providers": None})
        self.assertIsNone(merged["providers"])

    def test_does_not_mutate_inputs(self):
        base = {"providers": {"kimi": {"model": "a"}}}
        extra = {"providers": {"kimi": {"model": "b", "timeout": 5}}, "defaults": {"context": "temp"}}
        merged = E.deep_merge(base, extra)
        self.assertEqual(base, {"providers": {"kimi": {"model": "a"}}})
        self.assertEqual(
            extra,
            {"providers": {"kimi": {"model": "b", "timeout": 5}}, "defaults": {"context": "temp"}},
        )
        merged["providers"]["kimi"]["model"] = "mutated"
        self.assertEqual(base["providers"]["kimi"]["model"], "a")

    def test_none_extra_returns_shallow_copy(self):
        base = {"a": {"b": 1}}
        merged = E.deep_merge(base, None)
        self.assertEqual(merged, base)
        self.assertIsNot(merged, base)


class ProviderSettingsTest(unittest.TestCase):
    def test_defaults_match_builtin_providers(self):
        settings = E.provider_settings({})
        self.assertEqual(E.all_keys(settings), ["kimi", "gemini", "deepseek", "codex"])
        for key, base in E.PROVIDERS.items():
            self.assertEqual(settings[key]["label"], base["label"])
            self.assertEqual(settings[key]["parse"], base["parse"])
            self.assertEqual(settings[key]["accent"], base["accent"])
            self.assertEqual(settings[key]["timeout"], base["timeout"])
            self.assertTrue(settings[key]["enabled"])

    def test_provider_override_wins(self):
        settings = E.provider_settings(
            {"providers": {"kimi": {"model": "kimi-test", "timeout": 42, "enabled": False}}}
        )
        self.assertEqual(settings["kimi"]["model"], "kimi-test")
        self.assertEqual(settings["kimi"]["timeout"], 42)
        self.assertFalse(settings["kimi"]["enabled"])
        # Untouched providers keep their defaults.
        self.assertEqual(settings["gemini"]["parse"], "text")
        self.assertTrue(settings["gemini"]["enabled"])

    def test_defaults_models_override_provider_specific_model(self):
        # Precedence documented by the implementation: defaults.models is applied
        # after the per-provider merge, so it wins.
        config = {
            "defaults": {"models": {"kimi": "from-defaults"}},
            "providers": {"kimi": {"model": "from-provider"}},
        }
        settings = E.provider_settings(config)
        self.assertEqual(settings["kimi"]["model"], "from-defaults")

    def test_extra_provider_gets_generic_defaults(self):
        settings = E.provider_settings(
            {"providers": {"local-llm": {"bin": "local-llm", "parse": "text"}}}
        )
        self.assertIn("local-llm", settings)
        self.assertEqual(settings["local-llm"]["label"], "Local Llm")
        self.assertEqual(settings["local-llm"]["accent"], "#6B7280")
        self.assertEqual(settings["local-llm"]["bin"], "local-llm")
        self.assertIsNone(settings["local-llm"]["model"])
        self.assertEqual(settings["local-llm"]["timeout"], 300)
        self.assertEqual(settings["local-llm"]["enabled"], True)
        keys = E.all_keys(settings)
        self.assertEqual(len(keys), 5)
        self.assertEqual(keys[-1], "local-llm")

    def test_extra_provider_override_can_be_partial(self):
        settings = E.provider_settings({"providers": {"ollama": {"timeout": 60}}})
        self.assertEqual(settings["ollama"]["timeout"], 60)
        self.assertEqual(settings["ollama"]["parse"], "text")
        self.assertEqual(settings["ollama"]["bin"], "ollama")

    def test_none_providers_and_none_entries_tolerated(self):
        configs = (
            {"providers": None},
            {"providers": {"kimi": None}},
            {"providers": None, "defaults": {}},
        )
        for config in configs:
            with self.subTest(config=config):
                settings = E.provider_settings(config)
                self.assertEqual(settings["kimi"]["label"], "Kimi")
                self.assertEqual(settings["codex"]["parse"], "codex-jsonl")

    def test_does_not_mutate_builtin_provider_table(self):
        settings = E.provider_settings({"providers": {"kimi": {"model": "x"}}})
        settings["kimi"]["model"] = "mutated"
        settings["kimi"]["timeout"] = 1
        self.assertEqual(E.PROVIDERS["kimi"]["model"], "kimi-code")
        self.assertEqual(E.PROVIDERS["kimi"]["timeout"], 300)

    def test_command_template_is_preserved_for_custom_providers(self):
        command = ["my-cli", "--prompt", "{prompt}", "--model", "{model}"]
        settings = E.provider_settings({"providers": {"custom": {"command": command}}})
        self.assertEqual(settings["custom"]["command"], command)


class LoadConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ensemble-config-"))
        self.addCleanup(shutil.rmtree, str(self.tmp), True)

    def _write(self, name, payload):
        path = self.tmp / name
        path.write_text(json.dumps(payload))
        return path

    def test_missing_files_yield_empty_config(self):
        with mock.patch.object(E, "CONFIG_PATHS", [self.tmp / "nope.json"]):
            self.assertEqual(E.load_config(), {"defaults": {}, "providers": {}})

    def test_later_files_deep_merge_over_earlier(self):
        first = self._write(
            "first.json",
            {
                "defaults": {"context": "temp", "timeout": 100},
                "providers": {"kimi": {"model": "a"}},
            },
        )
        second = self._write(
            "second.json",
            {"providers": {"kimi": {"timeout": 90}, "codex": {"enabled": False}}},
        )
        with mock.patch.object(E, "CONFIG_PATHS", [first, second]):
            config = E.load_config()
        self.assertEqual(config["defaults"]["context"], "temp")
        self.assertEqual(config["defaults"]["timeout"], 100)
        self.assertEqual(config["providers"]["kimi"], {"model": "a", "timeout": 90})
        self.assertFalse(config["providers"]["codex"]["enabled"])

    def test_malformed_file_is_ignored(self):
        good = self._write("good.json", {"providers": {"kimi": {"model": "ok"}}})
        bad = self.tmp / "bad.json"
        bad.write_text("{this is not json")
        stderr = io.StringIO()
        with mock.patch.object(E, "CONFIG_PATHS", [bad, good]), redirect_stderr(stderr):
            config = E.load_config()
        self.assertEqual(config["providers"]["kimi"]["model"], "ok")
        self.assertIn("ignoring", stderr.getvalue())
        self.assertIn("bad.json", stderr.getvalue())

    def test_loaded_config_feeds_provider_settings(self):
        path = self._write(
            "cfg.json",
            {
                "defaults": {"models": {"gemini": "gemini-2.5-pro"}},
                "providers": {"kimi": {"timeout": 120}},
            },
        )
        with mock.patch.object(E, "CONFIG_PATHS", [path]):
            config = E.load_config()
        settings = E.provider_settings(config)
        self.assertEqual(settings["gemini"]["model"], "gemini-2.5-pro")
        self.assertEqual(settings["kimi"]["timeout"], 120)
        self.assertEqual(settings["kimi"]["label"], "Kimi")


class FindDshTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ensemble-dsh-"))
        self.addCleanup(shutil.rmtree, str(self.tmp), True)
        self.fake = self.tmp / "dsh"
        self.fake.write_text("#!/bin/sh\nexit 0\n")
        self.fake.chmod(0o755)

    def test_env_override_used_when_file_exists(self):
        with mock.patch.dict(os.environ, {"ENSEMBLE_DSH_PATH": str(self.fake)}):
            self.assertEqual(E.find_dsh({}), str(self.fake))

    def test_settings_path_used_when_env_absent(self):
        with mock.patch.dict(os.environ, {"ENSEMBLE_DSH_PATH": ""}):
            self.assertEqual(E.find_dsh({"deepseek": {"path": str(self.fake)}}), str(self.fake))

    def test_nonexistent_env_override_falls_through(self):
        missing = str(self.tmp / "missing-dsh")
        with mock.patch.dict(os.environ, {"ENSEMBLE_DSH_PATH": missing}):
            self.assertNotEqual(E.find_dsh({}), missing)


class EnvironmentIsolationTest(unittest.TestCase):
    def test_ensemble_home_is_a_temp_directory(self):
        self.assertEqual(E.HOME, _support.TEST_HOME)
        self.assertNotEqual(E.HOME, Path.home() / ".ensemble")
        self.assertTrue(E.HOME.is_dir())

    def test_derived_paths_point_into_test_home(self):
        self.assertEqual(E.GEMINI_KEY_FILE, _support.TEST_HOME / "gemini.key")


if __name__ == "__main__":
    unittest.main()
