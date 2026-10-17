"""User profile endpoints (spec §3).

Two audiences, two response models. `/users/me` returns the caller their own
record, email and all. `/users/{id}` returns what the SPA needs to draw someone
else — a name and an avatar — and is a separate type rather than the same model
with fields omitted, so that adding a field to the profile model later cannot
quietly start publishing it.

`/users/me/preferences` holds the caller's stored choices (register D28); it is
declared before `/{user_id}` so `me` is not read as an id.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth import identities, names, preferences
from auth.db import session as db_session
from auth.schemas import PublicUserResponse, UpdateUserRequest, UserResponse
from shared import ProblemException, UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/users", tags=["users"])

# The whole 409 body: it names nobody and no workspace (D46, Conventions §5.4).
TAKEN = "That name is already taken."
GONE = "This account no longer exists."


@router.get("/me", response_model=UserResponse)
async def me(
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> UserResponse:
    user = await identities.find_user(session, principal.user_id)
    if user is None:
        # A valid token for an account that has since been deleted.
        raise ProblemException.not_found(GONE)

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

    The display name is normalised by `auth.names` (trimmed, NFC, 1 to 100 code
    points, no invisible characters → 400) and unique across CollabHub, deleted
    accounts included (register D46 → 409 that names nobody). Saving the name you
    already have is a 200 that writes nothing.

    A field left out is left alone; `avatarAsset: null` clears the avatar. The
    two are told apart by what the request actually carried rather than by
    treating None as "no change", or an avatar could be set but never removed.
    """
    user = await identities.find_user(session, principal.user_id)
    if user is None:
        raise ProblemException.not_found("This account no longer exists.")

    supplied = body.model_fields_set
    written = False
    if "display_name" in supplied:
        if body.display_name is None:
            raise ProblemException.validation_error(
                "displayName cannot be null.",
                errors={"displayName": ["A display name is required"]},
            )
        # Saving the name you already have writes nothing, and is checked before
        # the character rules: a legacy name the migration kept (it only trims and
        # composes) must still be savable unchanged.
        if names.stored_form(body.display_name) != user.display_name:
            try:
                name = names.normalise_display_name(body.display_name)
            except names.InvalidNameError as exc:
                raise ProblemException.validation_error(
                    str(exc), errors={"displayName": [str(exc)]}
                ) from exc
            try:
                written = await identities.rename_user(session, user, name)
            except identities.NameTakenError as exc:
                # Names nobody: the sentence is fixed (D46, Conventions §5.4).
                raise ProblemException.conflict(TAKEN, errors={"displayName": [TAKEN]}) from exc
    if "avatar_asset" in supplied and body.avatar_asset != user.avatar_asset:
        # No existence check against the Asset service: services do not read
        # each other's data, and a synchronous call here would put Asset on the
        # path of a profile edit. A dangling reference renders as no avatar.
        user.avatar_asset = body.avatar_asset
        if not written:
            user.updated_at = datetime.now(UTC)
            user.version += 1

    await session.commit()

    return UserResponse.model_validate(user, from_attributes=True)


@router.get("/me/preferences")
async def my_preferences(
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    """The caller's stored preferences, `{}` if they have chosen nothing.

    Declared before `/{user_id}`, which would otherwise take `me` for an id.
    """
    if await identities.find_user(session, principal.user_id) is None:
        raise ProblemException.not_found(GONE)
    return await preferences.read(session, principal.user_id)


@router.patch("/me/preferences")
async def update_my_preferences(
    body: dict[str, Any],
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    """Merge a patch into the caller's preferences; `null` puts a key back to automatic.

    The body is a plain object so that `auth.preferences.parse_patch` is the one
    place it is validated, unknown keys and all. Nothing is applied unless every
    key is valid.
    """
    if await identities.find_user(session, principal.user_id) is None:
        raise ProblemException.not_found(GONE)
    try:
        patch = preferences.parse_patch(body)
    except preferences.InvalidPreferencesError as exc:
        raise ProblemException.validation_error(
            "Some preferences are invalid.", errors=exc.errors
        ) from exc

    stored = await preferences.apply_patch(session, principal.user_id, patch)
    await session.commit()
    return stored


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
