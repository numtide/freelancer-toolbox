"""Dynamic object resolver for SevDesk API."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import SevDeskClient


class ObjectType(Enum):
    """Supported object types for dynamic resolution."""

    UNITY = "Unity"
    TAX_RULE = "TaxRule"


class ObjectResolver:
    """Resolves object IDs dynamically from the SevDesk API."""

    def __init__(self, client: SevDeskClient) -> None:
        self.client = client
        self._cache: dict[tuple[ObjectType, str], dict[str, dict[str, Any]]] = {}

    def _fetch_objects(
        self, object_type: ObjectType, key_field: str = "translationCode"
    ) -> dict[str, dict[str, Any]]:
        """Fetch all objects of a specific type from the API and cache them.

        Args:
            object_type: The type of objects to fetch
            key_field: The field to use as the cache key (default: translationCode)

        Returns:
            Dict mapping key_field values to object data
        """
        params = {"limit": 1000}
        response = self.client.get(object_type.value, params=params)

        object_map = {}
        if "objects" in response:
            for obj in response["objects"]:
                key_value = obj.get(key_field)
                if key_value:
                    object_map[key_value] = {
                        "id": int(obj["id"]),
                        "name": obj.get("name", ""),
                        "objectName": obj.get("objectName", object_type.value),
                    }
                    # Include additional fields that might be useful
                    for field in ["code", "priority", "color", "systemType"]:
                        if field in obj:
                            object_map[key_value][field] = obj[field]

        return object_map

    def get_object(
        self, object_type: ObjectType, key: str, key_field: str = "translationCode"
    ) -> dict[str, Any]:
        """Get object data by key.

        Args:
            object_type: The type of object to fetch
            key: The key value to look up
            key_field: The field to use as the key (default: translationCode)

        Returns:
            Dict with object data including at least id, name, and objectName

        Raises:
            ValueError: If key not found
        """
        cache_key = (object_type, key_field)

        if cache_key not in self._cache:
            self._cache[cache_key] = self._fetch_objects(object_type, key_field)

        if key not in self._cache[cache_key]:
            # Try to refresh cache once
            self._cache[cache_key] = self._fetch_objects(object_type, key_field)

            if key not in self._cache[cache_key]:
                available = ", ".join(sorted(self._cache[cache_key].keys()))
                msg = f"{object_type.value} with {key_field}='{key}' not found. Available: {available}"
                raise ValueError(msg)

        return self._cache[cache_key][key]

    # Convenience methods for Unity
    def get_unity_by_translation_code(self, translation_code: str) -> dict[str, Any]:
        """Get Unity data by translation code."""
        return self.get_object(ObjectType.UNITY, translation_code)

    # Convenience methods for TaxRule
    def get_tax_rule_by_id(self, rule_id: int) -> dict[str, Any]:
        """Get TaxRule data by ID."""
        return self.get_object(ObjectType.TAX_RULE, str(rule_id), key_field="id")

    def get_tax_rule_by_name(self, name: str) -> dict[str, Any]:
        """Get TaxRule data by name."""
        return self.get_object(ObjectType.TAX_RULE, name, key_field="name")

    def get_tax_rule_by_code(self, code: str) -> dict[str, Any]:
        """Get TaxRule data by code."""
        return self.get_object(ObjectType.TAX_RULE, code, key_field="code")
