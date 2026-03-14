"""Registry of active calls for runtime tenant configuration propagation."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.services.tenant_runtime import TenantRuntimeConfig

if TYPE_CHECKING:
    from app.voice.realtime import RealtimeSession
    from app.voice.session import CallSession

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ActiveCallBinding:
    tenant_id: str
    session: "CallSession"
    realtime: "RealtimeSession"


_calls_by_sid: dict[str, ActiveCallBinding] = {}
_call_sids_by_tenant: dict[str, set[str]] = defaultdict(set)


def register_call(
    call_sid: str,
    tenant_id: str,
    session: "CallSession",
    realtime: "RealtimeSession",
) -> None:
    _calls_by_sid[call_sid] = ActiveCallBinding(
        tenant_id=tenant_id,
        session=session,
        realtime=realtime,
    )
    _call_sids_by_tenant[tenant_id].add(call_sid)


def unregister_call(call_sid: str) -> None:
    binding = _calls_by_sid.pop(call_sid, None)
    if not binding:
        return

    call_sids = _call_sids_by_tenant.get(binding.tenant_id)
    if not call_sids:
        return

    call_sids.discard(call_sid)
    if not call_sids:
        _call_sids_by_tenant.pop(binding.tenant_id, None)


async def propagate_tenant_config(
    tenant_id: str,
    config: TenantRuntimeConfig | None,
) -> None:
    if not config:
        return

    call_sids = list(_call_sids_by_tenant.get(tenant_id, ()))
    if not call_sids:
        return

    logger.info(
        "Propagating tenant runtime update to %d active call(s) for tenant %s",
        len(call_sids),
        tenant_id,
    )
    for call_sid in call_sids:
        binding = _calls_by_sid.get(call_sid)
        if not binding:
            continue
        binding.session.apply_runtime_config(config)
        await binding.realtime.apply_tenant_config(config)
