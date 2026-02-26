"""Property test for Analysis cascade deletion.

**Validates: Requirements 6.5**

Property 15: Analysis cascade deletion — For any Analysis that is deleted,
all associated FunctionRecords, Claims, and Violations must also be removed
from the database, leaving no orphaned records.
"""

from __future__ import annotations

import uuid

from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import Session, sessionmaker

from app.models import Analysis, Base, Claim, FunctionRecord, Violation


def _make_session() -> Session:
    """Create a fresh in-memory SQLite session with all tables.

    Enables SQLite foreign-key enforcement so that ON DELETE CASCADE
    works correctly (SQLite disables it by default).
    """
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _build_analysis(
    n_functions: int,
    claims_per_fn: list[int],
    violations_flags: list[list[bool]],
) -> Analysis:
    """Build an Analysis object tree from the given shape parameters."""
    analysis = Analysis(
        id=str(uuid.uuid4()),
        source_code="def foo(): pass",
        llm_provider="gpt-4o",
        status="complete",
    )

    for fi in range(n_functions):
        fn = FunctionRecord(
            id=str(uuid.uuid4()),
            name=f"func_{fi}",
            qualified_name=f"mod.func_{fi}",
            source=f"def func_{fi}(): pass",
            lineno=fi + 1,
            signature=f"def func_{fi}()",
        )
        analysis.functions.append(fn)

        for ci in range(claims_per_fn[fi]):
            claim = Claim(
                id=str(uuid.uuid4()),
                category="RSV",
                subject="return",
                predicate_object=f"returns value {ci}",
                source_line=ci + 1,
                raw_text=f"Returns value {ci}.",
            )
            fn.claims.append(claim)

            if violations_flags[fi][ci]:
                violation = Violation(
                    id=str(uuid.uuid4()),
                    outcome="fail",
                    test_code=f"def test_{fi}_{ci}(): assert False",
                )
                claim.violation = violation

    return analysis


# ---------------------------------------------------------------------------
# Hypothesis strategy — generates random tree shapes
# ---------------------------------------------------------------------------

@st.composite
def analysis_shape(draw: st.DrawFn):
    """Draw (n_functions, claims_per_fn, violations_flags).

    Each Analysis has 1-5 FunctionRecords, each FunctionRecord has 1-5 Claims,
    and each Claim may or may not have a Violation (random boolean).
    """
    n_fns: int = draw(st.integers(min_value=1, max_value=5))
    claims_per: list[int] = [
        draw(st.integers(min_value=1, max_value=5)) for _ in range(n_fns)
    ]
    viol_flags: list[list[bool]] = [
        [draw(st.booleans()) for _ in range(claims_per[i])]
        for i in range(n_fns)
    ]
    return n_fns, claims_per, viol_flags


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@given(shape=analysis_shape())
@h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_cascade_deletion_removes_all_children(
    shape: tuple[int, list[int], list[list[bool]]],
) -> None:
    """Property 15: Deleting an Analysis leaves no orphaned records.

    **Validates: Requirements 6.5**
    """
    n_functions, claims_per_fn, violations_flags = shape
    session = _make_session()

    # --- Arrange: insert the full object tree ---
    analysis = _build_analysis(n_functions, claims_per_fn, violations_flags)
    session.add(analysis)
    session.commit()

    # Sanity: records exist
    assert session.scalar(select(func.count()).select_from(Analysis)) == 1
    assert session.scalar(select(func.count()).select_from(FunctionRecord)) == n_functions

    expected_claims = sum(claims_per_fn)
    assert session.scalar(select(func.count()).select_from(Claim)) == expected_claims

    expected_violations = sum(
        1 for flags in violations_flags for flag in flags if flag
    )
    assert session.scalar(select(func.count()).select_from(Violation)) == expected_violations

    # --- Act: delete the Analysis ---
    session.delete(analysis)
    session.commit()

    # --- Assert: all four tables are empty ---
    assert session.scalar(select(func.count()).select_from(Analysis)) == 0
    assert session.scalar(select(func.count()).select_from(FunctionRecord)) == 0
    assert session.scalar(select(func.count()).select_from(Claim)) == 0
    assert session.scalar(select(func.count()).select_from(Violation)) == 0

    session.close()
