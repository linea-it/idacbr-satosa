# -*- coding: utf-8 -*-
"""
COmanage API client for managing organizations, identities, groups, and group members.
Provides methods for authenticated HTTP requests with error handling and retry mechanisms.
"""

import logging
from time import sleep
from typing import Any, Dict, List, NoReturn, Optional, Union
from urllib.parse import urljoin

import requests

from .config import COmanageConfig
from .exceptions import COmanageAPIError

logger = logging.getLogger(__name__)


class COmanageAPI:
    """
    API client for interacting with COmanage Registry, providing methods to manage
    organizations, identities, groups, and group members through RESTful API requests.

    Supports authenticated HTTP requests with retry mechanisms and comprehensive
    error handling for COmanage Registry operations.

    Attributes:
        config (COmanageConfig): Configuration for API authentication and connection
    """

    session: requests.Session
    config: COmanageConfig

    def __init__(self, config: COmanageConfig):
        """
        Initialize the COmanageAPI client with configuration and set up an authenticated session.

        Args:
            config (COmanageConfig): Configuration containing API authentication credentials
        """
        self.config = config
        self.session = requests.Session()
        self.session.auth = (self.config.api_user, self.config.password)
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

    # @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def get_request(
        self, endpoint: str, params: Dict[str, Any]
    ) -> Union[Dict[str, Any], str]:
        """
        Perform a GET request to the specified COmanage Registry API endpoint.

        Args:
            endpoint (str): The API endpoint to request
            params (dict): Query parameters to include in the request

        Returns:
            The parsed JSON response or text response from the API, handled by __handle_response

        Raises:
            COmanageAPIError: If there are issues with the API request or response processing
        """
        url = urljoin(self.config.api_url, endpoint)
        response = self.session.get(url, params=params, timeout=30)
        return self.__handle_response(response)

    def post_request(
        self, endpoint: str, params: Dict[str, Any]
    ) -> Union[Dict[str, Any], str]:
        """
        Perform a POST request to the specified COmanage Registry API endpoint.

        Args:
            endpoint (str): The API endpoint to request
            params (dict): Query parameters to include in the request

        Returns:
            The parsed JSON response or text response from the API, handled by __handle_response

        Raises:
            COmanageAPIError: If there are issues with the API request or response processing
        """
        url = urljoin(self.config.api_url, endpoint)
        response = self.session.post(url, json=params)
        return self.__handle_response(response)

    def delete_request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Union[Dict[str, Any], str, None]:
        """
        Perform a DELETE request to the specified COmanage Registry API endpoint.

        Args:
            endpoint (str): The API endpoint to request
            params (dict, optional): Query parameters to include in the request

        Returns:
            The parsed JSON response or text response from the API, handled by __handle_response

        Raises:
            COmanageAPIError: If there are issues with the API request or response processing
        """
        url = urljoin(self.config.api_url, endpoint)
        response = self.session.delete(url, params=params)
        return self.__handle_response(response)

    def __handle_response(
        self, response: requests.Response
    ) -> Union[Dict[str, Any], str, None]:
        """
        Handle the HTTP response from a COmanage Registry API request.

        Processes the response by checking status, parsing JSON, and handling various
        potential error scenarios. Returns JSON data, plain text, or None for 204 status.

        Args:
            response (requests.Response): The HTTP response to process

        Returns:
            dict or str or None: Parsed JSON response, raw text, or None for empty responses

        Raises:
            COmanageAPIError: For JSON decoding errors, request failures, or HTTP errors
        """
        try:
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()
        except requests.exceptions.JSONDecodeError:
            return response.text
        except requests.exceptions.HTTPError as err:
            raise COmanageAPIError(
                message=f"Request failed: {str(err)}",
                status_code=getattr(err.response, "status_code", None),
            ) from err
        except requests.exceptions.RequestException as err:
            raise COmanageAPIError(
                message=str(err), status_code=getattr(err.response, "status_code", None)
            ) from err

    def get_org_identity_by_identifier(
        self, identifier: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve an organizational identity by a specific identifier.

        Searches for org identities matching the given identifier, removes duplicates,
        and returns the first org identity link found.

        Args:
            identifier (str): The identifier to search for in organizational identities.

        Returns:
            Optional[Dict[str, Any]]: The first organizational identity link found,
            or None if no link exists.

        Raises:
            COmanageAPIError: If no organizational identities are found for the given
            identifier.
        """
        res = self.get_request(
            "registry/org_identities.json",
            {"coid": self.config.co_id, "search.identifier": identifier},
        )

        org_identities = res.get("OrgIdentities", [])

        if len(org_identities) == 0:
            raise COmanageAPIError(
                "get_org_identities should return one or more results "
                f"but returned {len(org_identities)}"
            )

        org_identities = self.remove_orgs_duplicates(org_identities)

        for org_identity in org_identities:
            sleep(0.05)
            org_identity_id = org_identity["Id"]

            res = self.get_request(
                "registry/co_org_identity_links.json",
                {"orgidentityid": org_identity_id},
            )

            if res:
                return res

        return None

    def get_identifiers(self, co_person_id: int) -> List[Dict[str, Any]]:
        """
        Retrieve identifiers for a specific COmanage person.

        Args:
            co_person_id (int): The unique identifier of the COmanage person.

        Returns:
            list: A list of identifiers associated with the specified person.
        """

        res = self.get_request(
            "registry/identifiers.json", {"copersonid": co_person_id}
        )
        return res.get("Identifiers", [])

    def get_names(self, co_person_id: int) -> List[Dict[str, Any]]:
        """
        Retrieve names for a specific COmanage person.

        Args:
            co_person_id (int): The unique identifier of the COmanage person.

        Returns:
            list: A list of names associated with the specified person.
        """
        res = self.get_request("registry/names.json", {"copersonid": co_person_id})
        return res.get("Names", [])

    def get_emails(self, co_person_id: int) -> List[Dict[str, Any]]:
        """
        Retrieve email addresses for a specific COmanage person.

        Args:
            co_person_id (int): The unique identifier of the COmanage person.

        Returns:
            list: A list of email addresses associated with the specified person.
        """
        res = self.get_request(
            "registry/email_addresses.json", {"copersonid": co_person_id}
        )
        return res.get("EmailAddresses", [])

    def get_groups_by_copersonid(
        self, co_person_id: int, include_internal_groups: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieve groups associated with a specific COmanage person.

        Args:
            co_person_id (int): The unique identifier of the COmanage person.
            include_internal_groups (bool, optional): Flag to include internal groups.
                Defaults to False. When False, only returns non-automatic standard groups.

        Returns:
            list: A list of groups associated with the specified person, filtered
            based on include_internal_groups.
        """
        res = self.get_request("registry/co_groups.json", {"copersonid": co_person_id})

        if include_internal_groups:
            return res.get("CoGroups", [])

        groups = []
        for group in res.get("CoGroups", []):
            if group["Auto"] is False and group["GroupType"] == "S":
                groups.append(group)
        return groups

    def get_group_members_by_copersonid(
        self, co_person_id: int
    ) -> List[Dict[str, Any]]:
        """
        Retrieve group members for a specific COmanage person.

        Args:
            co_person_id (int): The unique identifier of the COmanage person.

        Returns:
            list: A list of group members associated with the specified person.
        """
        res = self.get_request(
            "registry/co_group_members.json", {"copersonid": co_person_id}
        )

        return res.get("CoGroupMembers", [])

    def get_co_person_id(self, identifier: str) -> Optional[int]:
        """
        Retrieve the COmanage person ID for a given identifier.

        Args:
            identifier (str): The identifier to look up.

        Returns:
            int or None: The COmanage person ID if found, otherwise None.

        Raises:
            COmanageAPIError: If no identity links are found for the given identifier.
        """
        org_identity = self.get_org_identity_by_identifier(identifier)

        identity_links = org_identity.get("CoOrgIdentityLinks", [])

        if len(identity_links) == 0:
            logger.warning(
                "get_co_org_identity_links should return one or more results but returned %d",
                len(identity_links),
            )
            return None

        identities = [dict(t) for t in {tuple(l.items()) for l in identity_links}]

        if len(identities) > 1:
            logger.warning(
                "identities: more than one identity found. Using the last one!"
            )

        for identity in identities:
            co_person_id = identity.get("CoPersonId", None)

            if co_person_id:
                return co_person_id

        return None

    def get_co_people(self, co_person_id):
        """get COPeople for a given co_person_id

        Args:
            co_person_id (int): The unique identifier of the COmanage person.

        Returns:
            dict: A dictionary containing the COPeople data.
        """

        _res = self.get_request(
            f"registry/co_people/{co_person_id}.json",
            {"coid": self.config.co_id},
        )

        co_people = _res.get("CoPeople", None)
        if not co_people:
            logger.warning("COPeople not found for co_person_id: %s", co_person_id)

        return co_people[0]

    @staticmethod
    def remove_orgs_duplicates(org_identities: list) -> List[Dict[str, Any]]:
        """
        Remove duplicate organization identities by converting to a unique set of dictionaries.

        Args:
            org_identities (list): A list of organization identities to deduplicate.

        Returns:
            list: A list of unique organization identities, with a warning if multiple
            identities are found.
        """
        org_identities = [dict(t) for t in {tuple(l.items()) for l in org_identities}]

        if len(org_identities) > 1:
            logger.warning(
                "org identities: more than one org_identity found. Using the last one!"
            )

        return org_identities

    def get_groups_by_co(self) -> List[Dict[str, Any]]:
        """Retrieve all groups for the configured COmanage organization.

        Returns:
            List[Dict[str, Any]]: A list of group dictionaries associated with the
            configured COmanage organization ID.
        """
        _data = self.get_request("registry/co_groups.json", {"coid": self.config.co_id})

        return _data.get("CoGroups", None)

    def add_group(self, group_name) -> Dict[str, Any]:
        """Create a new group in COmanage with the specified group name.

        Args:
            group_name (str): The name of the group to be created.

        Returns:
            Dict[str, Any]: A dictionary containing group details including the
            newly created group's ID.
        """
        _data = {
            "Version": "1.0",
            "CoId": self.config.co_id,
            "Name": group_name,
            "Description": "Group added automatically",
            "Status": "Active",
        }

        response = self.post_request("registry/co_groups.json", _data)
        _data["Id"] = response["Id"]

        return _data

    def add_group_member(self, co_group_id: int, co_person_id: int) -> Dict[str, Any]:
        """Add a member to a COmanage group.

        Args:
            co_group_id (int): The unique identifier of the COmanage group.
            co_person_id (int): The unique identifier of the COmanage person to
            be added as a group member.

        Returns:
            Dict[str, Any]: The response from the COmanage API after adding the group member.
        """
        _data = {
            "Version": "1.0",
            "CoGroupId": co_group_id,
            "CoPersonId": co_person_id,
            "Member": True,
        }

        return self.post_request("registry/co_group_members.json", _data)

    def remove_group_member(self, co_group_member_id: int) -> NoReturn:
        """Remove a member from a COmanage group.

        Args:
            co_group_member_id (int): The unique identifier of the group member to be removed.

        Returns:
            None: Deletes the specified group member from the COmanage group.
        """
        return self.delete_request(
            f"registry/co_group_members/{co_group_member_id}.json"
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()
