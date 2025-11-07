"""
This module defines the COmanageUser class, which represents a user in the
COmanage identity management system.
It provides methods to retrieve and validate user information, including
person ID, status, groups, and identifiers from a COmanage API.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, NoReturn, Optional

from .api import COmanageAPI
from .utils import filter_groups, filter_groups_by_prefix
from .exceptions import COmanageUserNotActiveError, COmanageUserNonLIneAError

logger = logging.getLogger(__name__)

PENDING_USER_STATUS = [
    "Pending",
    "PendingApproval",
    "PendingConfirmation",
    "PendingVetting",
]


class COmanageUser:
    """
    Represents a user in the COmanage identity management system.

    This class provides methods to retrieve and validate user information,
    including person ID, status, groups, and identifiers from a COmanage API.

    Attributes:
        - Provides read-only properties for user details like UID, person ID, and active status
        - Supports retrieving user groups and group members
        - Validates user existence and active status during initialization

    Raises:
        COmanageUserNotActiveError: If the user is not active or cannot be found in COmanage
    """

    def __init__(self, identifier: str, api: COmanageAPI) -> NoReturn:
        """
        Initialize a COmanage user by retrieving and validating their identity.

        Args:
            identifier (str): The unique identifier used to look up the user in COmanage.
            api (COmanageAPI): The COmanage API client used to fetch user information.

        Raises:
            AssertionError: If no matching user is found in COmanage.
            COmanageUserNotActiveError: If the user is not in an active status.

        Notes:
            - Retrieves the user's COmanage person ID
            - Fetches the user's identifier and status
            - Validates the user's active status
        """

        self.__api = api
        try:
            self.__co_person_id = self.api.get_co_person_id(identifier)
        except Exception as e:
            raise COmanageUserNonLIneAError(
                f"Error retrieving CO Person ID for identifier {identifier}: {e}"
            ) from e

        logger.debug("User %s has co_person_id %s", identifier, self.co_person_id)

        if not self.co_person_id:
            raise COmanageUserNonLIneAError(
                f"No matching user found in COmanage (identifier: {identifier})"
            )

        co_people = self.api.get_co_people(self.co_person_id)
        self.__status = co_people.get("Status", "NotFound")

        self.__ldap_uid = self.get_ldap_uid()
        logger.debug("User %s is %s", self.uid, self.__status)

    def get_ldap_uid(self) -> str:
        """
        Retrieve the LDAP UID of the COmanage user.
        Returns:
            str: The LDAP UID of the user.
        Raises:
            COmanageUserNotActiveError: If the user is not active.
        """

        if not self.is_active:
            if self.status not in PENDING_USER_STATUS:
                raise COmanageUserNotActiveError(
                    f"COPERSON ID {self.co_person_id} is not active"
                )
            return None

        identifier_uid = self.__get_identifier_uid()
        return identifier_uid.get("Identifier")

    @property
    def is_active(self) -> bool:
        """returns if the user is active or not

        Returns:
            bool: True if the user is active, False otherwise.
        """
        return self.__status == "Active"

    @property
    def status(self) -> str:
        """returns the status of the user

        Rerturns:
            str: The status of the user.
        """
        return self.__status

    @property
    def uid(self) -> str:
        """returns the uid of the user

        Returns:
            str: The uid of the user.
        """
        return self.__ldap_uid

    @property
    def co_person_id(self) -> int:
        """returns the co_person_id of the user

        Returns:
            int: The co_person_id of the user.
        """
        return self.__co_person_id

    @property
    def api(self) -> COmanageAPI:
        """returns the api of the user

        Returns:
            COmanageAPI: The api of the user.
        """
        return self.__api

    def __get_identifier_uid(self) -> Optional[Dict[str, any]]:
        """
        Retrieve the UID identifier for a COmanage user from their identifiers.

        Returns:
            Optional[Dict[str, any]]: The identifier dictionary with type 'uid',
            or None if no matching identifier is found.

        Notes:
            - Logs a warning if no identifiers are found for the given COmanage person ID.
        """
        identifiers = self.api.get_identifiers(co_person_id=self.co_person_id)

        if identifiers:
            for identifier in identifiers:
                if identifier["Type"] == "uid":
                    return identifier

        logger.warning(
            "No matching identifiers found in COmanage: %s", self.co_person_id
        )
        return None

    def get_groups(self) -> List[Dict[str, any]]:
        """
        Retrieve the groups associated with the COmanage user.

        Returns:
            List[Dict[str, any]]: A list of groups the user belongs to in COmanage,
            retrieved using the user's COmanage person ID.
        """

        groups = self.api.get_groups_by_copersonid(self.co_person_id)
        return filter_groups(groups)

    def get_groups_by_prefix(self, prefix) -> List[Dict[str, any]]:
        """
        Retrieve the groups associated with a specific identity provider (IdP)
        for the COmanage user.

        Args:
            prefix: The prefix to filter groups.

        Returns:
            List[Dict[str, any]]: A filtered list of groups that match the
            specified identity provider.
        """
        groups = self.api.get_groups_by_copersonid(self.co_person_id)
        return filter_groups_by_prefix(prefix, groups)

    def get_group_members(self) -> List[Dict[str, any]]:
        """
        Retrieve the list of group members associated with the COmanage user.

        Returns:
            List[Dict[str, any]]: A list of group members the user belongs to in COmanage,
            retrieved using the user's COmanage person ID.
        """
        return self.api.get_group_members_by_copersonid(self.co_person_id)

    def __repr__(self):
        return f"<COmanageUser {self.uid}>"

    def __str__(self):
        return f"<COmanageUser {self.uid}>"


@dataclass
class UserAttributes:
    """
    A data class representing user attributes extracted from authentication data.

    Stores the unique identifier and group memberships for a user, with a class method
    to parse these attributes from a dictionary of authentication data.

    Attributes:
        edu_person_unique_id (str): The unique identifier for the user.
        is_member_of (list[str]): A list of groups the user belongs to.
    """

    edu_person_unique_id: str
    is_member_of: list[str]
    co_manage_user: Dict[str, any] = field(
        default_factory=lambda: {
            "COmanageUID": None,
            "COmanageUserStatus": None,
            "COmanageGroups": [],
            "COmanageLogError": None,
        }
    )

    @classmethod
    def from_data(cls, _data: dict) -> "UserAttributes":
        """
        Create a UserAttributes instance from authentication data.

        Extracts the unique identifier and group memberships from the provided
        authentication data dictionary.

        Args:
            _data (dict): A dictionary containing authentication attributes.

        Returns:
            UserAttributes: An instance of UserAttributes with extracted unique ID
            and group memberships.
        """
        attributes = _data.attributes
        return cls(
            edu_person_unique_id=attributes.get("eduPersonUniqueId", [""])[0],
            is_member_of=attributes.get("isMemberOf", [""])[0].split(),
        )
