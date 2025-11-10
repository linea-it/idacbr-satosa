"""Custom exceptions for COmanage account linking"""

from typing import Optional


class COmanageAccountLinkingError(Exception):
    """Custom exception for COmanage account linking errors"""


class COmanageUserNotActiveError(Exception):
    """Custom exception for COmanage user errors"""


class COmanageUserNonLIneAError(Exception):
    """Custom exception for COmanage user errors"""


class COmanageGroupsError(Exception):
    """Custom exception for COmanage groups errors"""


class COmanageAPIError(Exception):
    """Custom exception for COmanage api errors"""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)
