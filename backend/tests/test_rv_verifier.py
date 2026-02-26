"""Tests for the Runtime Verifier.
Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 10.5, 10.6, 11.1
"""
from __future__ import annotations
import os
import shutil
import pytest
from app.schemas import BCVCategory, Claim, SynthesizedTest, TestOutcome, ViolationReport
from app.pipeline.rv.verifier import RuntimeVerifier


def _claim(**kw):
    d = dict(category=BCVCategory.RSV, subject="return",
             predicate_object="returns an int", conditionality=None,
             source_line=1, raw_text="Returns an int.")
    d.update(kw)
    return Claim(**d)


def _st(code, name="test_example", claim=None):
    return SynthesizedTest(claim=claim or _claim(), test_code=code,
                           test_function_name=name, synthesis_model="gpt-4o")


class TestWriteTestModule:
    def test_creates_file_and_conftest(self):
        rv = RuntimeVerifier(timeout=10)
        p = rv._write_test_module([_st("def test_a():\n    assert 1==1\n")], "def f(): pass\n")
        try:
            assert os.path.isfile(p) and p.endswith(".py")
            assert os.path.isfile(os.path.join(os.path.dirname(p), "conftest.py"))
        finally:
            shutil.rmtree(os.path.dirname(p), ignore_errors=True)

    def test_contains_source(self):
        rv = RuntimeVerifier(timeout=10)
        p = rv._write_test_module([_st("def test_m():\n    pass\n")], "def mul(x,y):\n    return x*y\n")
        try:
            assert "def mul(x,y):" in open(p).read()
        finally:
            shutil.rmtree(os.path.dirname(p), ignore_errors=True)

    def test_contains_tests(self):
        rv = RuntimeVerifier(timeout=10)
        p = rv._write_test_module([_st("def test_n():\n    assert True\n")], "pass\n")
        try:
            assert "def test_n():" in open(p).read()
        finally:
            shutil.rmtree(os.path.dirname(p), ignore_errors=True)

    def test_conftest_has_collector(self):
        rv = RuntimeVerifier(timeout=10)
        p = rv._write_test_module([_st("def test_x():\n    pass\n")], "pass\n")
        try:
            cf = open(os.path.join(os.path.dirname(p), "conftest.py")).read()
            assert "_ResultCollector" in cf and "pytest_runtest_logreport" in cf
        finally:
            shutil.rmtree(os.path.dirname(p), ignore_errors=True)

    def test_multiple_tests(self):
        rv = RuntimeVerifier(timeout=10)
        ts = [_st("def test_a():\n    pass\n", "test_a"),
              _st("def test_b():\n    pass\n", "test_b")]
        p = rv._write_test_module(ts, "pass\n")
        try:
            c = open(p).read()
            assert "def test_a():" in c and "def test_b():" in c
        finally:
            shutil.rmtree(os.path.dirname(p), ignore_errors=True)


class TestRunPytest:
    def test_passing(self):
        rv = RuntimeVerifier(timeout=10)
        p = rv._write_test_module([_st("def test_add():\n    assert 1+2==3\n")], "pass\n")
        r = rv._run_pytest(p)
        assert len(r) == 1 and r[0]["outcome"] == "passed"
        assert "test_add" in r[0]["nodeid"] and r[0]["duration"] >= 0

    def test_failing(self):
        rv = RuntimeVerifier(timeout=10)
        p = rv._write_test_module([_st("def test_bad():\n    assert 1==99\n", "test_bad")], "pass\n")
        r = rv._run_pytest(p)
        assert len(r) == 1 and r[0]["outcome"] == "failed"
        assert r[0]["traceback"] is not None

    def test_name_error(self):
        rv = RuntimeVerifier(timeout=10)
        p = rv._write_test_module([_st("def test_ne():\n    no_such_fn()\n", "test_ne")], "pass\n")
        r = rv._run_pytest(p)
        assert len(r) == 1 and r[0]["outcome"] == "failed"

    def test_mixed(self):
        rv = RuntimeVerifier(timeout=10)
        src = "def double(n):\n    return n*2\n"
        ts = [_st("def test_ok():\n    assert double(3)==6\n", "test_ok"),
              _st("def test_no():\n    assert double(3)==7\n", "test_no")]
        p = rv._write_test_module(ts, src)
        r = rv._run_pytest(p)
        assert len(r) == 2
        m = {x["nodeid"].split("::")[-1]: x["outcome"] for x in r}
        assert m["test_ok"] == "passed" and m["test_no"] == "failed"

    def test_stdout(self):
        rv = RuntimeVerifier(timeout=10)
        src = "def greet():\n    print('hello')\n    return 'hello'\n"
        p = rv._write_test_module(
            [_st("def test_g():\n    assert greet()=='hello'\n", "test_g")], src)
        r = rv._run_pytest(p)
        assert len(r) == 1 and "hello" in r[0]["stdout"]

    def test_timeout(self):
        rv = RuntimeVerifier(timeout=2)
        src = "import time\ndef slow():\n    time.sleep(60)\n"
        p = rv._write_test_module([_st("def test_s():\n    slow()\n", "test_s")], src)
        assert rv._run_pytest(p) == []

    def test_result_keys(self):
        rv = RuntimeVerifier(timeout=10)
        p = rv._write_test_module([_st("def test_k():\n    assert True\n", "test_k")], "pass\n")
        r = rv._run_pytest(p)
        assert len(r) == 1
        assert set(r[0].keys()) == {"nodeid", "outcome", "stdout", "stderr", "traceback", "duration"}

    def test_cleanup(self):
        rv = RuntimeVerifier(timeout=10)
        p = rv._write_test_module([_st("def test_c():\n    assert True\n")], "pass\n")
        d = os.path.dirname(p)
        assert os.path.isdir(d)
        rv._run_pytest(p)
        assert not os.path.isdir(d)


