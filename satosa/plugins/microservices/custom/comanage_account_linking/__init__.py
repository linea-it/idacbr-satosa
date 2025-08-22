"""
COmanage Account Linking Microservice
This module provides a microservice for managing account linking in COmanage,
specifically handling group associations between identity providers and COmanage.
It includes functionality for processing authentication requests, linking user accounts,
and synchronizing group memberships across different identity providers and COmanage.
"""

import logging
from typing import Any, Dict, List, NoReturn

from satosa.context import Context
from satosa.exception import SATOSAAuthenticationError
from satosa.micro_services.base import ResponseMicroService

from .api import COmanageAPI
from .config import COmanageConfig
from .exceptions import (
    COmanageAPIError,
    COmanageGroupsError,
    COmanageUserNotActiveError,
)
from .groups import COmanageGroups
from .user import COmanageUser, UserAttributes
from .utils import get_backend_config

# from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class COmanageAccountLinkingMicroService(ResponseMicroService):
    """
    A microservice for handling account linking in COmanage, specifically managing
    group associations between identity providers and COmanage.

    This service processes authentication requests, links user accounts, and
    synchronizes group memberships across different identity providers and COmanage.
    It supports multiple target backends and handles group registration, addition,
    and removal based on user attributes.

    Attributes:
        api (COmanageAPI): API interface for COmanage interactions
        target_backends (List[Dict]): Configured backends for account linking
        backend (str): Current target backend being processed
    """

    def __init__(self, conf: Dict[str, Any], *args: Any, **kwargs: Any) -> NoReturn:
        """
        Initialize the COmanageAccountLinkingMicroService with configuration settings.

        Args:
            conf (Dict[str, Any]): Configuration dictionary containing COmanage API settings.
            *args (Any): Variable positional arguments to pass to the parent class constructor.
            **kwargs (Any): Variable keyword arguments to pass to the parent class constructor.

        Sets up the COmanage API connection and configures target backends for account linking.
        Initializes the backend attribute to None, which will be set during processing.
        """
        super().__init__(*args, **kwargs)
        self.api = COmanageAPI(COmanageConfig(**conf))
        self.target_backends = conf.get("target_backends", [])
        self.backend = None
        self.group_prefix = ""

    def process(self, context: Context, data) -> Dict[str, Any]:
        """
        Process an authentication request for COmanage account linking.

        Handles account linking for a specific backend by extracting user identifier,
        creating a COmanage user, and synchronizing group memberships. Supports
        redirecting to a registration page or handling account linking errors.

        Args:
            context (Context): The authentication request context.
            data (Dict[str, Any]): Authentication data containing user attributes.

        Returns:
            Dict[str, Any]: Processed authentication response or error handling result.

        Raises:
            AssertionError: If user identifier cannot be extracted.
            COmanageAccountLinkingError: If group synchronization fails.
        """
        logger.debug("Processing request with context: %s", context)

        self.backend = context.target_backend

        data.attributes["idpName"] = self.backend

        logger.debug("Processing data: %s", data)

        user = UserAttributes.from_data(data)

        if not self.backend in [item["name"] for item in self.target_backends]:
            logger.info("Backend %s not in target backends", self.backend)
            data.attributes.update(user.co_manage_user)
            return super().process(context, data)

        self.group_prefix = get_backend_config(
            self.backend, self.target_backends, "prefix", self.backend
        )

        try:
            comanage_user = COmanageUser(user.edu_person_unique_id, self.api)
            logger.info("COmanage user: %s", comanage_user)
        except AssertionError as err:
            logger.warning(err)
            data.attributes.update(user.co_manage_user)
            return super().process(context, data)
        except COmanageAPIError as err:
            logger.warning(err)
            data.attributes.update(user.co_manage_user)
            return super().process(context, data)
        except COmanageUserNotActiveError as err:
            logger.error(err)
            return SATOSAAuthenticationError(context.state, err)

        user.co_manage_user["COmanageUID"] = comanage_user.uid
        user.co_manage_user["COmanageUserStatus"] = comanage_user.status

        if comanage_user.is_active:
            if user.is_member_of:
                try:
                    self.register_groups(
                        idp_groups=user.is_member_of, comanage_user=comanage_user
                    )
                except COmanageGroupsError as err:
                    logger.error(err)

            cogroups = comanage_user.get_groups()
            user.co_manage_user["COmanageGroups"] = list(cogroups.keys())

        data.attributes.update(user.co_manage_user)
        return super().process(context, data)

    def register_groups(
        self, idp_groups: List[str], comanage_user: COmanageUser
    ) -> Dict[str, Any]:
        """
        Synchronize groups for a COmanage user across an identity provider and COmanage.

        This method handles group membership by creating or retrieving groups associated
        with the backend, adding new groups to the user, and removing groups no longer
        present in the identity provider's group list.

        Args:
            idp_groups (List[str]): Groups from the identity provider.
            comanage_user (COmanageUser): The COmanage user being processed.

        Returns:
            Dict[str, Any]: Dictionary containing the user's group memberships.
        """
        comanage_groups = COmanageGroups(self.api, self.group_prefix)

        idp_groups_user = {}

        for group in idp_groups:
            idp_group_name = f"{self.group_prefix}_{group}"
            idp_group = comanage_groups.get_or_create_group(idp_group_name)

            logger.debug(
                "Group %s: %s - %s",
                idp_group_name,
                idp_group["Id"],
                idp_group["Method"],
            )

            idp_groups_user[idp_group_name] = {
                "Id": idp_group["Id"],
                "Method": idp_group["Method"],
            }

        logger.info("--> IDP user groups with prefix: %s", idp_groups_user)

        com_group_members_user = comanage_groups.organize_group_members(
            comanage_user.get_group_members()
        )

        logger.info("--> COMANAGER group members by user: %s", com_group_members_user)

        com_groups_user = comanage_user.get_idp_groups(self.group_prefix)

        logger.info("--> COMANAGER group by user: %s", com_groups_user)

        for idp_group, _data in com_groups_user.items():
            if idp_group not in idp_groups_user:
                logger.debug("Group %s not found in idp groups", idp_group)
                logger.debug("Removing group %s from user", idp_group)
                group_member_id = com_group_members_user[_data["Id"]]
                comanage_groups.remove_member(group_member_id)

        for group_name, _data in idp_groups_user.items():
            if group_name not in com_groups_user:
                logger.debug("Group %s not found in comanage groups", group_name)
                logger.debug("Adding group %s to user", group_name)
                comanage_groups.set_member(_data["Id"], comanage_user.co_person_id)

        return idp_groups_user


