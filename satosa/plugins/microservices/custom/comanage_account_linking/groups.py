"""
This module defines the COmanageGroups class, which manages group operations
in the COmanage identity management system.
It provides methods to interact with COmanage groups, including:
    - Retrieving existing groups by identity provider
    - Creating new groups
    - Adding and removing group members
    - Caching and organizing group information
"""

import logging
from functools import lru_cache
from typing import Any, Dict, List, Optional, NoReturn, Set

from .api import COmanageAPI
from .exceptions import COmanageAPIError
from .utils import filter_groups, filter_groups_by_prefix


logger = logging.getLogger(__name__)


class COmanageGroups:
    """
    Manages group operations in the COmanage identity management system.

    This class provides methods to interact with COmanage groups, including:
        - Retrieving existing groups by identity provider
        - Creating new groups
        - Adding and removing group members
        - Caching and organizing group information

    Attributes:
        __api (COmanageAPI): The COmanage API client used for group operations.
        idp_groups (Dict[str, Dict[str, Any]]): Cached groups filtered by identity provider.
    """

    def __init__(self, api: COmanageAPI, unix_cluster_id: int) -> NoReturn:
        """
        Initialize a COmanageGroups instance.

        Args:
            api (COmanageAPI): The COmanage API client for performing group operations.
            unix_cluster_id (int): UnixCluster plugin record ID used for POSIX
                group provisioning.

        Initializes the instance with the provided API client and retrieves
        groups filtered by the specified backend.
        """

        self.__api = api
        self.__unix_cluster_id = int(unix_cluster_id)
        self.__groups = filter_groups(self.__api.get_groups_by_co())
        self.__unix_cluster_group_ids = self.__load_unix_cluster_group_ids()

    def __load_unix_cluster_group_ids(self) -> Set[int]:
        """Load active CO Group associations for the configured Unix Cluster."""
        associations = self.__api.get_unix_cluster_groups(self.__unix_cluster_id)

        return {
            int(association["CoGroupId"])
            for association in associations
            if not association.get("Deleted", False)
        }

    @property
    def groups(self) -> Dict[str, Dict[str, Any]]:
        """Get cached groups by co"""
        return self.__groups

    def groups_by_prefix(self, prefix: str) -> Dict[str, Dict[str, Any]]:
        """
        Retrieve and filter groups for a specific prefix group.

        Args:
            prefix (str): The prefix to filter groups.

        Returns:
            Dict[str, Dict[str, any]]: A dictionary of groups associated with the prefix group.
        """
        return filter_groups_by_prefix(prefix, self.groups)

    @lru_cache(maxsize=128)
    def get_group(self, group_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific group.

        Args:
            group_name (str): The name of the group to retrieve.

        Returns:
            Optional[Dict[str, Any]]: The group dictionary if found, otherwise None.
        """
        return self.groups.get(group_name)

    def get_or_create_group(self, group_name: str) -> Dict[str, Any]:
        """
        Retrieve an existing group or create a new one if it doesn't exist.

        Args:
            group_name (str): The name of the group to retrieve or create.

        Returns:
            Dict[str, Any]: The group dictionary with an additional 'Method' key
            indicating whether the group was retrieved ('GET') or created ('CREATED').
        """
        group = self.get_group(group_name)

        if group:
            group["Method"] = "GET"
        else:
            group = self.create_group(group_name)
            group["Method"] = "CREATED"

        return group

    def create_group(self, group_name: str) -> Dict[str, any]:
        """
        Create a new group in the COmanage system.

        Args:
            group_name (str): The name of the group to create.

        Returns:
            Dict[str, Any]: The data of the newly created group, including its unique identifier.
        """
        return self.__api.add_group(group_name)

    def ensure_unix_cluster_group(self, co_group_id: int) -> bool:
        """Ensure a CO Group is associated with the configured Unix Cluster.

        The operation is idempotent. If concurrent authentication requests try
        to create the same association, a failed POST is accepted only when a
        subsequent read confirms that the association now exists.

        Args:
            co_group_id (int): CO Group ID to associate.

        Returns:
            bool: True when this call created the association, otherwise False.

        Raises:
            COmanageAPIError: If the association cannot be created or confirmed.
        """
        co_group_id = int(co_group_id)

        if co_group_id in self.__unix_cluster_group_ids:
            return False

        try:
            self.__api.add_unix_cluster_group(
                self.__unix_cluster_id, co_group_id
            )
        except COmanageAPIError:
            # Another SATOSA request may have inserted the association after our
            # initial GET. Only suppress the error if COmanage confirms it exists.
            self.__unix_cluster_group_ids = self.__load_unix_cluster_group_ids()
            if co_group_id in self.__unix_cluster_group_ids:
                logger.info(
                    "Unix Cluster Group association already created concurrently: "
                    "unix_cluster_id=%s co_group_id=%s",
                    self.__unix_cluster_id,
                    co_group_id,
                )
                return False
            raise

        self.__unix_cluster_group_ids.add(co_group_id)
        return True

    def set_member(self, co_group_id: int, co_person_id: int) -> NoReturn:
        """
        Add a user to a group in the COmanage system.

        Args:
            co_group_id (int): The unique identifier of the group to add the member to.
            co_person_id (int): The unique identifier of the person to be added as a group member.
        """

        self.__api.add_group_member(co_group_id, co_person_id)

    def remove_member(self, co_group_member_id: int) -> NoReturn:
        """
        Remove a member from a group in the COmanage system.

        Args:
            co_group_member_id (int): The unique identifier of the group member to remove.
        """

        self.__api.remove_group_member(co_group_member_id)

    @staticmethod
    def organize_group_members(group_members: List[Dict[str, any]]) -> Dict[str, str]:
        """
        Transform a list of group members into a dictionary mapping group IDs to
        member IDs.

        Args:
            group_members (List[Dict[str, any]]): A list of group member dictionaries
            containing 'CoGroupId' and 'Id' keys.

        Returns:
            Dict[str, str]: A dictionary where keys are group IDs and values are
            corresponding member IDs.
        """
        new_group_members = {}

        for group in group_members:
            new_group_members[group["CoGroupId"]] = group["Id"]

        return new_group_members
