from satosa.micro_services.base import ResponseMicroService
from satosa.exception import SATOSAAuthenticationError
from satosa.context import Context
import requests
import logging
from urllib.parse import urljoin
from typing import Optional, Dict, Any, List, Union, NoReturn
from dataclasses import dataclass, field
from time import sleep
from functools import lru_cache
# from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@dataclass
class COmanageConfig:
    """
    Configuration class for COmanage API interactions.
    
    Holds authentication and connection parameters for interacting with the COmanage API,
    including API endpoint details, credentials, and connection settings.
    
    Attributes:
        api_url (str): Base URL for the COmanage API endpoint
        api_user (str): Username for API authentication
        password (str): Password for API authentication
        co_id (str): Identifier for the COmanage organization
        target_backends (List[Dict]): List of backend systems to target
    """
    api_url: str
    api_user: str
    password: str
    co_id: str
    target_backends: List[Dict]


class COmanageAccountLinkingError(Exception):
    """Custom exception for COmanage account linking errors"""
    pass


class COmanageUserNotActiveError(Exception):
    """Custom exception for COmanage user errors"""
    pass 


class COmanageGroupsError(Exception):
    """Custom exception for COmanage groups errors"""
    pass


class COmanageAPIError(Exception):
    """Custom exception for COmanage api errors"""
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


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
        self.session.auth = (config.api_user, config.password)
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    # @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def get_request(self, endpoint: str, params: Dict[str, Any]) -> Union[Dict[str, Any], str]:
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
        
    def post_request(self, endpoint: str, params: Dict[str, Any]) -> Union[Dict[str, Any], str]:
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

    def delete_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Union[Dict[str, Any], str, None]:
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

    def __handle_response(self, response: requests.Response) -> Union[Dict[str, Any], str, None]:
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
        except ValueError:
            return response.text
        except requests.exceptions.JSONDecodeError:
            raise COmanageAPIError("Invalid JSON response", response.status_code, response.text)
        except requests.exceptions.RequestException as err:
            raise COmanageAPIError(str(err), getattr(err.response, 'status_code', None))
        except requests.exceptions.HTTPError as err:
            raise COmanageAPIError(f"Request failed: {str(err)}", getattr(err.response, 'status_code', None))

    def get_org_identity_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an organizational identity by a specific identifier.
    
        Searches for org identities matching the given identifier, removes duplicates,
        and returns the first org identity link found.
    
        Args:
            identifier (str): The identifier to search for in organizational identities.
    
        Returns:
            Optional[Dict[str, Any]]: The first organizational identity link found, or None if no link exists.
    
        Raises:
            COmanageAPIError: If no organizational identities are found for the given identifier.
        """        
        result = self.get_request(
            "registry/org_identities.json",
            {"coid": self.config.co_id, "search.identifier": identifier},
        ) 
    
        org_identities = result["OrgIdentities"]

        if len(org_identities) == 0:
            raise COmanageAPIError(
                f"get_org_identities should return one or more results but returned {len(org_identities)}"
            )

        org_identities = self.remove_orgs_duplicates(org_identities)

        for org_identity in org_identities:
            sleep(0.05)
            org_identity_id = org_identity["Id"]

            result = self.get_request(
                "registry/co_org_identity_links.json", {"orgidentityid": org_identity_id}
            )

            if result:
                return result

        return None

    def get_identifiers(self, co_person_id: int) -> List[Dict[str, Any]]:
        """
        Retrieve identifiers for a specific COmanage person.

        Args:
            co_person_id (int): The unique identifier of the COmanage person.

        Returns:
            list: A list of identifiers associated with the specified person.
        """

        result = self.get_request("registry/identifiers.json", {"copersonid": co_person_id})
        return result["Identifiers"]

    def get_names(self, co_person_id: int) -> List[Dict[str, Any]]:
        """
        Retrieve names for a specific COmanage person.
        
        Args:
            co_person_id (int): The unique identifier of the COmanage person.
        
        Returns:
            list: A list of names associated with the specified person.
        """
        result = self.get_request("registry/names.json", {"copersonid": co_person_id})
        return result["Names"]

    def get_emails(self, co_person_id: int) -> List[Dict[str, Any]]:
        """
        Retrieve email addresses for a specific COmanage person.
        
        Args:
            co_person_id (int): The unique identifier of the COmanage person.
        
        Returns:
            list: A list of email addresses associated with the specified person.
        """
        result = self.get_request(
            "registry/email_addresses.json", {"copersonid": co_person_id}
        )
        return result["EmailAddresses"]

    def get_groups_by_copersonid(self, co_person_id: int, include_internal_groups: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieve groups associated with a specific COmanage person.
    
        Args:
            co_person_id (int): The unique identifier of the COmanage person.
            include_internal_groups (bool, optional): Flag to include internal groups. 
                Defaults to False. When False, only returns non-automatic standard groups.
    
        Returns:
            list: A list of groups associated with the specified person, filtered based on include_internal_groups.
        """
        result = self.get_request("registry/co_groups.json", {"copersonid": co_person_id})

        if include_internal_groups:
            return result["CoGroups"]
        else:
            groups = []
            for group in result["CoGroups"]:
                if group["Auto"] == False and group["GroupType"] == "S":
                    groups.append(group)
            return groups

    def get_group_members_by_copersonid(self, co_person_id: int) -> List[Dict[str, Any]]:
        """
        Retrieve group members for a specific COmanage person.
        
        Args:
            co_person_id (int): The unique identifier of the COmanage person.
        
        Returns:
            list: A list of group members associated with the specified person.
        """
        result = self.get_request("registry/co_group_members.json", {"copersonid": co_person_id})

        return result["CoGroupMembers"]

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

        identity_links = org_identity["CoOrgIdentityLinks"]

        if len(identity_links) == 0:
            logger.warning(
                f"get_co_org_identity_links should return one or more results but returned {len(identity_links)}"
            )
            return None
        
        identities = [dict(t) for t in {tuple(l.items()) for l in identity_links}]

        if len(identities) > 1:
            logger.warning("identities: more than one identity found. Using the last one!")

        for identity in identities:            
            co_person_id = identity.get("CoPersonId", None)

            if co_person_id:
                return co_person_id

        return None

    @staticmethod
    def remove_orgs_duplicates(org_identities: list) -> List[Dict[str, Any]]:
        """
        Remove duplicate organization identities by converting to a unique set of dictionaries.
        
        Args:
            org_identities (list): A list of organization identities to deduplicate.
        
        Returns:
            list: A list of unique organization identities, with a warning if multiple identities are found.
        """
        org_identities = [dict(t) for t in {tuple(l.items()) for l in org_identities}]

        if len(org_identities) > 1:
            logger.warning("org identities: more than one org_identity found. Using the last one!")
        
        return org_identities
    
    def get_groups_by_co(self) -> List[Dict[str, Any]]:
        """ Retrieve all groups for the configured COmanage organization.

        Returns:
            List[Dict[str, Any]]: A list of group dictionaries associated with the configured COmanage organization ID.
        """
        data = self.get_request("registry/co_groups.json", {"coid": self.config.co_id})

        return data["CoGroups"]

    def add_group(self, group_name) -> Dict[str, Any]:
        """ Create a new group in COmanage with the specified group name.
    
        Args:
            group_name (str): The name of the group to be created.
    
        Returns:
            Dict[str, Any]: A dictionary containing group details including the newly created group's ID.
        """
        data = {
            "Version": "1.0",
            "CoId": self.config.co_id,
            "Name": group_name,
            "Description": "Group added automatically",
            "Status": "Active",
        }

        response = self.post_request("registry/co_groups.json", data)
        data["Id"] = response["Id"]

        return data
    
    def add_group_member(self, co_group_id: int, co_person_id: int) -> Dict[str, Any]:
        """ Add a member to a COmanage group.
    
        Args:
            co_group_id (int): The unique identifier of the COmanage group.
            co_person_id (int): The unique identifier of the COmanage person to be added as a group member.
    
        Returns:
            Dict[str, Any]: The response from the COmanage API after adding the group member.
        """        
        data = {"Version":"1.0","CoGroupId": co_group_id,"CoPersonId": co_person_id, "Member": True}

        return self.post_request("registry/co_group_members.json", data)
    
    def remove_group_member(self, co_group_member_id: int) -> NoReturn:
        """ Remove a member from a COmanage group.

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
            group["Method"] = 'GET'
        else:
            group = self.create_group(group_name)
            group["Method"] = 'CREATED'

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
        Transform a list of group members into a dictionary mapping group IDs to member IDs.
    
        Args:
            group_members (List[Dict[str, any]]): A list of group member dictionaries containing 'CoGroupId' and 'Id' keys.
    
        Returns:
            Dict[str, str]: A dictionary where keys are group IDs and values are corresponding member IDs.
        """
        new_group_members = {}

        for group in group_members:
            new_group_members[group["CoGroupId"]] = group["Id"]

        return new_group_members
    

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
        self.__co_person_id = self.api.get_co_person_id(identifier)

        logger.debug(f"User {identifier} has co_person_id {self.co_person_id}")
        
        assert self.co_person_id, f"No matching user found in COmanage (identifier: {identifier})"

        identifier_uid = self.__get_identifier_uid()
        self.__status = identifier_uid.get("Status", "")
        self.__ldap_uid = identifier_uid.get("Identifier")

        if not self.is_active:
            raise COmanageUserNotActiveError(f"User {self.uid} is not active")
        
        logger.debug(f"User {self.uid} is {self.__status}")

    @property
    def is_active(self) -> bool:
        return self.__status == "Active"

    @property
    def status(self) -> str:
        return self.__status
    
    @property
    def uid(self) -> str:
        return self.__ldap_uid
    
    @property
    def co_person_id(self) -> int:
        return self.__co_person_id
    
    @property
    def api(self) -> COmanageAPI:
        return self.__api

    def __get_identifier_uid(self) -> Optional[Dict[str, any]]:
        """
        Retrieve the UID identifier for a COmanage user from their identifiers.
    
        Returns:
            Optional[Dict[str, any]]: The identifier dictionary with type 'uid', or None if no matching identifier is found.
    
        Notes:
            - Logs a warning if no identifiers are found for the given COmanage person ID.
        """        
        identifiers = self.api.get_identifiers(co_person_id=self.co_person_id)

        if identifiers:
            for identifier in identifiers:
                if identifier["Type"] == "uid":
                    return identifier

        logger.warning(f"No matching identifiers found in COmanage: {self.co_person_id}")
        return None
    
    def get_groups(self) -> List[Dict[str, any]]:
        """
        Retrieve the list of groups associated with the COmanage user.
    
        Returns:
            List[Dict[str, any]]: A list of groups the user belongs to in COmanage,
            retrieved using the user's COmanage person ID.
        """
        return self.api.get_groups_by_copersonid(self.co_person_id)

    def get_idp_groups(self, prefix) -> List[Dict[str, any]]:
        """
        Retrieve the groups associated with a specific identity provider (IdP) for the COmanage user.
    
        Args:
            prefix: The prefix to filter groups.
    
        Returns:
            List[Dict[str, any]]: A filtered list of groups that match the specified identity provider.
        """
        return filter_idp_groups(prefix, self.get_groups())

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
    co_manage_user: Dict[str, any] = field(default_factory=lambda: {
        "COmanageUID": "",
        "COmanageUserStatus": "",
        "COmanageGroups": []
    })

    @classmethod
    def from_data(cls, data: dict) -> "UserAttributes":
        """
        Create a UserAttributes instance from authentication data.

        Extracts the unique identifier and group memberships from the provided authentication data dictionary.
    
        Args:
            data (dict): A dictionary containing authentication attributes.
    
        Returns:
            UserAttributes: An instance of UserAttributes with extracted unique ID and group memberships.
        """
        attributes = data.attributes
        return cls(
            edu_person_unique_id=attributes.get("eduPersonUniqueId", [""])[0],
            is_member_of=attributes.get("isMemberOf", [""])[0].split()
        )


