"""status.holding_period (§7.3) and residence.travel_consistency (§7.8) evaluators. Pure."""

import uuid
from datetime import date

from app.requirements.domain import Conclusion
from app.requirements.evaluation import (
    KEY_TRAVEL_CONSISTENCY,
    EvaluatedResult,
    EvidenceLinkInput,
    ResidenceAssessmentInputs,
    RouteAssessmentInputs,
    TripInput,
    evaluate_residence_requirements,
    evaluate_status_holding_period,
)

_APP = date(2027, 4, 15)


def _status_inputs(granted: date | None, app: date = _APP) -> RouteAssessmentInputs:
    return RouteAssessmentInputs(
        date_of_birth=date(1990, 5, 1),
        status_type="ILR",
        status_granted_on=granted,
        married_to_british_citizen=False,
        may_already_be_british=False,
        application_date=app,
        route_profile_version_id=uuid.uuid4(),
        application_date_version_id=uuid.uuid4(),
    )


def test_holding_period_supported_with_clear_margin() -> None:
    result = evaluate_status_holding_period(_status_inputs(date(2025, 3, 1)))
    # earliest = 2026-03-01; app 2027-04-15 is well past earliest + 7 days.
    assert result.conclusion == Conclusion.SUPPORTED.value
    assert result.summary_code == "STATUS_PERIOD_SATISFIED"
    assert result.summary_parameters["earliest_application_date"] == "2026-03-01"


def test_holding_period_narrow_margin_is_supported_with_caution() -> None:
    # earliest = 2026-04-16; app 2026-04-20 is inside the 7-day caution band.
    result = evaluate_status_holding_period(
        _status_inputs(date(2025, 4, 16), app=date(2026, 4, 20))
    )
    assert result.conclusion == Conclusion.SUPPORTED.value
    assert result.summary_code == "STATUS_PERIOD_NARROW_MARGIN"
    assert result.limitations[0].severity.value == "CAUTION"


def test_holding_period_not_yet_met_returns_earliest_date() -> None:
    # earliest = 2027-05-01; app 2027-04-15 is before it.
    result = evaluate_status_holding_period(_status_inputs(date(2026, 5, 1), app=date(2027, 4, 15)))
    assert result.conclusion == Conclusion.NOT_CURRENTLY_SATISFIED.value
    assert result.summary_code == "STATUS_PERIOD_NOT_YET_MET"
    assert result.next_actions[0].label_parameters["earliest_application_date"] == "2027-05-01"


def test_holding_period_incomplete_when_grant_date_missing() -> None:
    result = evaluate_status_holding_period(_status_inputs(None))
    assert result.conclusion == Conclusion.INCOMPLETE.value


def _consistency(*trips: TripInput, evidenced: bool = True) -> EvaluatedResult:
    """Evaluate the consistency rule.

    `evidenced=True` by default — one link per trip — so the tests below stay about the
    property each is named for. Without it every one of them would also be asserting the
    coverage detection, and a change to coverage would turn a dozen unrelated tests red.
    The coverage tests pass `evidenced=False` and say so.
    """
    links = (
        tuple(
            EvidenceLinkInput(link_id=uuid.uuid4(), travel_record_id=t.travel_record_id)
            for t in trips
        )
        if evidenced
        else ()
    )
    inputs = ResidenceAssessmentInputs(
        application_date=_APP,
        application_date_version_id=uuid.uuid4(),
        trips=tuple(trips),
        evidence_links=links,
    )
    return {r.requirement_key: r for r in evaluate_residence_requirements(inputs)}[
        KEY_TRAVEL_CONSISTENCY
    ]


def _trip(
    dep: date,
    ret: date,
    *,
    confidence: str = "EXACT",
    trusted: bool = True,
    record_id: uuid.UUID | None = None,
    review_state: str = "CONFIRMED",
    country: str | None = None,
    label: str = "",
) -> TripInput:
    return TripInput(
        departure_date=dep,
        return_date=ret,
        travel_record_version_id=uuid.uuid4(),
        travel_record_id=record_id or uuid.uuid4(),
        is_trusted=trusted,
        destination_country_code=country,
        destination_label=label,
        date_confidence=confidence,
        review_state=review_state,
    )


def test_consistency_supported_with_clean_records() -> None:
    result = _consistency(_trip(date(2023, 1, 1), date(2023, 1, 20)))
    assert result.conclusion == Conclusion.SUPPORTED.value
    assert result.summary_code == "TRAVEL_RECORDS_CONSISTENT"


