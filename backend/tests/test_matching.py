from matching import (
    adaptive_raw_score,
    apply_category_multiplier,
    compare_serials,
    compute_match,
    location_boost,
    score_tier,
    time_boost,
)


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


def test_adaptive_score_full_signals():
    score = adaptive_raw_score(0.80, 0.90, 0.70)
    assert approx(score, 0.90 * 0.60 + 0.80 * 0.25 + 0.70 * 0.15)


def test_adaptive_score_image_and_text_only():
    score = adaptive_raw_score(0.80, 0.90, None)
    assert approx(score, 0.90 * 0.75 + 0.80 * 0.25)


def test_adaptive_score_image_only_with_found_text():
    score = adaptive_raw_score(None, 0.88, 0.60)
    assert approx(score, 0.88 * 0.85 + 0.60 * 0.15)


def test_adaptive_score_text_only():
    assert approx(adaptive_raw_score(0.77, None, None), 0.77)


def test_category_multiplier_and_cap():
    assert approx(apply_category_multiplier(0.80, True), 0.88)
    assert approx(apply_category_multiplier(0.80, False), 0.60)
    assert approx(apply_category_multiplier(0.95, True), 0.99)


def test_tiers():
    assert score_tier(0.90) == "strong"
    assert score_tier(0.75) == "possible"
    assert score_tier(0.60) == "weak"
    assert score_tier(0.50) is None


def test_location_and_time_boosts():
    assert location_boost("Library", "Library") == 0.06
    assert location_boost("Library | Room 401", "Room 401") == 0.06
    assert location_boost("Library | Room 401", "Faculty") == 0.0
    assert location_boost("Library", "Library", apply_boost=False) == 0.0
    assert location_boost("Main Library Floor 2", "Main Library, Floor 2") > 0
    assert location_boost("Engineering Building", "Student Canteen") == 0.0
    assert time_boost("2026-06-11", "2026-06-11") == 0.03
    assert time_boost("2026-06-11", "2026-06-13") == 0.02
    assert time_boost("June 11, 2026", "2026-06-11") == 0.03


def test_compute_match_location_boost_raises_score():
    base, _, _, _ = compute_match(
        text_to_image=0.70,
        image_to_image=None,
        found_text_to_lost_image=None,
        lost_category="Gadgets",
        found_category="Gadgets",
        lost_location="Library",
        found_location="Faculty",
    )
    boosted, _, _, _ = compute_match(
        text_to_image=0.70,
        image_to_image=None,
        found_text_to_lost_image=None,
        lost_category="Gadgets",
        found_category="Gadgets",
        lost_location="Library | Faculty",
        found_location="Faculty",
    )
    assert boosted > base
    bypassed, _, _, _ = compute_match(
        text_to_image=0.70,
        image_to_image=None,
        found_text_to_lost_image=None,
        lost_category="Gadgets",
        found_category="Gadgets",
        lost_location="Library | Faculty",
        found_location="Faculty",
        apply_location_boost=False,
    )
    assert approx(bypassed, base)


def test_compute_match_discards_weak_cross_category():
    score, tier, same, breakdown = compute_match(
        text_to_image=0.70,
        image_to_image=None,
        found_text_to_lost_image=None,
        lost_category="Gadgets",
        found_category="Electronics",
    )
    assert same is False
    assert approx(score, 0.70 * 0.75)
    assert tier is None
    assert "text_to_image" in breakdown
    assert breakdown["image_to_image"] is None


def test_compare_serials_statuses():
    assert compare_serials(None, None) == "missing"
    assert compare_serials("", "") == "missing"
    assert compare_serials("ABC123", None) == "one_sided"
    assert compare_serials(None, "ABC123") == "one_sided"
    assert compare_serials("abc-123", "ABC123") == "match"
    assert compare_serials("IMEI 356938035643809", "356938035643809") == "match"
    assert compare_serials("SN12345678", "5678") == "partial"
    assert compare_serials("ABCDEFGH", "XXXXEFGH") == "partial"
    assert compare_serials("PHONE-1111", "PHONE-2222") == "mismatch"


def test_compare_serials_does_not_imply_clip_match():
    # serial equality is a desk flag only — compute_match is independent
    score, tier, *_ = compute_match(
        text_to_image=0.40,
        image_to_image=0.40,
        found_text_to_lost_image=None,
        lost_category="Gadgets",
        found_category="Clothing",
    )
    assert compare_serials("SAMEIMEI", "SAMEIMEI") == "match"
    assert tier is None
    assert score < 0.55


def test_compute_match_keeps_possible_same_category():
    score, tier, same, breakdown = compute_match(
        text_to_image=0.70,
        image_to_image=None,
        found_text_to_lost_image=None,
        lost_category="Gadgets",
        found_category="Gadgets",
    )
    assert same is True
    assert approx(score, min(0.70 * 1.10, 0.99))
    assert tier == "possible"
    assert approx(breakdown["text_to_image"], 0.70)


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} tests passed")
