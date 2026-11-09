"""Runtime-enforced user disruption policy.

Warnings and confirmations are represented by short-lived, one-use receipts
minted by trusted runtime surfaces. Booleans supplied in a model action are not
accepted as authorization evidence.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from enum import StrEnum

from adaptive_operator.device_context import DeviceActivity


class InterruptionLevel(StrEnum):
    L0_SILENT = "L0"
    L1_WARN = "L1"
    L2_CONFIRM = "L2"


@dataclass(frozen=True)
class ActionEffects:
    read_only: bool = False
    visible_ui: bool = False
    focus_change: bool = False
    pointer: bool = False
    keyboard: bool = False
    desktop_change: bool = False
    destructive: bool = False
    closes_unsaved_work: bool = False
    sensitive_permission: bool = False
    irreversible: bool = False
    restart_or_shutdown: bool = False

    def level(self) -> InterruptionLevel:
        if any((
            self.destructive,
            self.closes_unsaved_work,
            self.sensitive_permission,
            self.irreversible,
            self.restart_or_shutdown,
        )):
            return InterruptionLevel.L2_CONFIRM
        if any((
            self.visible_ui,
            self.focus_change,
            self.pointer,
            self.keyboard,
            self.desktop_change,
        )):
            return InterruptionLevel.L1_WARN
        return InterruptionLevel.L0_SILENT


@dataclass(frozen=True)
class EnforcementEvidence:
    warning_receipt_id: str | None = None
    confirmation_grant_id: str | None = None


@dataclass(frozen=True)
class InterruptionDecision:
    level: InterruptionLevel
    allowed: bool
    warning_required: bool
    confirmation_required: bool
    user_active: bool | None


@dataclass(frozen=True)
class _Receipt:
    kind: str
    action_scope: str
    device_id: str
    expires_at: float


class RuntimeEvidenceLedger:
    """In-memory contract prototype; production wiring uses the approval store."""

    def __init__(self) -> None:
        self._receipts: dict[str, _Receipt] = {}

    def record_warning(
        self, *, action_scope: str, device_id: str, now: float, ttl_seconds: float
    ) -> str:
        return self._record("warning", action_scope, device_id, now, ttl_seconds)

    def record_confirmation(
        self, *, action_scope: str, device_id: str, now: float, ttl_seconds: float
    ) -> str:
        return self._record("confirmation", action_scope, device_id, now, ttl_seconds)

    def _record(
        self,
        kind: str,
        action_scope: str,
        device_id: str,
        now: float,
        ttl_seconds: float,
    ) -> str:
        if not action_scope or not device_id or ttl_seconds <= 0:
            raise ValueError("receipt scope, device and positive TTL are required")
        receipt_id = secrets.token_urlsafe(24)
        self._receipts[receipt_id] = _Receipt(
            kind=kind,
            action_scope=action_scope,
            device_id=device_id,
            expires_at=now + ttl_seconds,
        )
        return receipt_id

    def consume(
        self,
        receipt_id: str | None,
        *,
        kind: str,
        action_scope: str,
        device_id: str,
        now: float,
    ) -> bool:
        if not receipt_id:
            return False
        receipt = self._receipts.pop(receipt_id, None)
        return bool(
            receipt is not None
            and receipt.kind == kind
            and receipt.action_scope == action_scope
            and receipt.device_id == device_id
            and now <= receipt.expires_at
        )


class PolicyBlocked(PermissionError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class InterruptionGate:
    """Authoritative gate immediately before dispatch, independent of prompt prose."""

    def __init__(self, ledger: RuntimeEvidenceLedger) -> None:
        self.ledger = ledger

    def authorize(
        self,
        effects: ActionEffects,
        *,
        activity: DeviceActivity | None,
        evidence: EnforcementEvidence,
        action_scope: str,
        device_id: str,
        now: float,
    ) -> InterruptionDecision:
        level = effects.level()
        user_active = activity.user_active if activity is not None else None
        if (
            activity is not None
            and activity.screen_locked is True
            and level is InterruptionLevel.L1_WARN
        ):
            raise PolicyBlocked(
                "visible or foreground input is refused while the screen is locked",
                code="screen_locked_visible_action_refused",
            )
        if level is InterruptionLevel.L2_CONFIRM and not self.ledger.consume(
            evidence.confirmation_grant_id,
            kind="confirmation",
            action_scope=action_scope,
            device_id=device_id,
            now=now,
        ):
            raise PolicyBlocked(
                "explicit confirmation is required for this action",
                code="interruption_confirmation_required",
            )
        if level is InterruptionLevel.L1_WARN and not self.ledger.consume(
            evidence.warning_receipt_id,
            kind="warning",
            action_scope=action_scope,
            device_id=device_id,
            now=now,
        ):
            raise PolicyBlocked(
                "a user interruption warning must be emitted before dispatch",
                code="interruption_warning_required",
            )
        return InterruptionDecision(
            level=level,
            allowed=True,
            warning_required=level is InterruptionLevel.L1_WARN,
            confirmation_required=level is InterruptionLevel.L2_CONFIRM,
            user_active=user_active,
        )