def test_conflicting_date_is_inconsistent() -> None:
    result = _consistency(_trip(date(2023, 1, 1), date(2023, 1, 20), confidence="CONFLICTING"))
    assert result.conclusion == Conclusion.INCONSISTENT.value
    assert result.summary_code == "TRAVEL_RECORDS_CONFLICT"
    assert result.limitations[0].code == "CONFLICTING_SOURCE_DATES"


def test_overlapping_trips_are_inconsistent() -> None:
    result = _consistency(
        _trip(date(2023, 1, 1), date(2023, 1, 20)),
        _trip(date(2023, 1, 10), date(2023, 1, 30)),
    )
    assert result.conclusion == Conclusion.INCONSISTENT.value
    assert result.summary_code == "TRAVEL_RECORDS_OVERLAP"


def test_uncertain_date_is_incomplete() -> None:
    result = _consistency(_trip(date(2023, 1, 1), date(2023, 1, 20), confidence="ESTIMATED"))
    assert result.conclusion == Conclusion.INCOMPLETE.value
    assert result.summary_code == "TRAVEL_RECORDS_UNCERTAIN"


def test_out_of_window_conflict_is_not_flagged() -> None:
    # A CONFLICTING trip wholly before the qualifying window (starts 2022-04-16 for this app
    # date) is informational only: window-scoped like UNCERTAIN, it is not surfaced (§7.8).
    result = _consistency(_trip(date(2019, 1, 1), date(2019, 1, 20), confidence="CONFLICTING"))
    assert result.conclusion == Conclusion.SUPPORTED.value
    assert result.summary_code == "TRAVEL_RECORDS_CONSISTENT"


def test_boundary_trip_is_flagged_but_stays_consistent() -> None:
    # A trip whose absent set contains the anchor 2022-04-16 raises a boundary note, but
    # a single clean-confidence trip is not itself an inconsistency.
    result = _consistency(_trip(date(2022, 4, 14), date(2022, 4, 26)))
    assert result.conclusion == Conclusion.SUPPORTED.value
    assert any(limitation.code == "NEAR_STANDARD_THRESHOLD" for limitation in result.limitations)


# --- coverage (§7.8, from v2.0.0) ---------------------------------------------------


def test_a_confirmed_trip_with_no_document_is_reported_but_still_consistent() -> None:
    """§7.8: "only informational detections → SUPPORTED + limitations".

    The conclusion stays SUPPORTED because the *records* are consistent — what is missing
    is paperwork the user has not filed. A data-quality rule that downgraded its verdict
    for that would be reporting a document-management state as a defect in the travel
    history, and the user would go looking for an error in dates that are perfectly fine.
    """
    result = _consistency(_trip(date(2023, 1, 1), date(2023, 1, 20)), evidenced=False)

    assert result.conclusion == Conclusion.SUPPORTED.value
    assert result.summary_code == "TRAVEL_RECORDS_UNEVIDENCED"
    codes = [lim.code for lim in result.limitations]
    assert "MISSING_TRAVEL_EVIDENCE" in codes


def test_an_evidenced_trip_is_not_reported() -> None:
    result = _consistency(_trip(date(2023, 1, 1), date(2023, 1, 20)))

    assert result.summary_code == "TRAVEL_RECORDS_CONSISTENT"
    assert [lim.code for lim in result.limitations] == []


def test_only_the_unevidenced_trips_are_named() -> None:
    """The limitation carries `affected_input_ids`, which the issue queue turns into one
    item per trip. Naming an evidenced trip there would send the user to a row with a
    document already attached and nothing to do."""
    covered = _trip(date(2023, 1, 1), date(2023, 1, 20))
    bare = _trip(date(2024, 3, 1), date(2024, 3, 10))

    inputs = ResidenceAssessmentInputs(
        application_date=_APP,
        application_date_version_id=uuid.uuid4(),
        trips=(covered, bare),
        evidence_links=(
            EvidenceLinkInput(link_id=uuid.uuid4(), travel_record_id=covered.travel_record_id),
        ),
    )
    result = {r.requirement_key: r for r in evaluate_residence_requirements(inputs)}[
        KEY_TRAVEL_CONSISTENCY
    ]

    limitation = next(lim for lim in result.limitations if lim.code == "MISSING_TRAVEL_EVIDENCE")
    assert limitation.affected_input_ids == (str(bare.travel_record_version_id),)


