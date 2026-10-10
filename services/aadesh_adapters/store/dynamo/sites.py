"""DynamoDB store for construction-site profiles.

A site profile is the set of facts obligations are resolved against, so it is data, not code.
Keeping it in DynamoDB rather than bundled with the Lambda means the facts a resolution rests
on can be inspected and corrected without a redeploy -- and it means the deployed system has
exactly one source of site facts rather than a packaged copy that drifts from it.
"""

from __future__ import annotations

from typing import Any

from aadesh_adapters.store.dynamo.client import dynamo_resource, table_name
from aadesh_core.domain.construction import ConstructionSite


class DynamoSitesStore:
    def __init__(self, *, dynamo: Any = None, table_name_override: str | None = None) -> None:
        self._table_name = table_name_override or table_name("sites")
        self._dynamo = dynamo
        self._table = None

    @property
    def table(self) -> Any:
        if self._table is None:
            self._table = (self._dynamo or dynamo_resource()).Table(self._table_name)
        return self._table

    def get(self, site_id: str) -> ConstructionSite | None:
        item = self.table.get_item(Key={"site_id": site_id}, ConsistentRead=True).get("Item")
        if not item:
            return None
        payload = {k: v for k, v in item.items() if k != "label"}
        return ConstructionSite.from_dict(_native(payload))

    def save(self, site: ConstructionSite) -> None:
        from dataclasses import asdict

        item = {k: v for k, v in asdict(site).items() if v is not None}
        item["site_id"] = site.site_id
        self.table.put_item(Item=item)


def _native(payload: dict[str, Any]) -> dict[str, Any]:
    """Turn DynamoDB's Decimal back into int/float so `from_dict` sees plain numbers.

    `from_dict` rejects a non-finite or negative numeric and accepts `int|float`; a `Decimal`
    is neither, and silently accepting it would let a type-tagged profile change meaning.
    """
    from decimal import Decimal

    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, Decimal):
            out[key] = int(value) if value == value.to_integral_value() else float(value)
        else:
            out[key] = value
    return out
