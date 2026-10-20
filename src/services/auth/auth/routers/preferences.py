"""The caller's preferences (register D28; issue gh-3, Req 6).

Per user and global — never per workspace — and keyed by the token's `sub`, so
there is no id in the request. The keys the server accepts are `auth.preferences.KEYS`.
Both routes fail open with the token denylist down, like every ordinary route.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth import identities, preferences
from auth.db import session as db_session
from shared import ProblemException, UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/users/me/preferences", tags=["users"])


@router.get("")
async def read_preferences(
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    """The stored map, `{}` for a user with none. Reading never creates a row."""
    if await identities.find_user(session, principal.user_id) is None:
        raise ProblemException.not_found("This account no longer exists.")
    return await preferences.read(session, principal.user_id)


@router.patch("")
async def update_preferences(
    body: dict[str, Any] = Body(...),
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    """Merge the keys in the body; `null` removes one. All or nothing.

    Every bad key is reported at once under `errors.<key>`, and nothing is
    written if any is. An empty patch reads and writes nothing.
    """
    if await identities.find_user(session, principal.user_id) is None:
        raise ProblemException.not_found("This account no longer exists.")

    try:
        patch = preferences.parse_patch(body)
    except preferences.InvalidPreferencesError as exc:
        raise ProblemException.validation_error(
            "Some preferences are invalid.", errors=exc.errors
        ) from exc

    if not patch.set and not patch.remove:
        return await preferences.read(session, principal.user_id)
    return await preferences.apply(session, principal.user_id, patch)
