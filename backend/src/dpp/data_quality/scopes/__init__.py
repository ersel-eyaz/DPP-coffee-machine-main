"""
Scope definitions shared by harmonization and anomaly detection.
"""

from dpp.data_quality.scopes.emission import EMISSION_SCOPE
from dpp.data_quality.scopes.product import PRODUCT_SCOPE
from dpp.data_quality.scopes.schemas import CanonicalField, CanonicalRelation, ScopeDefinition

SUPPORTED_SCOPES = {
    PRODUCT_SCOPE.name: PRODUCT_SCOPE,
    EMISSION_SCOPE.name: EMISSION_SCOPE,
}

__all__ = [
    "CanonicalField",
    "CanonicalRelation",
    "ScopeDefinition",
    "PRODUCT_SCOPE",
    "EMISSION_SCOPE",
    "SUPPORTED_SCOPES",
]
