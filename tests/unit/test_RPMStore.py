#!/usr/bin/env python

import pytest

from repoman.common.stores.RPM.RPM import RPMVersion


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
def rpm_version_lt_tuple(request):
    """Fixture tuple of RPMVersion when a first is less then a second."""
    yield tuple(RPMVersion(ver) for ver in request.param)


class TestRPMVersion:
    """Tests for RPMVersion."""

    def test_comparison_lt(self, rpm_version_lt_tuple):
        """Test case when one RPM version is less then another."""
        assert rpm_version_lt_tuple[0] < rpm_version_lt_tuple[1]

    def test_comparison_gt(self, rpm_version_lt_tuple):
        """Test case when one RPM version is bigger then another."""
        assert rpm_version_lt_tuple[1] > rpm_version_lt_tuple[0]
