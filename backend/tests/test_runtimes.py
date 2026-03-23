"""Unit tests for RuntimeRegistry and all runtime adapters.

**Validates: Requirements 4.1, 4.7, 4.8, 4.9**

Tests:
- RuntimeRegistry.get() returns correct adapter for each language
- RuntimeRegistry.get() raises UnsupportedRuntimeError for unknown language
- RuntimeRegistry.supported_languages() returns all registered languages
- Each adapter's is_available() returns a boolean
- PythonRuntimeAdapter.execute() works end-to-end with a simple test
- Output parsing methods for non-Python adapters with mock data
- Each adapter's write_test_module() creates files in tmpdir
- UnsupportedRuntimeError has correct language attribute and message
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

# Force all runtime adapters to register themselves
import app.pipeline.runtimes.python_runtime  # noqa: F401
import app.pipeline.runtimes.nodejs_runtime  # noqa: F401
import app.pipeline.runtimes.java_runtime  # noqa: F401
import app.pipeline.runtimes.go_runtime  # noqa: F401
import app.pipeline.runtimes.rust_runtime  # noqa: F401

from app.pipeline.runtimes import RuntimeAdapter as _RuntimeAdapterABC, UnsupportedRuntimeError
from app.pipeline.runtimes.registry import RuntimeRegistry
from app.pipeline.runtimes.python_runtime import PythonRuntimeAdapter
from app.pipeline.runtimes.nodejs_runtime import NodeJSRuntimeAdapter
from app.pipeline.runtimes.java_runtime import JavaRuntimeAdapter, _parse_junit_output
from app.pipeline.runtimes.go_runtime import GoRuntimeAdapter
from app.pipeline.runtimes.rust_runtime import RustRuntimeAdapter


# ===========================================================================
# RuntimeRegistry tests  (Requirement 4.1)
# ===========================================================================


class TestRuntimeRegistry:
    """Tests for RuntimeRegistry lookup, registration, and error handling."""

    def test_get_returns_correct_adapter_for_python(self):
        assert isinstance(RuntimeRegistry.get("python"), PythonRuntimeAdapter)

    def test_get_returns_correct_adapter_for_javascript(self):
        assert isinstance(RuntimeRegistry.get("javascript"), NodeJSRuntimeAdapter)

    def test_get_returns_correct_adapter_for_typescript(self):
        assert isinstance(RuntimeRegistry.get("typescript"), NodeJSRuntimeAdapter)

    def test_get_returns_correct_adapter_for_java(self):
        assert isinstance(RuntimeRegistry.get("java"), JavaRuntimeAdapter)

    def test_get_returns_correct_adapter_for_go(self):
        assert isinstance(RuntimeRegistry.get("go"), GoRuntimeAdapter)

    def test_get_returns_correct_adapter_for_rust(self):
        assert isinstance(RuntimeRegistry.get("rust"), RustRuntimeAdapter)

    def test_get_raises_unsupported_runtime_error_for_unknown(self):
        with pytest.raises(UnsupportedRuntimeError):
            RuntimeRegistry.get("cobol")

    def test_unsupported_error_message_contains_language(self):
        with pytest.raises(UnsupportedRuntimeError, match="cobol"):
            RuntimeRegistry.get("cobol")

    def test_unsupported_error_has_language_attribute(self):
        with pytest.raises(UnsupportedRuntimeError) as exc_info:
            RuntimeRegistry.get("fortran")
        assert exc_info.value.language == "fortran"

    def test_supported_languages_returns_all_registered(self):
        langs = RuntimeRegistry.supported_languages()
        for expected in ("python", "javascript", "typescript", "java", "go", "rust"):
            assert expected in langs

    def test_supported_languages_returns_list(self):
        assert isinstance(RuntimeRegistry.supported_languages(), list)

    def test_get_returns_new_instance_each_call(self):
        a = RuntimeRegistry.get("python")
        b = RuntimeRegistry.get("python")
        assert a is not b

    def test_all_adapters_are_runtime_adapter_subclasses(self):
        for lang in RuntimeRegistry.supported_languages():
            adapter = RuntimeRegistry.get(lang)
            assert isinstance(adapter, _RuntimeAdapterABC)


# ===========================================================================
# UnsupportedRuntimeError tests  (Requirement 4.9)
# ===========================================================================


class TestUnsupportedRuntimeError:
    """Tests for UnsupportedRuntimeError attributes and message."""

    def test_has_language_attribute(self):
        err = UnsupportedRuntimeError("haskell")
        assert err.language == "haskell"

    def test_message_contains_language(self):
        err = UnsupportedRuntimeError("haskell")
        assert "haskell" in str(err)

    def test_message_mentions_no_adapter(self):
        err = UnsupportedRuntimeError("haskell")
        msg = str(err).lower()
        assert "no runtime adapter" in msg or "unsupported" in msg

    def test_is_exception_subclass(self):
        assert issubclass(UnsupportedRuntimeError, Exception)


# ===========================================================================
# is_available() tests  (Requirement 4.8)
# ===========================================================================


class TestIsAvailable:
    """Each adapter's is_available() must return a boolean."""

    @pytest.mark.parametrize("language", RuntimeRegistry.supported_languages())
    def test_is_available_returns_bool(self, language):
        adapter = RuntimeRegistry.get(language)
        result = adapter.is_available()
        assert isinstance(result, bool)

    def test_python_runtime_is_available(self):
        """pytest IS available in the test environment."""
        adapter = PythonRuntimeAdapter()
        assert adapter.is_available() is True