class TestClassifyOutcome:
    def test_passed_maps_to_pass(self):
        rv = RuntimeVerifier(timeout=10)
        assert rv._classify_outcome({"outcome": "passed"}) == TestOutcome.PASS

    def test_failed_maps_to_fail(self):
        rv = RuntimeVerifier(timeout=10)
        assert rv._classify_outcome({"outcome": "failed"}) == TestOutcome.FAIL

    def test_error_maps_to_error(self):
        rv = RuntimeVerifier(timeout=10)
        assert rv._classify_outcome({"outcome": "error"}) == TestOutcome.ERROR

    def test_unknown_maps_to_undetermined(self):
        rv = RuntimeVerifier(timeout=10)
        assert rv._classify_outcome({"outcome": "skipped"}) == TestOutcome.UNDETERMINED

    def test_missing_outcome_maps_to_undetermined(self):
        rv = RuntimeVerifier(timeout=10)
        assert rv._classify_outcome({}) == TestOutcome.UNDETERMINED


class TestExtractExpectedActual:
    def test_none_traceback(self):
        rv = RuntimeVerifier(timeout=10)
        assert rv._extract_expected_actual(None) == (None, None)

    def test_assert_eq_pattern(self):
        rv = RuntimeVerifier(timeout=10)
        tb = "E       assert 42 == 99"
        expected, actual = rv._extract_expected_actual(tb)
        assert expected == "99"
        assert actual == "42"

    def test_no_assert_pattern(self):
        rv = RuntimeVerifier(timeout=10)
        tb = "NameError: name 'foo' is not defined"
        assert rv._extract_expected_actual(tb) == (None, None)


class TestVerify:
    def test_empty_suite(self):
        rv = RuntimeVerifier(timeout=10)
        report = rv.verify([], "pass\n", analysis_id="a1", function_name="f")
        assert isinstance(report, ViolationReport)
        assert report.total_claims == 0
        assert report.violations == []
        assert report.bcv_rate == 0.0

    def test_all_passing(self):
        rv = RuntimeVerifier(timeout=10)
        src = "def add(a, b):\n    return a + b\n"
        ts = [_st("def test_add():\n    assert add(1, 2) == 3\n", "test_add")]
        report = rv.verify(ts, src, analysis_id="a2", function_name="add")
        assert report.pass_count == 1
        assert report.fail_count == 0
        assert report.violations == []
        assert report.bcv_rate == 0.0

    def test_all_failing(self):
        rv = RuntimeVerifier(timeout=10)
        src = "def add(a, b):\n    return a - b\n"
        ts = [_st("def test_add():\n    assert add(1, 2) == 3\n", "test_add")]
        report = rv.verify(ts, src, analysis_id="a3", function_name="add")
        assert report.pass_count == 0
        assert report.fail_count == 1
        assert report.bcv_rate == 1.0
        assert len(report.violations) == 1
        assert report.violations[0].outcome == TestOutcome.FAIL
        assert report.violations[0].traceback is not None

    def test_mixed_pass_fail(self):
        rv = RuntimeVerifier(timeout=10)
        src = "def double(n):\n    return n * 2\n"
        ts = [
            _st("def test_ok():\n    assert double(3) == 6\n", "test_ok"),
            _st("def test_bad():\n    assert double(3) == 7\n", "test_bad"),
        ]
        report = rv.verify(ts, src, analysis_id="a4", function_name="double")
        assert report.pass_count == 1
        assert report.fail_count == 1
        assert report.bcv_rate == pytest.approx(0.5)
        assert len(report.violations) == 1
        assert report.violations[0].outcome == TestOutcome.FAIL

    def test_violations_only_contain_fails(self):
        rv = RuntimeVerifier(timeout=10)
        src = "def inc(n):\n    return n + 1\n"
        ts = [
            _st("def test_pass():\n    assert inc(1) == 2\n", "test_pass"),
            _st("def test_fail():\n    assert inc(1) == 99\n", "test_fail"),
        ]
        report = rv.verify(ts, src, analysis_id="a5", function_name="inc")
        for v in report.violations:
            assert v.outcome == TestOutcome.FAIL

    def test_bcv_rate_range(self):
        rv = RuntimeVerifier(timeout=10)
        src = "def f():\n    return 1\n"
        ts = [_st("def test_f():\n    assert f() == 1\n", "test_f")]
        report = rv.verify(ts, src)
        assert 0.0 <= report.bcv_rate <= 1.0

    def test_report_fields(self):
        rv = RuntimeVerifier(timeout=10)
        src = "def f():\n    return 1\n"
        ts = [_st("def test_f():\n    assert f() == 1\n", "test_f")]
        report = rv.verify(ts, src, analysis_id="id1", function_name="f")
        assert report.analysis_id == "id1"
        assert report.function_name == "f"
        assert report.total_claims == 1
