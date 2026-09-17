import pytest

from wos_cli import query
from wos_cli.errors import WosUsageError


def test_plain_query_wraps_in_ts():
    assert query.build_plain_query("molybdenum doped indium oxide") == (
        "TS=(molybdenum doped indium oxide)"
    )


def test_doi_query_wraps_in_do():
    assert query.build_doi_query("10.1038/s41586-020-2649-2") == (
        "DO=(10.1038/s41586-020-2649-2)"
    )


def test_empty_plain_query_rejected():
    with pytest.raises(WosUsageError):
        query.build_plain_query("   ")


def test_declared_tags_are_18_and_supported_17():
    assert len(query.DECLARED_TAGS) == 18
    assert len(query.SUPPORTED_TAGS) == 17
    assert query.DISABLED_TAGS == {"SUR"}
    assert query.UNSUPPORTED_TAGS == {"WC"}


@pytest.mark.parametrize("q", ["TS=(a) AND WC=(b)", "WC=(Computer Science)"])
def test_wc_rejected(q):
    with pytest.raises(WosUsageError) as exc:
        query.validate_raw_query(q)
    assert "WC" in str(exc.value)


def test_sur_rejected():
    with pytest.raises(WosUsageError) as exc:
        query.validate_raw_query("SUR=(repo)")
    assert "SUR" in str(exc.value)


def test_unknown_tag_rejected():
    with pytest.raises(WosUsageError):
        query.validate_raw_query("FOO=(bar)")


def test_valid_raw_query_passes():
    assert query.validate_raw_query("TS=(ITO AND ENZ) AND PY=(2022-2026)") == []


def test_raw_without_tag_warns():
    warnings = query.validate_raw_query("machine learning")
    assert warnings and "field tag" in warnings[0]


@pytest.mark.parametrize(
    "sort,order,expected",
    [("TC", "D", "TC+D"), ("RS", None, "RS+D"), ("PY", "A", "PY+A"), ("LD", "a", "LD+A")],
)
def test_sort_field_format(sort, order, expected):
    assert query.build_sort_field(sort, order) == expected


def test_sort_field_is_never_space_separated():
    # Regression: third-party code emitted "RS DESC" instead of "RS+D".
    value = query.build_sort_field("RS", "D")
    assert value == "RS+D"
    assert " " not in value and "DESC" not in value


def test_sort_field_none_when_unsorted():
    assert query.build_sort_field(None, "D") is None


@pytest.mark.parametrize("sort", ["date", "XX", "D"])
def test_invalid_sort_rejected(sort):
    with pytest.raises(WosUsageError):
        query.build_sort_field(sort, "D")


def test_empty_sort_means_unset():
    assert query.build_sort_field("", "D") is None


@pytest.mark.parametrize("order", ["desc", "Z", "DD"])
def test_invalid_order_rejected(order):
    with pytest.raises(WosUsageError):
        query.build_sort_field("TC", order)


@pytest.mark.parametrize("limit", [0, -1, 51, 100, 1000])
def test_limit_out_of_range_rejected(limit):
    with pytest.raises(WosUsageError):
        query.validate_limit(limit)


@pytest.mark.parametrize("limit", [1, 10, 50])
def test_limit_in_range_ok(limit):
    assert query.validate_limit(limit) == limit


def test_looks_like_advanced():
    assert query.looks_like_advanced("TS=(x)")
    assert not query.looks_like_advanced("machine learning")


def test_looks_like_doi():
    assert query.looks_like_doi("10.1038/s41586-020-2649-2")
    assert not query.looks_like_doi("doi:10.1038/x")


@pytest.mark.parametrize("value", ["0028-0836", "1476-4687", "00280836"])
def test_is_issn(value):
    assert query.is_issn(value)


def test_is_issn_false_for_journal_id():
    assert not query.is_issn("NATURE-2025")