# ===========================================================================
# write_test_module() tests  (Requirement 4.7)
# ===========================================================================


class TestWriteTestModule:
    """Each adapter's write_test_module() creates files in tmpdir."""

    def test_python_write_test_module(self, tmp_path):
        adapter = PythonRuntimeAdapter()
        tests = [{"test_code": "def test_add():\n    assert 1 + 1 == 2\n"}]
        source = "def add(a, b):\n    return a + b\n"
        result = adapter.write_test_module(tests, source, str(tmp_path))
        assert os.path.isfile(result)
        content = open(result).read()
        assert "test_add" in content
        assert "def add" in content
        # conftest.py should also be created
        assert os.path.isfile(os.path.join(str(tmp_path), "conftest.py"))

    def test_nodejs_write_test_module(self, tmp_path):
        adapter = NodeJSRuntimeAdapter()
        tests = [{"test_code": "test('adds', () => { expect(1+1).toBe(2); });"}]
        source = "function add(a, b) { return a + b; }"
        result = adapter.write_test_module(tests, source, str(tmp_path))
        assert os.path.isfile(result)
        assert result.endswith(".test.js")
        # source.js should also be created
        assert os.path.isfile(os.path.join(str(tmp_path), "source.js"))

    def test_java_write_test_module(self, tmp_path):
        adapter = JavaRuntimeAdapter()
        tests = [{"test_code": "import org.junit.jupiter.api.Test;\npublic class SourceTest {\n    @Test\n    void testAdd() {}\n}\n"}]
        source = "public class Source {\n    public int add(int a, int b) { return a + b; }\n}\n"
        result = adapter.write_test_module(tests, source, str(tmp_path))
        assert os.path.isfile(result)
        assert result.endswith(".java")

    def test_go_write_test_module(self, tmp_path):
        adapter = GoRuntimeAdapter()
        tests = [{"test_code": 'package veridoc_test\nimport "testing"\nfunc TestAdd(t *testing.T) {}\n'}]
        source = "package veridoc_test\nfunc Add(a, b int) int { return a + b }\n"
        result = adapter.write_test_module(tests, source, str(tmp_path))
        assert os.path.isfile(result)
        assert result.endswith("_test.go")
        # go.mod should also be created
        assert os.path.isfile(os.path.join(str(tmp_path), "go.mod"))

    def test_rust_write_test_module(self, tmp_path):
        adapter = RustRuntimeAdapter()
        tests = [{"test_code": "#[cfg(test)]\nmod tests {\n    #[test]\n    fn test_add() { assert_eq!(1+1, 2); }\n}\n"}]
        source = "pub fn add(a: i32, b: i32) -> i32 { a + b }\n"
        result = adapter.write_test_module(tests, source, str(tmp_path))
        assert os.path.isfile(result)
        assert result.endswith("lib.rs")
        # Cargo.toml should also be created
        assert os.path.isfile(os.path.join(str(tmp_path), "Cargo.toml"))


# ===========================================================================
# PythonRuntimeAdapter end-to-end test  (Requirement 4.2, 4.7)
# ===========================================================================


