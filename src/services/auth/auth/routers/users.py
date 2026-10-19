"""User profile endpoints (spec §3).

Two audiences, two response models. `/users/me` returns the caller their own
record, email and all. `/users/{id}` returns what the SPA needs to draw someone
else — a name and an avatar — and is a separate type rather than the same model
with fields omitted, so that adding a field to the profile model later cannot
quietly start publishing it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import identities, names, preferences
from auth.db import session as db_session
from auth.schemas import PublicUserResponse, UpdateUserRequest, UserResponse
from shared import ProblemException, UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/users", tags=["users"])

# The one sentence a taken name gets, wherever it is detected (register D46).
NAME_TAKEN = "That name is already taken."


@router.get("/me", response_model=UserResponse)
async def me(
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> UserResponse:
    user = await identities.find_user(session, principal.user_id)
    if user is None:
        # A valid token for an account that has since been deleted.
        raise ProblemException.not_found("This account no longer exists.")

    return UserResponse.model_validate(user, from_attributes=True)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UpdateUserRequest,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> UserResponse:
    """Update the caller's own profile.

    Only ever the caller's own: there is no `PATCH /users/{id}`, and the row
    edited comes from the token's `sub`, so there is no id in the request for
    anyone to substitute.

    A field left out is left alone; `avatarAsset: null` clears the avatar. The
    two are told apart by what the request actually carried rather than by
    treating None as "no change", or an avatar could be set but never removed.

    The name is stored trimmed and NFC-composed, and is unique across the
    installation ignoring case, deleted accounts included (register D46). The
    database's unique index is the only referee: a rename that loses a race gets
    the same 409 as one that finds the name already taken, and changes nothing.
    The 409 names nobody — no user, no workspace — whatever holds the name.
    Saving the name you already have is not a write: when nothing else is
    supplied either, `version` and `updated_at` stay as they were.
    """
    user = await identities.find_user(session, principal.user_id)
    if user is None:
        raise ProblemException.not_found("This account no longer exists.")

    supplied = body.model_fields_set
    changed = False
    if "display_name" in supplied:
        if body.display_name is None:
            raise ProblemException.validation_error(
                "displayName cannot be null.",
                errors={"displayName": ["A display name is required"]},
            )
        try:
            name = names.normalise_display_name(body.display_name)
        except names.InvalidDisplayNameError as exc:
            raise ProblemException.validation_error(
                str(exc), errors={"displayName": [str(exc)]}
            ) from exc
        if name != user.display_name:
            user.display_name = name
            changed = True
    if "avatar_asset" in supplied:
        # No existence check against the Asset service: services do not read
        # each other's data, and a synchronous call here would put Asset on the
        # path of a profile edit. A dangling reference renders as no avatar.
        user.avatar_asset = body.avatar_asset
        changed = True

    if not changed:
        return UserResponse.model_validate(user, from_attributes=True)

    user.updated_at = datetime.now(UTC)
    user.version += 1
    try:
        await session.flush()
    except IntegrityError as exc:
        if not identities.is_name_taken(exc):
            raise
        await session.rollback()
        raise ProblemException.conflict(NAME_TAKEN, errors={"displayName": [NAME_TAKEN]}) from exc
    await session.commit()

    return UserResponse.model_validate(user, from_attributes=True)


@router.get("/me/preferences")
async def my_preferences(
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    """The caller's preferences: `{}` until they have saved one. Creates no row."""
    await _require_account(session, principal)
    return await preferences.read(session, principal.user_id)


@router.patch("/me/preferences")
async def update_my_preferences(
    body: dict[str, Any] = Body(...),
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    """Merge a patch into the caller's preferences; `null` removes a key.

    The whole patch is refused if any key is unknown or any value is bad, so a
    400 changes nothing. Only the caller's own row is reachable: the id comes
    from the token. Not in Conventions §5.2's fail-closed set, so it is plain
    `require_user`.
    """
    await _require_account(session, principal)
    try:
        patch = preferences.parse_patch(body)
    except preferences.InvalidPreferencesError as exc:
        raise ProblemException.validation_error(
            "Some preferences are not valid.", errors=exc.errors
        ) from exc

    merged = await preferences.merge(session, principal.user_id, patch)
    await session.commit()
    return merged


async def _require_account(session: AsyncSession, principal: UserPrincipal) -> None:
    if await identities.find_user(session, principal.user_id) is None:
        raise ProblemException.not_found("This account no longer exists.")


@router.get("/{user_id}", response_model=PublicUserResponse)
async def public_profile(
    user_id: uuid.UUID,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> PublicUserResponse:
    """Another user's public profile, for avatars and mentions.

    Restricted to people the caller shares a workspace with. Spec §3 says only
    "Bearer", but every access token is scoped to one workspace (Conventions
    §5.4), and answering for any user in the installation would make a
    workspace-scoped token a directory of every tenant.

    Not found and not visible give the same 404. Distinguishing them would
    confirm that an account exists for an address, which is the fact being
    withheld.
    """
    user = await identities.find_user(session, user_id)
    visible = user is not None and (
        user.id == principal.user_id
        or await identities.shares_workspace(
            session, viewer_id=principal.user_id, subject_id=user.id
        )
    )
    if user is None or not visible:
        raise ProblemException.not_found("No such user.")

    return PublicUserResponse.model_validate(user, from_attributes=True)
