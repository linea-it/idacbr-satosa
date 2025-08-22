"""This module provides utility functions"""

from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def filter_idp_groups(
    prefix: str, groups: List[Dict[str, any]]
) -> Dict[str, Dict[str, any]]:
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

    logger.info("---> GROUPS: %s", groups)
    logger.info("---> prefix: %s", prefix)

    for group in groups:
        if (
            group["Name"].startswith(f"{prefix}_")
            and group["GroupType"] == "S"
        ):
            response[group["Name"]] = group

    logger.info("---> idp groups: %s", response)

    return response


def filter_groups(groups: List[Dict[str, any]]) -> Dict[str, Dict[str, any]]:
    """
    Filter groups by group type.

    Args:
        groups (List[Dict[str, any]]): A list of group dictionaries to filter.

    Returns:
        Dict[str, Dict[str, any]]: A dictionary of filtered groups by group type.
    """
    response = {}

    for group in groups:
        if group["Auto"] is False and group["GroupType"] == "S":
            response[group["Name"]] = group

    return response


def get_backend_config(
    backend_name: str,
    target_backends: List[Dict[str, Any]],
    config_key: str,
    default=None,
) -> Any:
    """
    Get the configuration for a specific backend.

    Args:
        backend_name (str): The name of the backend.
        target_backends (List[Dict[str, Any]]): List of configured backends.
        config_key (str): The configuration key to retrieve.
        default (any, optional): Default value if the configuration is not found.

    Returns:
        any: The configuration value for the specified backend.
    """

    for backend in target_backends:
        if backend["name"] == backend_name:
            return backend.get(config_key, default)
    return default