class TestPythonRuntimeAdapterE2E:
    """End-to-end test for PythonRuntimeAdapter since pytest IS available."""

    def test_execute_passing_test(self, tmp_path):
        adapter = PythonRuntimeAdapter()
        tests = [{"test_code": "def test_add():\n    assert add(2, 3) == 5\n"}]
        source = "def add(a, b):\n    return a + b\n"
        test_path = adapter.write_test_module(tests, source, str(tmp_path))
        results = adapter.execute(test_path, timeout=30)
        assert len(results) == 1
        assert results[0]["outcome"] == "passed"
        assert "nodeid" in results[0]
        assert "stdout" in results[0]
        assert "stderr" in results[0]
        assert "traceback" in results[0]
        assert "duration" in results[0]

    def test_execute_failing_test(self, tmp_path):
        adapter = PythonRuntimeAdapter()
        tests = [{"test_code": "def test_fail():\n    assert 1 == 2\n"}]
        source = ""
        test_path = adapter.write_test_module(tests, source, str(tmp_path))
        results = adapter.execute(test_path, timeout=30)
        assert len(results) == 1
        assert results[0]["outcome"] == "failed"
        assert results[0]["traceback"] is not None

    def test_execute_multiple_tests(self, tmp_path):
        adapter = PythonRuntimeAdapter()
        tests = [
            {"test_code": "def test_pass():\n    assert True\n"},
            {"test_code": "def test_also_pass():\n    assert 1 + 1 == 2\n"},
        ]
        source = ""
        test_path = adapter.write_test_module(tests, source, str(tmp_path))
        results = adapter.execute(test_path, timeout=30)
        assert len(results) == 2
        assert all(r["outcome"] == "passed" for r in results)

    def test_execute_result_keys(self, tmp_path):
        """Verify all required keys are present in each result dict."""
        adapter = PythonRuntimeAdapter()
        tests = [{"test_code": "def test_ok():\n    pass\n"}]
        source = ""
        test_path = adapter.write_test_module(tests, source, str(tmp_path))
        results = adapter.execute(test_path, timeout=30)
        required_keys = {"nodeid", "outcome", "stdout", "stderr", "traceback", "duration"}
        for result in results:
            assert required_keys.issubset(result.keys())


# ===========================================================================
# NodeJSRuntimeAdapter parse tests  (Requirement 4.3, 4.7)
# ===========================================================================


class TestNodeJSParseVitestJson:
    """Test NodeJSRuntimeAdapter._parse_vitest_json with mock data."""

    def test_parse_passing_tests(self):
        vitest_output = json.dumps({
            "testResults": [{
                "name": "source.test.js",
                "assertionResults": [
                    {
                        "ancestorTitles": ["math"],
                        "title": "adds numbers",
                        "status": "passed",
                        "duration": 5,
                        "failureMessages": [],
                    }
                ],
            }]
        })
        results = NodeJSRuntimeAdapter._parse_vitest_json(vitest_output)
        assert len(results) == 1
        assert results[0]["outcome"] == "passed"
        assert results[0]["nodeid"] == "math > adds numbers"
        assert results[0]["duration"] == 0.005  # 5ms -> seconds

    def test_parse_failing_tests(self):
        vitest_output = json.dumps({
            "testResults": [{
                "name": "source.test.js",
                "assertionResults": [
                    {
                        "ancestorTitles": ["math"],
                        "title": "subtracts numbers",
                        "status": "failed",
                        "duration": 3,
                        "failureMessages": ["Expected 5 but got 3"],
                    }
                ],
            }]
        })
        results = NodeJSRuntimeAdapter._parse_vitest_json(vitest_output)
        assert len(results) == 1
        assert results[0]["outcome"] == "failed"
        assert results[0]["traceback"] is not None
        assert "Expected 5" in results[0]["traceback"]

    def test_parse_empty_output(self):
        results = NodeJSRuntimeAdapter._parse_vitest_json("")
        assert results == []

    def test_parse_invalid_json(self):
        results = NodeJSRuntimeAdapter._parse_vitest_json("not json at all")
        assert results == []

    def test_parse_multiple_tests(self):
        vitest_output = json.dumps({
            "testResults": [{
                "name": "source.test.js",
                "assertionResults": [
                    {"ancestorTitles": [], "title": "test1", "status": "passed", "duration": 1, "failureMessages": []},
                    {"ancestorTitles": [], "title": "test2", "status": "failed", "duration": 2, "failureMessages": ["err"]},
                ],
            }]
        })
        results = NodeJSRuntimeAdapter._parse_vitest_json(vitest_output)
        assert len(results) == 2
        assert results[0]["outcome"] == "passed"
        assert results[1]["outcome"] == "failed"

    def test_result_keys_present(self):
        vitest_output = json.dumps({
            "testResults": [{
                "name": "source.test.js",
                "assertionResults": [
                    {"ancestorTitles": [], "title": "t", "status": "passed", "duration": 0, "failureMessages": []},
                ],
            }]
        })
        results = NodeJSRuntimeAdapter._parse_vitest_json(vitest_output)
        required_keys = {"nodeid", "outcome", "stdout", "stderr", "traceback", "duration"}
        for r in results:
            assert required_keys.issubset(r.keys())


