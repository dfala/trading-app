"""In-memory model registry for controlled promotion workflows."""

from __future__ import annotations

from datetime import datetime

from trading_app.learning.models import (
    ModelRegistrySnapshot,
    ModelRegistryState,
    ModelVersionRecord,
)


class ModelRegistryError(ValueError):
    """Raised when a registry operation would violate promotion controls."""


class ModelRegistry:
    """Track model versions and which versions are actively allowed to trade."""

    def __init__(self) -> None:
        self._records: dict[str, ModelVersionRecord] = {}

    def register(self, record: ModelVersionRecord) -> ModelVersionRecord:
        if record.key in self._records:
            raise ModelRegistryError(f"model version already registered: {record.key}")
        if record.is_active and self.active_model(record.strategy_id) is not None:
            raise ModelRegistryError(
                f"active model already exists for {record.strategy_id}"
            )
        self._records[record.key] = record
        return record

    def get(self, strategy_id: str, version: str) -> ModelVersionRecord:
        key = _key(strategy_id, version)
        try:
            return self._records[key]
        except KeyError as error:
            raise ModelRegistryError(f"unknown model version: {key}") from error

    def active_model(self, strategy_id: str) -> ModelVersionRecord | None:
        active = [
            record
            for record in self._records.values()
            if record.strategy_id == strategy_id and record.is_active
        ]
        if len(active) > 1:
            raise ModelRegistryError(f"multiple active models for {strategy_id}")
        return active[0] if active else None

    def transition_state(
        self,
        *,
        strategy_id: str,
        version: str,
        state: ModelRegistryState,
    ) -> ModelVersionRecord:
        record = self.get(strategy_id, version)
        updated = record.model_copy(update={"state": state})
        self._records[record.key] = updated
        return updated

    def set_active(
        self,
        *,
        strategy_id: str,
        version: str,
        approved_by: str,
    ) -> ModelVersionRecord:
        """Manual-only active model change; nightly jobs should not call this."""

        if not approved_by:
            raise ModelRegistryError("approved_by is required to change active model")
        target = self.get(strategy_id, version)
        for record in list(self._records.values()):
            if record.strategy_id == strategy_id and record.is_active:
                self._records[record.key] = record.model_copy(
                    update={"is_active": False}
                )
        updated = target.model_copy(update={"is_active": True})
        self._records[target.key] = updated
        return updated

    def snapshot(self, as_of: datetime) -> ModelRegistrySnapshot:
        records = tuple(sorted(self._records.values(), key=lambda record: record.key))
        active_keys = tuple(record.key for record in records if record.is_active)
        return ModelRegistrySnapshot(
            as_of=as_of,
            records=records,
            active_keys=active_keys,
        )


def _key(strategy_id: str, version: str) -> str:
    return f"{strategy_id}:{version}"
