"""
This module defines the COmanageGroups class, which manages group operations
in the COmanage identity management system.
It provides methods to interact with COmanage groups, including:
    - Retrieving existing groups by identity provider
    - Creating new groups
    - Adding and removing group members
    - Caching and organizing group information
"""

from functools import lru_cache
from typing import Any, Dict, List, Optional, NoReturn

from .api import COmanageAPI
from .utils import filter_idp_groups


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

    def __init__(self, api: COmanageAPI, prefix: str) -> NoReturn:
        """
        Initialize a COmanageGroups instance.

        Args:
            api (COmanageAPI): The COmanage API client for performing group operations.
            prefix (str): The prefix to filter groups.

        Initializes the instance with the provided API client and retrieves
        groups filtered by the specified backend.
        """

        self.__api = api
        self.__idp_groups = self.__get_idp_groups(prefix)

    @property
    def idp_groups(self) -> Dict[str, Dict[str, Any]]:
        """Cached groups filtered by identity provider."""
        return self.__idp_groups

    @lru_cache(maxsize=128)
    def get_idp_group(self, group_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific group from the cached identity provider groups.

        Args:
            group_name (str): The name of the group to retrieve.

        Returns:
            Optional[Dict[str, Any]]: The group dictionary if found, otherwise None.
        """
        return self.idp_groups.get(group_name, None)

    def get_or_create_group(self, group_name: str) -> Dict[str, Any]:
        """
        Retrieve an existing group or create a new one if it doesn't exist.

        Args:
            group_name (str): The name of the group to retrieve or create.

        Returns:
            Dict[str, Any]: The group dictionary with an additional 'Method' key
            indicating whether the group was retrieved ('GET') or created ('CREATED').
        """
        group = self.get_idp_group(group_name)

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

    def __get_idp_groups(self, prefix: str) -> Dict[str, Dict[str, any]]:
        """
        Retrieve and filter groups for a specific prefix group.

        Args:
            prefix (str): The prefix to filter groups.

        Returns:
            Dict[str, Dict[str, any]]: A dictionary of groups associated with the prefix group.
        """

        groups = self.__api.get_groups_by_co()
        return filter_idp_groups(prefix, groups)

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