# ===========================================================================
# GoRuntimeAdapter parse tests  (Requirement 4.5, 4.7)
# ===========================================================================


class TestGoParseGoTestJson:
    """Test GoRuntimeAdapter._parse_go_test_json with mock data."""

    def test_parse_passing_test(self):
        lines = [
            json.dumps({"Action": "run", "Test": "TestAdd", "Package": "veridoc_test"}),
            json.dumps({"Action": "output", "Test": "TestAdd", "Output": "=== RUN   TestAdd\n"}),
            json.dumps({"Action": "output", "Test": "TestAdd", "Output": "--- PASS: TestAdd (0.00s)\n"}),
            json.dumps({"Action": "pass", "Test": "TestAdd", "Elapsed": 0.001}),
        ]
        stdout = "\n".join(lines)
        results = GoRuntimeAdapter._parse_go_test_json(stdout, "")
        assert len(results) == 1
        assert results[0]["outcome"] == "passed"
        assert results[0]["nodeid"] == "TestAdd"
        assert results[0]["duration"] == 0.001

    def test_parse_failing_test(self):
        lines = [
            json.dumps({"Action": "run", "Test": "TestFail", "Package": "veridoc_test"}),
            json.dumps({"Action": "output", "Test": "TestFail", "Output": "    source_test.go:10: expected 5 got 3\n"}),
            json.dumps({"Action": "fail", "Test": "TestFail", "Elapsed": 0.002}),
        ]
        stdout = "\n".join(lines)
        results = GoRuntimeAdapter._parse_go_test_json(stdout, "")
        assert len(results) == 1
        assert results[0]["outcome"] == "failed"
        assert results[0]["traceback"] is not None

    def test_parse_skipped_test(self):
        lines = [
            json.dumps({"Action": "run", "Test": "TestSkip", "Package": "veridoc_test"}),
            json.dumps({"Action": "output", "Test": "TestSkip", "Output": "--- SKIP: TestSkip\n"}),
            json.dumps({"Action": "skip", "Test": "TestSkip", "Elapsed": 0.0}),
        ]
        stdout = "\n".join(lines)
        results = GoRuntimeAdapter._parse_go_test_json(stdout, "")
        assert len(results) == 1
        assert results[0]["outcome"] == "skipped"

    def test_parse_empty_output(self):
        results = GoRuntimeAdapter._parse_go_test_json("", "")
        assert results == []

    def test_parse_ignores_package_level_events(self):
        lines = [
            json.dumps({"Action": "pass", "Package": "veridoc_test", "Elapsed": 0.5}),
        ]
        stdout = "\n".join(lines)
        results = GoRuntimeAdapter._parse_go_test_json(stdout, "")
        assert results == []

    def test_result_keys_present(self):
        lines = [
            json.dumps({"Action": "pass", "Test": "TestOk", "Elapsed": 0.01}),
        ]
        stdout = "\n".join(lines)
        results = GoRuntimeAdapter._parse_go_test_json(stdout, "")
        required_keys = {"nodeid", "outcome", "stdout", "stderr", "traceback", "duration"}
        for r in results:
            assert required_keys.issubset(r.keys())


# ===========================================================================
# RustRuntimeAdapter parse tests  (Requirement 4.6, 4.7)
# ===========================================================================


