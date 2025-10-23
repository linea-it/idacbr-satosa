"""This file is part of the SATOSA project."""

import logging
import os
from dataclasses import dataclass
from typing import Dict, List

import pytest
import yaml
from comanage_account_linking import COmanageAccountLinkingMicroService
from comanage_account_linking.utils import get_backend_config
from satosa.context import Context

logger = logging.getLogger()


@pytest.fixture
def mock_context():
    """Fixture for creating a mock Context."""
    return Context()


@pytest.fixture
def comanage_config():
    """Fixture for loading COmanage configuration."""
    config_file = os.getenv("COMANAGE_CONFIG")
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        return config["config"]


@pytest.fixture
def microservice(comanage_config) -> COmanageAccountLinkingMicroService:
    """Fixture for initializing the microservice."""
    config = comanage_config
    return COmanageAccountLinkingMicroService(
        config, name="comanage_account_linking", base_url=config.get("api_url")
    )


def test_init(microservice: COmanageAccountLinkingMicroService):
    """Test service initialization."""
    assert microservice.api is not None


def test_process(
    microservice: COmanageAccountLinkingMicroService,
    mock_context: Context,
    comanage_config: Dict[str, str],
):
    """Test process when backend is not in target backends."""

    # Setup mock data with command line arguments
    @dataclass
    class Data:
        """Mock data"""

        attributes: Dict[str, List[str]]

    edu_person_unique_id = os.getenv("EDU_PERSON_UNIQUE_ID")
    is_member_of = os.getenv("IS_MEMBER_OF")

    _data = Data(
        attributes={
            "eduPersonUniqueId": [edu_person_unique_id],
            "isMemberOf": [is_member_of],
        }
    )

    _context = mock_context
    backend_name = comanage_config.get("target_backends", [])[0].get("name")
    _context.target_backend = backend_name

    # Define a mock next callback
    def mock_next(_context, internal_data):
        """Mock next callback function"""
        return {"success": True, "data": internal_data}

    # Assign the mock_next callback as an attribute for testing purposes
    setattr(microservice, "next", mock_next)

    # Test the process method
    result = microservice.process(_context, _data)
    data = result["data"]

    groups = []

    logger.info("Data attributes before: %s", data.attributes)

    is_member_of = data.attributes.get("isMemberOf", [None])[0]
    if is_member_of:
        group_prefix = get_backend_config(
            backend_name,
            comanage_config.get("target_backends", []),
            "prefix",
            backend_name,
        )
        logger.info("Groups: %s", is_member_of)
        is_member_of = is_member_of.split(",")
        groups = list(map(lambda x: f"{group_prefix}_{x}", is_member_of))

    for group in groups:
        assert group in data.attributes.get("COmanageGroups", [])

    assert result["success"] is True

    logger.info("Data attributes: %s", data.attributes)


def test_process_no_backend(
    microservice: COmanageAccountLinkingMicroService,
    mock_context: Context,
):
    """Test process when backend is not in target backends."""

    # Setup mock data with command line arguments
    @dataclass
    class Data:
        """Mock data"""

        attributes: Dict[str, List[str]]

    edu_person_unique_id = os.getenv("EDU_PERSON_UNIQUE_ID")
    is_member_of = os.getenv("IS_MEMBER_OF")

    _data = Data(
        attributes={
            "eduPersonUniqueId": [edu_person_unique_id],
            "isMemberOf": [is_member_of],
        }
    )

    _context = mock_context
    _context.target_backend = "non_existent_backend"

    # Define a mock next callback
    def mock_next(_context, internal_data):
        """Mock next callback function"""
        return {"success": True, "data": internal_data}

    # Assign the mock_next callback as an attribute for testing purposes
    setattr(microservice, "next", mock_next)

    # Test the process method
    result = microservice.process(_context, _data)
    data = result["data"]

    assert data.attributes.get("COmanageUID", None) is None
    assert data.attributes.get("COmanageUserStatus", None) is None
    assert data.attributes.get("COmanageGroups", []) == []
    assert result["success"] is True

    logger.info("Data attributes: %s", data.attributes)
