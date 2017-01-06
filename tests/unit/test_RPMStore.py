#!/usr/bin/env python

import pytest

from repoman.common.stores.RPM.RPM import RPMVersion


def _create_rpm_versions_tuple(strings_tuple):
    """Return tuple of RPMVersion object from tuple of strings."""
    return tuple(RPMVersion(ver) for ver in strings_tuple)


@pytest.fixture(params=[
    ('0.0-1.el7.centos', '0.1-1.el7.centos'),
    ('0.1-1.el7.centos', '1.0-1.el7.centos'),
    ('1.0-1.el7.centos', '1.0-1.20170103101841.centos'),
    ('1.0-1.20170103101841.centos', '1.0-1.20180103101841.centos'),
    ('1.0-1.20180103101841.centos', '1.0-1.20180103101841.git17e7bc0.el7.centos'),  # noqa
    ('1.0-1.20180103101841.git17e7bc0.el7.centos', '1.0-1.20190103101841.git17e7bc0.el7.centos'),  # noqa
    ('1.0-1.20190103101841.git17e7bc0.el7.centos', '1.1-1.20190103101841.git17e7bc0.el7.centos'),  # noqa
    ('1.1-1.20190103101841.git17e7bc0.el7.centos', '2.1-1.20190103101841.git17e7bc0.el7.centos'),  # noqa
])
def rpm_versions_lt_tuple(request):
    """Fixture tuple of RPMVersion when a first is less then a second."""
    yield _create_rpm_versions_tuple(request.param)


@pytest.fixture(params=[
    ('1.1-1.20190103101841.git17e7bc0.el7.centos', '1.1-1.20190103101841.git17e7bc0.el7.centos'),  # noqa
])
def rpm_versions_eq_tuple(request):
    """Fixture tuple of RPMVersion of the same version."""
    yield _create_rpm_versions_tuple(request.param)


class TestRPMVersion(object):
    """Tests for RPMVersion."""

    def test_comparison_lt(self, rpm_versions_lt_tuple):
        """Test case when one RPM version is less then another."""
        assert rpm_versions_lt_tuple[0] < rpm_versions_lt_tuple[1]

    def test_comparison_gt(self, rpm_versions_lt_tuple):
        """Test case when one RPM version is bigger then another."""
        assert rpm_versions_lt_tuple[1] > rpm_versions_lt_tuple[0]

    def test_comparion_ne(self, rpm_versions_lt_tuple):
        """Test case when one RPM version is not equal to another."""
        assert rpm_versions_lt_tuple[0] != rpm_versions_lt_tuple[1]

    def test_comparison_eq(self, rpm_versions_eq_tuple):
        """Test case when one RPM version is equal to another."""
        assert rpm_versions_eq_tuple[0] == rpm_versions_eq_tuple[1]

    def test_comparison_le(self, rpm_versions_lt_tuple, rpm_versions_eq_tuple):
        """Test case when one RPM version is less or equal to another."""
        assert rpm_versions_lt_tuple[0] <= rpm_versions_lt_tuple[1]

    def test_comparison_ge(self, rpm_versions_lt_tuple, rpm_versions_eq_tuple):
        """Test case when one RPM version is bigger or equal to another."""
        assert rpm_versions_lt_tuple[1] >= rpm_versions_lt_tuple[0]