def test_an_unconfirmed_trip_is_not_asked_for_documents() -> None:
    """§7.8 says *confirmed* trip. A draft or uncertain record is something the user is
    still deciding about, and asking them to evidence it before they have decided it
    happened is noise in a queue whose value is that everything in it is actionable."""
    result = _consistency(
        _trip(date(2023, 1, 1), date(2023, 1, 20), review_state="DRAFT"), evidenced=False
    )

    assert [lim.code for lim in result.limitations] == []
    assert result.summary_code == "TRAVEL_RECORDS_CONSISTENT"


def test_a_trip_outside_the_window_is_still_asked_for_documents() -> None:
    """Coverage is **not** window-scoped, unlike the confidence detections.

    Those ask "can this distort a total?", which is a question about the qualifying
    window. This asks "has the user evidenced this trip?", which is a question about the
    trip — it is still in their travel history and still theirs to evidence, and hiding
    its coverage state would make the support column silently incomplete.
    """
    ancient = _trip(date(2015, 1, 1), date(2015, 1, 20))
    result = _consistency(ancient, evidenced=False)

    limitation = next(lim for lim in result.limitations if lim.code == "MISSING_TRAVEL_EVIDENCE")
    assert limitation.affected_input_ids == (str(ancient.travel_record_version_id),)


def test_a_more_serious_detection_wins_the_summary_code() -> None:
    """Precedence: an overlap is an inconsistency and unevidenced trips are not. The
    summary code is what the requirement card leads with, and leading with the weakest
    finding while records overlap would bury the thing that needs attention."""
    result = _consistency(
        _trip(date(2023, 1, 1), date(2023, 1, 20)),
        _trip(date(2023, 1, 10), date(2023, 1, 30)),
        evidenced=False,
    )

    assert result.conclusion == Conclusion.INCONSISTENT.value
    assert result.summary_code == "TRAVEL_RECORDS_OVERLAP"
    # ... and the coverage finding is still recorded, not dropped.
    assert "MISSING_TRAVEL_EVIDENCE" in [lim.code for lim in result.limitations]


def test_the_rule_links_every_evidence_link_it_read() -> None:
    """Provenance (directive 5, and the `new-rule` skill's step 6): a rule that declares
    `EVIDENCE_SUPPORT` must record the links it read, including those on trips it did not
    flag. Provenance describes what was read, not what turned out to matter."""
    from app.requirements.evaluation import LinkInputKind

    covered = _trip(date(2023, 1, 1), date(2023, 1, 20))
    bare = _trip(date(2024, 3, 1), date(2024, 3, 10))
    link = EvidenceLinkInput(link_id=uuid.uuid4(), travel_record_id=covered.travel_record_id)

    inputs = ResidenceAssessmentInputs(
        application_date=_APP,
        application_date_version_id=uuid.uuid4(),
        trips=(covered, bare),
        evidence_links=(link,),
    )
    result = {r.requirement_key: r for r in evaluate_residence_requirements(inputs)}[
        KEY_TRAVEL_CONSISTENCY
    ]

    evidence_links = [
        spec for spec in result.input_links if spec.input_kind == LinkInputKind.EVIDENCE_LINK
    ]
    assert [spec.input_version_id for spec in evidence_links] == [link.link_id]


def test_evaluating_twice_over_the_same_inputs_gives_the_same_answer() -> None:
    """Determinism, with evidence in the mix. The links arrive in a stable order from the
    repository precisely so the provenance rows do not shuffle between runs — two
    assessments over identical inputs must be byte-identical, or comparing them shows a
    diff where nothing changed."""
    trips = (_trip(date(2023, 1, 1), date(2023, 1, 20)), _trip(date(2024, 3, 1), date(2024, 3, 10)))
    links = tuple(
        EvidenceLinkInput(link_id=uuid.uuid4(), travel_record_id=t.travel_record_id) for t in trips
    )

    # Hoisted: minting a fresh one per run made the *application date* link differ and
    # the test fail for a reason that had nothing to do with determinism.
    date_version = uuid.uuid4()

    def run() -> EvaluatedResult:
        inputs = ResidenceAssessmentInputs(
            application_date=_APP,
            application_date_version_id=date_version,
            trips=trips,
            evidence_links=links,
        )
        return {r.requirement_key: r for r in evaluate_residence_requirements(inputs)}[
            KEY_TRAVEL_CONSISTENCY
        ]

    first, second = run(), run()
    assert first.summary_code == second.summary_code
    assert first.limitations == second.limitations
    assert [s.input_version_id for s in first.input_links] == [
        s.input_version_id for s in second.input_links
    ]


# --- duplicate records (§7.8, slice 4b) ---------------------------------------------


def _duplicate_ids(result: EvaluatedResult) -> tuple[str, ...]:
    limitation = next(
        (lim for lim in result.limitations if lim.code == "DUPLICATE_TRAVEL_RECORD"), None
    )
    return limitation.affected_input_ids if limitation else ()


