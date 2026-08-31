"""Unit tests for COmanage POSIX group association provisioning."""

from unittest.mock import call

import pytest

import comanage_account_linking as comanage_module
from comanage_account_linking.api import COmanageAPI
from comanage_account_linking.config import COmanageConfig
from comanage_account_linking.exceptions import COmanageAPIError, COmanageGroupsError
from comanage_account_linking.groups import COmanageGroups


@pytest.fixture
def api_config():
    """Return an API configuration that never contacts a real COmanage."""
    return COmanageConfig(
        api_url="https://registry.example.org/",
        api_user="test-api-user",
        password="test-api-key",
        co_id="2",
        target_backends=[],
    )


def test_get_unix_cluster_groups_uses_plugin_endpoint(mocker, api_config):
    """The GET must use the plugin endpoint and its snake-case API filter."""
    api = COmanageAPI(api_config)
    get_request = mocker.patch.object(
        api,
        "get_request",
        return_value={"UnixClusterGroups": [{"CoGroupId": "123"}]},
    )

    result = api.get_unix_cluster_groups(7)

    assert result == [{"CoGroupId": "123"}]
    get_request.assert_called_once_with(
        "registry/unix_cluster/unix_cluster_groups.json",
        {"unix_cluster_id": 7},
    )


def test_add_unix_cluster_group_uses_expected_payload(mocker, api_config):
    """The POST must use the UnixCluster plugin ID and CO Group ID."""
    api = COmanageAPI(api_config)
    post_request = mocker.patch.object(
        api, "post_request", return_value={"Id": "55"}
    )

    result = api.add_unix_cluster_group(7, 123)

    assert result == {"Id": "55"}
    post_request.assert_called_once_with(
        "registry/unix_cluster/unix_cluster_groups.json",
        {
            "Version": "1.0",
            "UnixClusterId": 7,
            "CoGroupId": 123,
        },
    )


def build_group_manager(mocker, associations=None):
    """Build a COmanageGroups instance backed by a mocked API."""
    api = mocker.Mock(spec=COmanageAPI)
    api.get_groups_by_co.return_value = []
    api.get_unix_cluster_groups.return_value = associations or []
    api.add_unix_cluster_group.return_value = {"Id": "55"}
    return COmanageGroups(api, unix_cluster_id=7), api


def test_existing_unix_cluster_group_is_not_created_again(mocker):
    """An existing association makes ensure a read-only operation."""
    groups, api = build_group_manager(
        mocker,
        associations=[{"CoGroupId": "123", "Deleted": False}],
    )

    assert groups.ensure_unix_cluster_group(123) is False
    api.add_unix_cluster_group.assert_not_called()


def test_missing_unix_cluster_group_is_created_once(mocker):
    """A missing association is created and cached for the current request."""
    groups, api = build_group_manager(mocker)

    assert groups.ensure_unix_cluster_group(123) is True
    assert groups.ensure_unix_cluster_group(123) is False
    api.add_unix_cluster_group.assert_called_once_with(7, 123)


def test_concurrent_creation_is_accepted_only_after_confirmation(mocker):
    """A duplicate POST is safe only if a reread finds the association."""
    api = mocker.Mock(spec=COmanageAPI)
    api.get_groups_by_co.return_value = []
    api.get_unix_cluster_groups.side_effect = [
        [],
        [{"CoGroupId": "123", "Deleted": False}],
    ]
    api.add_unix_cluster_group.side_effect = COmanageAPIError(
        "association already exists", status_code=400
    )
    groups = COmanageGroups(api, unix_cluster_id=7)

    assert groups.ensure_unix_cluster_group(123) is False
    assert api.get_unix_cluster_groups.call_count == 2


def test_unconfirmed_creation_error_is_propagated(mocker):
    """An API failure must stop provisioning when no association exists."""
    api = mocker.Mock(spec=COmanageAPI)
    api.get_groups_by_co.return_value = []
    api.get_unix_cluster_groups.side_effect = [[], []]
    api.add_unix_cluster_group.side_effect = COmanageAPIError(
        "invalid Unix Cluster", status_code=400
    )
    groups = COmanageGroups(api, unix_cluster_id=7)

    with pytest.raises(COmanageAPIError, match="invalid Unix Cluster"):
        groups.ensure_unix_cluster_group(123)


def test_association_is_created_before_group_membership(mocker):
    """The queue-triggering membership change must be the last write."""
    service = object.__new__(
        comanage_module.COmanageAccountLinkingMicroService
    )
    service.api = mocker.Mock(spec=COmanageAPI)

    groups = mocker.Mock(spec=COmanageGroups)
    groups.get_or_create_group.return_value = {
        "Id": "123",
        "Method": "CREATED",
    }
    groups.ensure_unix_cluster_group.return_value = True
    groups.organize_group_members.return_value = {}

    mocked_groups_class = mocker.patch.object(
        comanage_module, "COmanageGroups", return_value=groups
    )
    mocker.patch.object(comanage_module, "sleep")

    comanage_user = mocker.Mock()
    comanage_user.uid = "test-user"
    comanage_user.co_person_id = 1877
    comanage_user.get_group_members.return_value = []
    comanage_user.get_groups_by_prefix.return_value = {}

    service.register_groups(
        is_member_of=["science-platform"],
        comanage_user=comanage_user,
        group_prefix="lsst",
        unix_cluster_id="7",
    )

    mocked_groups_class.assert_called_once_with(service.api, 7)
    assert groups.method_calls == [
        call.get_or_create_group("lsst_science-platform"),
        call.ensure_unix_cluster_group("123"),
        call.organize_group_members([]),
        call.set_member("123", 1877),
    ]


def test_association_failure_prevents_membership_change(mocker):
    """Incomplete POSIX data must never trigger a membership queue event."""
    service = object.__new__(
        comanage_module.COmanageAccountLinkingMicroService
    )
    service.api = mocker.Mock(spec=COmanageAPI)

    groups = mocker.Mock(spec=COmanageGroups)
    groups.get_or_create_group.return_value = {
        "Id": "123",
        "Method": "CREATED",
    }
    groups.ensure_unix_cluster_group.side_effect = COmanageAPIError(
        "unable to associate group", status_code=500
    )
    mocker.patch.object(comanage_module, "COmanageGroups", return_value=groups)
    mocker.patch.object(comanage_module, "sleep")

    comanage_user = mocker.Mock()
    comanage_user.co_person_id = 1877

    with pytest.raises(COmanageAPIError, match="unable to associate group"):
        service.register_groups(
            is_member_of=["science-platform"],
            comanage_user=comanage_user,
            group_prefix="lsst",
            unix_cluster_id=7,
        )

    groups.set_member.assert_not_called()


@pytest.mark.parametrize("unix_cluster_id", [None, "", "not-an-id", 0, -1])
def test_invalid_unix_cluster_id_fails_explicitly(mocker, unix_cluster_id):
    """Bad configuration must fail before making any COmanage API call."""
    service = object.__new__(
        comanage_module.COmanageAccountLinkingMicroService
    )
    service.api = mocker.Mock(spec=COmanageAPI)
    groups_class = mocker.patch.object(comanage_module, "COmanageGroups")

    with pytest.raises(COmanageGroupsError, match="unix_cluster_id"):
        service.register_groups(
            is_member_of=["science-platform"],
            comanage_user=mocker.Mock(),
            group_prefix="lsst",
            unix_cluster_id=unix_cluster_id,
        )

    groups_class.assert_not_called()