if __name__ == "__main__":
    import argparse
    from dataclasses import dataclass

    import yaml

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="""Test COmanage Account Linking microservice functionality.

        This script provides a command-line interface to test the COmanageAccountLinkingMicroService
        by simulating a user authentication and group membership process. It allows manual testing
        of account linking with configurable parameters.

        Requires:
            - YAML configuration file
            - eduPersonUniqueId
            - Space-separated list of group memberships"""
    )
    parser.add_argument(
        "--config", type=str, required=True, help="Path to YAML config file"
    )
    parser.add_argument(
        "--edu-person-unique-id",
        type=str,
        required=True,
        help="eduPersonUniqueId value",
    )
    parser.add_argument(
        "--is-member-of",
        type=str,
        required=True,
        help="Space-separated list of group memberships",
    )
    _args = parser.parse_args()

    with open(_args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        config = config["config"]

    # Setup mock data with command line arguments
    @dataclass
    class Data:
        """Mock data"""

        attributes: Dict[str, List[str]]

    _data = Data(
        attributes={
            "eduPersonUniqueId": [_args.edu_person_unique_id],
            "isMemberOf": [_args.is_member_of],
        }
    )

    # Mock context
    _context = Context()
    _context.target_backend = "rubin_oidc"

    # Define a mock next callback
    def mock_next(_context, internal_data):
        """Mock next callback function"""
        return {"success": True, "data": internal_data}

    # Initialize the service
    service = COmanageAccountLinkingMicroService(
        config,
        name="comanage_account_linking",
        base_url=config.get("api_url"),
    )

    # Assign the mock_next callback as an attribute for testing purposes
    setattr(service, "next", mock_next)

    # Test the process method
    result = service.process(_context, _data)
    print(f"Result: {result}")
