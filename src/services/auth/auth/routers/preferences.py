"""The caller's own preferences (register D28).

Keyed on the token's `sub`, like `/users/me` — no id in the path or body. Both
routes stay on `require_user`, so they fail open when R1 is unreachable: a clock
setting is not worth a 503.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth import identities, preferences
from auth.db import session as db_session
from auth.schemas import PreferencesResponse
from shared import ProblemException, UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me/preferences", response_model=PreferencesResponse, response_model_exclude_none=True)
async def my_preferences(
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> PreferencesResponse:
    if await identities.find_user(session, principal.user_id) is None:
        raise ProblemException.not_found("This account no longer exists.")

    return PreferencesResponse.model_validate(await preferences.read(session, principal.user_id))


@router.patch(
    "/me/preferences", response_model=PreferencesResponse, response_model_exclude_none=True
)
async def update_my_preferences(
    body: preferences.PreferencesPatch,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> PreferencesResponse:
    """Set or remove keys; `{}` writes nothing. Answers with the merged object."""
    if await identities.find_user(session, principal.user_id) is None:
        raise ProblemException.not_found("This account no longer exists.")

    to_set, to_remove = preferences.split(body)
    if to_set or to_remove:
        stored = await preferences.merge(session, principal.user_id, to_set, to_remove)
        await session.commit()
    else:
        stored = await preferences.read(session, principal.user_id)

    return PreferencesResponse.model_validate(stored)
