# -*- coding: utf-8 -*-
# This file is part of the SATOSA project.

from unittest.mock import MagicMock, patch

import pytest
from comanage_account_linking import COmanageAccountLinkingMicroService
from comanage_account_linking.exceptions import (
    COmanageAPIError,
    COmanageGroupsError,
    COmanageUserNotActiveError,
)
from satosa.context import Context
from satosa.exception import SATOSAAuthenticationError


@pytest.fixture
def mock_comanage_api():
    """Fixture for mocking COmanageAPI."""
    with patch("comanage_account_linking.COmanageAPI") as mock_api:
        yield mock_api


@pytest.fixture
def mock_comanage_user():
    """Fixture for mocking COmanageUser."""
    with patch("comanage_account_linking.COmanageUser") as mock_user:
        instance = mock_user.return_value
        instance.is_active = True
        instance.uid = "test_uid"
        instance.status = "Active"
        instance.co_person_id = "123"
        instance.get_groups.return_value = {"group1": {}, "group2": {}}
        instance.get_idp_groups.return_value = {"prefix_group1": {}}
        instance.get_group_members.return_value = {}
        yield mock_user


# @pytest.fixture
# def mock_comanage_groups():
#     """Fixture for mocking COmanageGroups."""
#     with patch(
#         "satosa.plugins.microservices.custom.comanage_account_linking.COmanageGroups"
#     ) as mock_groups:
#         instance = mock_groups.return_value
#         instance.get_or_create_group.side_effect = lambda name: {
#             "Id": name,
#             "Method": "Created",
#         }
#         instance.organize_group_members.return_value = {}
#         yield mock_groups


# @pytest.fixture
# def mock_user_attributes():
#     """Fixture for mocking UserAttributes."""
#     with patch(
#         "satosa.plugins.microservices.custom.comanage_account_linking.UserAttributes"
#     ) as mock_attributes:
#         instance = mock_attributes.from_data.return_value
#         instance.edu_person_unique_id = "test_user"
#         instance.is_member_of = ["group1", "group2"]
#         instance.co_manage_user = {}
#         yield mock_attributes


# @pytest.fixture
# def microservice(mock_comanage_api):
#     """Fixture for initializing the microservice."""
#     config = {
#         "api_url": "https://comanage.test",
#         "co_id": 1,
#         "api_user": "test_user",
#         "api_pass": "test_pass",
#         "target_backends": [{"name": "test_backend", "prefix": "prefix"}],
#     }
#     service = COmanageAccountLinkingMicroService(
#         config, name="test_service", base_url="https://satosa.test"
#     )
#     return service


# def test_init(microservice, mock_comanage_api):
#     """Test service initialization."""
#     assert microservice.api is not None
#     mock_comanage_api.assert_called_once()
#     assert microservice.target_backends == [
#         {"name": "test_backend", "prefix": "prefix"}
#     ]


# def test_process_backend_not_in_target(microservice, mock_user_attributes):
#     """Test process when backend is not in target backends."""
#     context = Context()
#     context.target_backend = "another_backend"
#     data = MagicMock()
#     data.attributes = {}

#     with patch.object(COmanageAccountLinkingMicroService, "next") as mock_next:
#         microservice.process(context, data)
#         mock_next.assert_called_once()


# def test_process_user_not_found(microservice, mock_user_attributes, mock_comanage_user):
#     """Test process when user is not found in COmanage."""
#     mock_comanage_user.side_effect = COmanageAPIError("User not found")
#     context = Context()
#     context.target_backend = "test_backend"
#     data = MagicMock()
#     data.attributes = {}

#     with patch.object(COmanageAccountLinkingMicroService, "next") as mock_next:
#         microservice.process(context, data)
#         mock_next.assert_called_once()


# def test_process_user_not_active(
#     microservice, mock_user_attributes, mock_comanage_user
# ):
#     """Test process when user is not active in COmanage."""
#     mock_comanage_user.side_effect = COmanageUserNotActiveError("User not active")
#     context = Context()
#     context.target_backend = "test_backend"
#     data = MagicMock()
#     data.attributes = {}

#     result = microservice.process(context, data)
#     assert isinstance(result, SATOSAAuthenticationError)


# def test_process_success(
#     microservice, mock_user_attributes, mock_comanage_user, mock_comanage_groups
# ):
#     """Test successful processing of a user."""
#     context = Context()
#     context.target_backend = "test_backend"
#     data = MagicMock()
#     data.attributes = {"isMemberOf": ["group1"]}

#     with patch.object(COmanageAccountLinkingMicroService, "next") as mock_next:
#         microservice.process(context, data)
#         mock_next.assert_called_once()
#         assert "COmanageUID" in data.attributes
#         assert "COmanageUserStatus" in data.attributes
#         assert "COmanageGroups" in data.attributes


# def test_register_groups(microservice, mock_comanage_user, mock_comanage_groups):
#     """Test group registration."""
#     microservice.backend = "test_backend"
#     microservice.group_prefix = "prefix"
#     comanage_user = mock_comanage_user.return_value

#     microservice.register_groups(["group1", "group3"], comanage_user)

#     mock_groups_instance = mock_comanage_groups.return_value
#     mock_groups_instance.set_member.assert_called_with(
#         "prefix_group3", comanage_user.co_person_id
#     )
#     mock_groups_instance.remove_member.assert_not_called()


# def test_register_groups_with_removal(
#     microservice, mock_comanage_user, mock_comanage_groups
# ):
#     """Test group registration with removal of old groups."""
#     microservice.backend = "test_backend"
#     microservice.group_prefix = "prefix"
#     comanage_user = mock_comanage_user.return_value
#     comanage_user.get_idp_groups.return_value = {
#         "prefix_group1": {"Id": "g1"},
#         "prefix_group2": {"Id": "g2"},
#     }

#     mock_groups_instance = mock_comanage_groups.return_value
#     mock_groups_instance.organize_group_members.return_value = {
#         "g1": "gm1",
#         "g2": "gm2",
#     }

#     microservice.register_groups(["group1"], comanage_user)

#     mock_groups_instance.remove_member.assert_called_once_with("gm2")
#     mock_groups_instance.set_member.assert_not_called()


# def test_register_groups_error(microservice, mock_comanage_user, mock_comanage_groups):
#     """Test error handling in group registration."""
#     mock_comanage_groups.return_value.get_or_create_group.side_effect = (
#         COmanageGroupsError("Group error")
#     )
#     microservice.backend = "test_backend"
#     microservice.group_prefix = "prefix"
#     comanage_user = mock_comanage_user.return_value

#     with pytest.raises(COmanageGroupsError):
#         microservice.register_groups(["group1"], comanage_user)