class COmanageAccountLinkingMicroService(ResponseMicroService):
    """
    A microservice for handling account linking in COmanage, specifically managing group associations
    between identity providers and COmanage.
    
    This service processes authentication requests, links user accounts, and synchronizes group memberships
    across different identity providers and COmanage. It supports multiple target backends and handles
    group registration, addition, and removal based on user attributes.
    
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
        self.backend = None

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
        logger.debug("Processing data: %s", data)

        self.backend = context.target_backend

        user = UserAttributes.from_data(data)

        if not self.backend in [item["name"] for item in self.target_backends]:
            logger.info(f"Backend {self.backend} not in target backends")
            data.attributes.update(user.co_manage_user)
            return super().process(context, data)
        
        self.group_prefix = self.__get_group_prefix(self.backend, self.target_backends)

        try: 
            comanage_user = COmanageUser(user.edu_person_unique_id, self.api)
            logger.info(f"COmanage user: {comanage_user}")
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

        try:
            user_groups = self.register_groups(
                idp_groups=user.is_member_of,
                comanage_user=comanage_user
            )
            user.co_manage_user["COmanageGroups"] = list(user_groups.keys())
        except COmanageGroupsError as err:
            logger.error(err)
        
        data.attributes.update(user.co_manage_user)
        return super().process(context, data)

    def __get_group_prefix(self, backend_name: str, target_backends: List[Dict[str, Any]]) -> str:
        """
        Get the group prefix for a specific backend.

        Args:
            backend_name (str): The name of the backend.
            target_backends (List[Dict[str, Any]]): List of configured backends.

        Returns:
            str: The group prefix for the backend.
        """
        for backend in target_backends:
            if backend["name"] == backend_name:
                return backend.get("prefix", backend_name)
        return backend_name

    def register_groups(self, idp_groups: List[str], comanage_user: COmanageUser) -> Dict[str, Any]:
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

            logger.debug(f"Group {idp_group_name}: {idp_group['Id']} - {idp_group['Method']}")

            idp_groups_user[idp_group_name] = {
                "Id": idp_group["Id"],
                "Method": idp_group["Method"],
            }

        com_group_members_user = comanage_groups.organize_group_members(
            comanage_user.get_group_members()
        )

        com_groups_user = comanage_user.get_idp_groups(self.backend)

        for group_name, data in idp_groups_user.items():
            if group_name not in com_groups_user:
                logger.debug(f"Group {group_name} not found in comanage groups")
                logger.debug(f"Adding group {group_name} to user")
                comanage_groups.set_member(data["Id"], comanage_user.co_person_id)

        for idp_group, data in com_groups_user.items():
            if idp_group not in idp_groups_user:
                logger.debug(f"Group {idp_group} not found in idp groups")
                logger.debug(f"Removing group {idp_group} from user")
                group_member_id = com_group_members_user[data["Id"]]
                comanage_groups.remove_member(group_member_id)

        return idp_groups_user


def filter_idp_groups(prefix: str, groups: List[Dict[str, any]]) -> Dict[str, Dict[str, any]]:
    """
    Filter groups by identity provider and group type.
    
    Args:
        prefix (str): The identity provider prefix to match against group names.
        groups (List[Dict[str, any]]): A list of group dictionaries to filter.
    
    Returns:
        Dict[str, Dict[str, any]]: A dictionary of filtered groups, keyed by group name,
        where the group name starts with the specified idp and has a group type of 'S'.
    """
    response = {}

    for group in groups: 
        if group["Name"].startswith(prefix) and group["GroupType"] == "S":
            response[group["Name"]] = group

    return response


if __name__ == "__main__":
    """
    Script to test COmanage Account Linking microservice functionality.

    This script provides a command-line interface to test the COmanageAccountLinkingMicroService
    by simulating a user authentication and group membership process. It allows manual testing
    of account linking with configurable parameters.

    Usage:
        python comanage_account_linking.py --config comanage_account_linking.yaml --edu-person-unique-id b70fa504e3a@example.com --is-member-of "group1 group2"

    Requires:
        - YAML configuration file
        - eduPersonUniqueId
        - Space-separated list of group memberships
    """

    import yaml
    import argparse

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(description='Test COmanage Account Linking')
    parser.add_argument('--config', type=str, required=True, help='Path to YAML config file')
    parser.add_argument('--edu-person-unique-id', type=str, required=True, help='eduPersonUniqueId value')
    parser.add_argument('--is-member-of', type=str, required=True, help='Space-separated list of group memberships')
    args = parser.parse_args()

    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
        config = config["config"]
    

    # Setup mock data with command line arguments
    @dataclass
    class Data:
        attributes: Dict[str, List[str]]


    data = Data(attributes = {
        "eduPersonUniqueId": [args.edu_person_unique_id],
        "isMemberOf": [args.is_member_of]
    })

    # Mock context
    context = Context()
    context.target_backend = "rubin_oidc"

    # Define a mock next callback
    def mock_next(context, internal_data):
        return {"success": True, "data": internal_data}

    # Initialize the service
    service = COmanageAccountLinkingMicroService(
        config,
        name="comanage_account_linking",
        base_url=config.get("api_url"),
    )

    service.next = mock_next

    # Test the process method
    result = service.process(context, data)
    print(f"Result: {result}")