def test_two_identical_trips_are_reported_as_duplicates() -> None:
    a = _trip(date(2024, 6, 5), date(2024, 7, 15), country="GR")
    b = _trip(date(2024, 6, 5), date(2024, 7, 15), country="GR")

    result = _consistency(a, b)

    assert set(_duplicate_ids(result)) == {
        str(a.travel_record_version_id),
        str(b.travel_record_version_id),
    }


def test_the_duplicate_detection_does_not_move_the_conclusion() -> None:
    """§7.8: the detection adds a limitation and does not touch the banding.

    Two identical week-long trips do overlap — their absent-date sets are the same set,
    which intersects itself — so the conclusion is still INCONSISTENT and the summary code
    is still the overlap one. What changes is the *limitation*: the pair's overlap is fully
    explained by their being duplicates, so `OVERLAPPING_TRAVEL` does not name them and the
    queue gets one item per record rather than two.
    """
    result = _consistency(
        _trip(date(2024, 6, 5), date(2024, 7, 15), country="GR"),
        _trip(date(2024, 6, 5), date(2024, 7, 15), country="GR"),
    )

    assert result.conclusion == Conclusion.INCONSISTENT.value
    assert result.summary_code == "TRAVEL_RECORDS_OVERLAP"
    codes = {lim.code for lim in result.limitations}
    assert "DUPLICATE_TRAVEL_RECORD" in codes
    assert "OVERLAPPING_TRAVEL" not in codes


def test_an_overlap_between_two_duplicate_pairs_is_still_reported() -> None:
    """The defect both reviews found, and the reason the exclusion moved into the rule.

    Greece twice and Italy twice, where a Greece trip overlaps an Italy trip. Every record
    is somebody's duplicate, so subtracting the duplicated *records* wholesale — which is
    what the derivation used to do — left zero overlap items on an INCONSISTENT case whose
    every remaining item said "no figure changes either way" and was dismissible. The user
    could empty the queue of a case the rules call inconsistent.

    The Greece/Italy overlap survives removing both duplicates, so it is a real finding.
    """
    greece = [_trip(date(2024, 6, 5), date(2024, 7, 15), country="GR") for _ in range(2)]
    italy = [_trip(date(2024, 7, 1), date(2024, 8, 1), country="IT") for _ in range(2)]

    result = _consistency(*greece, *italy)

    overlap = next(lim for lim in result.limitations if lim.code == "OVERLAPPING_TRAVEL")
    assert set(overlap.affected_input_ids) == {
        str(t.travel_record_version_id) for t in [*greece, *italy]
    }
    duplicates = next(lim for lim in result.limitations if lim.code == "DUPLICATE_TRAVEL_RECORD")
    assert len(duplicates.affected_input_ids) == 4


def test_a_duplicate_that_also_overlaps_a_third_trip_reports_both() -> None:
    """One record, two genuine problems: it is a copy of one trip and overlaps another."""
    a = _trip(date(2024, 6, 5), date(2024, 7, 15), country="GR")
    b = _trip(date(2024, 6, 5), date(2024, 7, 15), country="GR")
    c = _trip(date(2024, 7, 1), date(2024, 8, 1), country="IT")

    result = _consistency(a, b, c)

    overlap = next(lim for lim in result.limitations if lim.code == "OVERLAPPING_TRAVEL")
    assert str(c.travel_record_version_id) in overlap.affected_input_ids
    assert str(a.travel_record_version_id) in overlap.affected_input_ids


# --- the destination relation, and its transitive closure ---------------------------


def test_a_coded_trip_matches_an_uncoded_one_with_the_same_label() -> None:
    """§7.8: the label is the fallback "when *either* does not" have a code.

    The likeliest duplicate in the product, and the one a per-trip canonical key missed:
    import a history (no codes) and re-enter a trip by hand (the form derives one).
    """
    result = _consistency(
        _trip(date(2024, 6, 5), date(2024, 7, 15), country="ES", label="Spain"),
        _trip(date(2024, 6, 5), date(2024, 7, 15), country=None, label="Spain"),
    )

    assert len(_duplicate_ids(result)) == 2


def test_the_grouping_closes_transitively() -> None:
    """`_same_place` is not transitive on its own: A(ES,"Spain") matches B(None,"Spain") by
    label and C(ES,"España") by code, while B and C match by neither. Closing the relation
    is what makes "a group of duplicates" well-defined — if A is the same trip as B and as
    C, all three are one trip."""
    a = _trip(date(2024, 6, 5), date(2024, 7, 15), country="ES", label="Spain")
    b = _trip(date(2024, 6, 5), date(2024, 7, 15), country=None, label="Spain")
    c = _trip(date(2024, 6, 5), date(2024, 7, 15), country="ES", label="España")

    assert len(_duplicate_ids(_consistency(a, b, c))) == 3