class TestRustParseCargoTestOutput:
    """Test RustRuntimeAdapter._parse_cargo_test_output with mock data."""

    def test_parse_passing_test(self):
        stdout = "test tests::test_add ... ok\n\ntest result: ok. 1 passed; 0 failed;\n"
        results = RustRuntimeAdapter._parse_cargo_test_output(stdout, "")
        assert len(results) == 1
        assert results[0]["outcome"] == "passed"
        assert results[0]["nodeid"] == "tests::test_add"

    def test_parse_failing_test(self):
        stdout = (
            "test tests::test_sub ... FAILED\n\n"
            "failures:\n\n"
            "---- tests::test_sub stdout ----\n"
            "thread 'tests::test_sub' panicked at 'assertion failed'\n\n"
            "failures:\n"
            "    tests::test_sub\n\n"
            "test result: FAILED. 0 passed; 1 failed;\n"
        )
        results = RustRuntimeAdapter._parse_cargo_test_output(stdout, "")
        assert len(results) == 1
        assert results[0]["outcome"] == "failed"
        assert results[0]["traceback"] is not None
        assert "panicked" in results[0]["traceback"]

    def test_parse_mixed_results(self):
        stdout = (
            "test tests::test_ok ... ok\n"
            "test tests::test_bad ... FAILED\n\n"
            "failures:\n\n"
            "---- tests::test_bad stdout ----\n"
            "assertion failed\n\n"
            "failures:\n"
            "    tests::test_bad\n\n"
            "test result: FAILED. 1 passed; 1 failed;\n"
        )
        results = RustRuntimeAdapter._parse_cargo_test_output(stdout, "")
        assert len(results) == 2
        outcomes = {r["nodeid"]: r["outcome"] for r in results}
        assert outcomes["tests::test_ok"] == "passed"
        assert outcomes["tests::test_bad"] == "failed"

    def test_parse_ignored_test(self):
        stdout = "test tests::test_skip ... ignored\n\ntest result: ok. 0 passed; 0 failed; 1 ignored;\n"
        results = RustRuntimeAdapter._parse_cargo_test_output(stdout, "")
        assert len(results) == 1
        assert results[0]["outcome"] == "skipped"

    def test_parse_empty_output(self):
        results = RustRuntimeAdapter._parse_cargo_test_output("", "")
        assert results == []

    def test_result_keys_present(self):
        stdout = "test tests::test_x ... ok\n"
        results = RustRuntimeAdapter._parse_cargo_test_output(stdout, "")
        required_keys = {"nodeid", "outcome", "stdout", "stderr", "traceback", "duration"}
        for r in results:
            assert required_keys.issubset(r.keys())


# ===========================================================================
# JavaRuntimeAdapter parse tests  (Requirement 4.4, 4.7)
# ===========================================================================


class TestJavaParseJunitOutput:
    """Test _parse_junit_output with mock data."""

    def test_parse_tree_output_passing(self):
        stdout = (
            "├─ JUnit Jupiter ✔\n"
            "│  └─ SourceTest ✔\n"
            "│     ├─ testAdd() ✔\n"
            "│     └─ testSub() ✔\n"
        )
        results = _parse_junit_output(stdout, "")
        assert len(results) == 2
        assert all(r["outcome"] == "passed" for r in results)

    def test_parse_tree_output_failing(self):
        stdout = (
            "├─ JUnit Jupiter ✔\n"
            "│  └─ SourceTest ✔\n"
            "│     ├─ testAdd() ✔\n"
            "│     └─ testSub() ✘\n"
        )
        results = _parse_junit_output(stdout, "")
        assert len(results) == 2
        outcomes = {r["nodeid"]: r["outcome"] for r in results}
        assert outcomes["testAdd()"] == "passed"
        assert outcomes["testSub()"] == "failed"

    def test_parse_summary_fallback(self):
        stdout = "[ 2 tests successful ]\n[ 1 tests failed ]\n"
        results = _parse_junit_output(stdout, "")
        assert len(results) == 3
        passed = [r for r in results if r["outcome"] == "passed"]
        failed = [r for r in results if r["outcome"] == "failed"]
        assert len(passed) == 2
        assert len(failed) == 1

    def test_parse_empty_output(self):
        results = _parse_junit_output("", "")
        assert results == []

    def test_result_keys_present(self):
        stdout = "│     ├─ testOk() ✔\n"
        results = _parse_junit_output(stdout, "")
        required_keys = {"nodeid", "outcome", "stdout", "stderr", "traceback", "duration"}
        for r in results:
            assert required_keys.issubset(r.keys())


# ===========================================================================
# Cross-adapter contract tests  (Requirement 4.7)
# ===========================================================================


class TestCrossAdapterContracts:
    """Verify contracts that all RuntimeAdapter implementations must satisfy."""

    @pytest.mark.parametrize("language", RuntimeRegistry.supported_languages())
    def test_is_available_returns_bool(self, language):
        adapter = RuntimeRegistry.get(language)
        assert isinstance(adapter.is_available(), bool)

    @pytest.mark.parametrize("language", RuntimeRegistry.supported_languages())
    def test_adapter_has_required_methods(self, language):
        adapter = RuntimeRegistry.get(language)
        assert callable(getattr(adapter, "write_test_module", None))
        assert callable(getattr(adapter, "execute", None))
        assert callable(getattr(adapter, "is_available", None))
