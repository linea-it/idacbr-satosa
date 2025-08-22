"""Configuration for COmanage Account Linking Microservice"""

from typing import Dict, List
from dataclasses import dataclass


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
