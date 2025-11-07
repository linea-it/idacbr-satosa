"""
COmanage Account Linking Microservice
This module provides a microservice for managing account linking in COmanage,
specifically handling group associations between identity providers and COmanage.
It includes functionality for processing authentication requests, linking user accounts,
and synchronizing group memberships across different identity providers and COmanage.
"""

import logging
from typing import Any, Dict, List, NoReturn
from time import sleep

from satosa.context import Context
from satosa.exception import SATOSAAuthenticationError
from satosa.micro_services.base import ResponseMicroService

from .api import COmanageAPI
from .config import COmanageConfig
from .exceptions import (
    COmanageUserNonLIneAError,
    COmanageUserNotActiveError,
)
from .groups import COmanageGroups
from .user import COmanageUser, UserAttributes
from .utils import get_backend_config


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

    def __init__(self, config: Dict[str, Any], *args: Any, **kwargs: Any) -> NoReturn:
        """
        Initialize the COmanageAccountLinkingMicroService with configuration settings.

        Args:
            config (Dict[str, Any]): Configuration dictionary containing COmanage API settings.
            *args (Any): Variable positional arguments to pass to the parent class constructor.
            **kwargs (Any): Variable keyword arguments to pass to the parent class constructor.

        Sets up the COmanage API connection and configures target backends for account linking.
        Initializes the backend attribute to None, which will be set during processing.
        """
        super().__init__(*args, **kwargs)
        self.api = COmanageAPI(COmanageConfig(**config))
        self.target_backends = config.get("target_backends", [])

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
        logger.debug("Processing request: %s", context)
        backend = context.target_backend
        data.attributes["backendName"] = backend
        user = UserAttributes.from_data(data)

        if not backend in [item["name"] for item in self.target_backends]:
            logger.info("Backend %s not in target backends", backend)
            data.attributes.update(user.co_manage_user)
            return super().process(context, data)

        group_prefix = get_backend_config(
            backend, self.target_backends, "prefix", backend
        )

        try:
            comanage_user = COmanageUser(user.edu_person_unique_id, self.api)
        except COmanageUserNotActiveError as err:
            logger.exception(err)
            return SATOSAAuthenticationError(context.state, err)
        except COmanageUserNonLIneAError as err:
            logger.exception(err)
            user.co_manage_user["COmanageLogError"] = str(err)
            user.co_manage_user["COmanageUserStatus"] = "NonLIneA"
            data.attributes.update(user.co_manage_user)
            return super().process(context, data)
        except Exception as err:  # pylint: disable=broad-except
            logger.exception(err)
            user.co_manage_user["COmanageLogError"] = str(err)
            user.co_manage_user["COmanageUserStatus"] = "Error"
            data.attributes.update(user.co_manage_user)
            return super().process(context, data)

        user.co_manage_user["COmanageUID"] = comanage_user.uid
        user.co_manage_user["COmanageUserStatus"] = comanage_user.status

        if comanage_user.is_active:
            if user.is_member_of:
                try:
                    self.register_groups(
                        is_member_of=user.is_member_of,
                        comanage_user=comanage_user,
                        group_prefix=group_prefix,
                    )
                except Exception as err:  # pylint: disable=broad-except
                    logger.exception(err)
                    user.co_manage_user["COmanageLogError"] = str(err)
                    user.co_manage_user["COmanageUserStatus"] = "Error"
                    data.attributes.update(user.co_manage_user)
                    return super().process(context, data)

            cogroups = comanage_user.get_groups()
            user.co_manage_user["COmanageGroups"] = list(cogroups.keys())

        data.attributes.update(user.co_manage_user)
        return super().process(context, data)

    def register_groups(
        self,
        is_member_of: List[str],
        comanage_user: COmanageUser,
        group_prefix: str = "",
    ) -> Dict[str, Any]:
        """
        Synchronize groups for a COmanage user across an identity provider and COmanage.

        This method handles group membership by creating or retrieving groups associated
        with the backend, adding new groups to the user, and removing groups no longer
        present in the identity provider's group list.

        Args:
            is_member_of (List[str]): Groups from the identity provider.
            comanage_user (COmanageUser): The COmanage user being processed.

        Returns:
            Dict[str, Any]: Dictionary containing the user's group memberships.
        """
        comanage_groups = COmanageGroups(self.api)

        groups_user = {}

        # Iterate over the identity provider groups and ensure they exist in COmanage
        for group in is_member_of:
            sleep(0.05)  # To avoid hitting the API rate limit
            group_name = f"{group_prefix}_{group}"
            group = comanage_groups.get_or_create_group(group_name)

            logger.debug(
                "Group %s: %s - %s",
                group_name,
                group["Id"],
                group["Method"],
            )

            groups_user[group_name] = {
                "Id": group["Id"],
                "Method": group["Method"],
            }

        logger.debug("User %s groups: %s", comanage_user.uid, groups_user)

        # Get the current group membership from COmanage
        group_members = comanage_groups.organize_group_members(
            comanage_user.get_group_members()
        )

        # Get the groups associated with the user that match the identity provider prefix
        cmn_groups_with_prefix = comanage_user.get_groups_by_prefix(group_prefix)

        # Remove groups that are no longer present in the identity provider's group list
        for cmn_group, group in cmn_groups_with_prefix.items():
            sleep(0.05)  # To avoid hitting the API rate limit
            if cmn_group not in groups_user:
                logger.debug("Group %s not found in IDP groups", cmn_group)
                logger.debug("Removing group %s from user", cmn_group)
                group_member_id = group_members[group["Id"]]
                comanage_groups.remove_member(group_member_id)

        # Add new groups from the identity provider to the COmanage user
        for group_name, group in groups_user.items():
            sleep(0.05)  # To avoid hitting the API rate limit
            if group_name not in cmn_groups_with_prefix:
                logger.debug("Group %s not found in comanage groups", group_name)
                logger.debug("Adding group %s to user", group_name)
                comanage_groups.set_member(group["Id"], comanage_user.co_person_id)

        return groups_user
