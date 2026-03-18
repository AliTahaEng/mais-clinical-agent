"""
API authentication — re-exports from auth package for backwards compatibility.
All actual logic lives in medical_ais/auth/.
"""
from medical_ais.auth.dependencies import (  # noqa: F401
    get_current_user,
    get_current_user_optional,
    require_admin,
)