def test_identical_zero_day_trips_are_duplicates_that_never_overlapped() -> None:
    """The case the overlap detection cannot see at all.

    Depart *D*, return *D + 1* gives an empty absent-date set (§5.2, both endpoints
    excluded), and empty sets do not intersect. These trips have never overlapped, so their
    conclusion must stay exactly what the other detections gave it — banding them
    INCONSISTENT would downgrade a verdict on records that distort no figure.
    """
    result = _consistency(
        _trip(date(2024, 6, 5), date(2024, 6, 6), country="GR"),
        _trip(date(2024, 6, 5), date(2024, 6, 6), country="GR"),
    )

    assert result.conclusion == Conclusion.SUPPORTED.value
    codes = {lim.code for lim in result.limitations}
    assert "DUPLICATE_TRAVEL_RECORD" in codes
    assert "OVERLAPPING_TRAVEL" not in codes


def test_the_same_dates_to_a_different_place_are_not_duplicates() -> None:
    result = _consistency(
        _trip(date(2024, 6, 5), date(2024, 7, 15), country="GR"),
        _trip(date(2024, 6, 5), date(2024, 7, 15), country="FR"),
    )

    assert _duplicate_ids(result) == ()
    # They still overlap, which is the honest reading: the user cannot have been in two
    # countries at once, and that is a conflict rather than a duplicate.
    assert result.summary_code == "TRAVEL_RECORDS_OVERLAP"


def test_the_same_place_on_different_dates_is_not_a_duplicate() -> None:
    result = _consistency(
        _trip(date(2024, 6, 5), date(2024, 7, 15), country="GR"),
        _trip(date(2025, 6, 5), date(2025, 7, 15), country="GR"),
    )

    assert _duplicate_ids(result) == ()


def test_destination_matching_prefers_the_country_code() -> None:
    """ "Spain" and "España" are one country, and the product already knows it — the code is
    derived from the label at entry."""
    result = _consistency(
        _trip(date(2024, 6, 5), date(2024, 7, 15), country="ES", label="Spain"),
        _trip(date(2024, 6, 5), date(2024, 7, 15), country="ES", label="España"),
    )

    assert len(_duplicate_ids(result)) == 2


def test_destination_matching_falls_back_to_the_normalised_label() -> None:
    """Free-text destinations have no country code, and they are exactly the entries a slip
    is most likely to duplicate. Comparing codes alone would never detect these."""
    result = _consistency(
        _trip(date(2024, 6, 5), date(2024, 7, 15), label="Mum's house"),
        _trip(date(2024, 6, 5), date(2024, 7, 15), label="  mum's HOUSE "),
    )

    assert len(_duplicate_ids(result)) == 2


def test_two_different_unmapped_places_are_not_duplicates() -> None:
    result = _consistency(
        _trip(date(2024, 6, 5), date(2024, 7, 15), label="Conference"),
        _trip(date(2024, 6, 5), date(2024, 7, 15), label="Mum's house"),
    )

    assert _duplicate_ids(result) == ()


def test_an_unmapped_label_cannot_collide_with_a_country_code() -> None:
    """The two comparison spaces are prefixed apart. Without that, a free-text destination
    that happens to read like an ISO code would match a real one."""
    result = _consistency(
        _trip(date(2024, 6, 5), date(2024, 7, 15), country="GR"),
        _trip(date(2024, 6, 5), date(2024, 7, 15), label="GR"),
    )

    assert _duplicate_ids(result) == ()


def test_three_identical_trips_all_name_each_other() -> None:
    trips = [_trip(date(2024, 6, 5), date(2024, 7, 15), country="GR") for _ in range(3)]

    result = _consistency(*trips)

    assert len(_duplicate_ids(result)) == 3


def test_the_duplicate_limitation_is_ordered_deterministically() -> None:
    """Sorted, like the other multi-record limitations: two runs over the same inputs must
    produce byte-identical output, or comparing assessments shows a diff where nothing
    changed."""
    trips = [_trip(date(2024, 6, 5), date(2024, 7, 15), country="GR") for _ in range(3)]

    first = _duplicate_ids(_consistency(*trips))
    second = _duplicate_ids(_consistency(*trips))

    assert first == second == tuple(sorted(first))
