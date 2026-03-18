from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from ..auth_repository import SessionRepository, UserRepository
from ..domain import SessionRecord, UserRecord
from ..security import generate_session_token, hash_password, verify_password


BOOTSTRAP_ADMIN_USERNAME = "admin"
BOOTSTRAP_ADMIN_PASSWORD = "admin123!"
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,50}$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AuthError(Exception):
    """Raised when authentication fails."""


@dataclass(frozen=True)
class AuthenticatedSession:
    session_token: str
    user: UserRecord


class AuthService:
    def __init__(
        self,
        *,
        user_repository: UserRepository,
        session_repository: SessionRepository,
    ) -> None:
        self._user_repository = user_repository
        self._session_repository = session_repository
        self.ensure_bootstrap_admin()

    def ensure_bootstrap_admin(self) -> None:
        if self._user_repository.list_users():
            return
        now = _utc_now()
        self._user_repository.create_user(
            UserRecord(
                id=str(uuid.uuid4()),
                username=BOOTSTRAP_ADMIN_USERNAME,
                password_hash=hash_password(BOOTSTRAP_ADMIN_PASSWORD),
                role="admin",
                is_active=True,
                created_at=now,
                updated_at=now,
                last_login_at=None,
            )
        )

    def authenticate(self, *, username: str, password: str) -> AuthenticatedSession:
        normalized_username = _normalize_username(username)
        user = self._user_repository.find_by_username(normalized_username)
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Invalid username or password.")
        if not user.is_active:
            raise AuthError("This account is disabled.")
        now = _utc_now()
        self._user_repository.update_user(
            user_id=user.id,
            username=user.username,
            password_hash=user.password_hash,
            role=user.role,
            is_active=user.is_active,
            updated_at=now,
            last_login_at=now,
        )
        session_record = SessionRecord(
            id=str(uuid.uuid4()),
            user_id=user.id,
            session_token=generate_session_token(),
            created_at=now,
            updated_at=now,
        )
        self._session_repository.create_session(session_record)
        refreshed_user = self._user_repository.get_user(user.id)
        if refreshed_user is None:
            raise AuthError("Authenticated account could not be reloaded.")
        return AuthenticatedSession(session_token=session_record.session_token, user=refreshed_user)

    def current_session(self, session_token: str) -> AuthenticatedSession:
        normalized_token = session_token.strip()
        if not normalized_token:
            raise AuthError("Missing session token.")
        session_record = self._session_repository.get_session_by_token(normalized_token)
        if session_record is None:
            raise AuthError("Session is not valid.")
        user = self._user_repository.get_user(session_record.user_id)
        if user is None or not user.is_active:
            raise AuthError("Session user is not available.")
        self._session_repository.touch_session(session_record.id, _utc_now())
        return AuthenticatedSession(session_token=normalized_token, user=user)

    def logout(self, session_token: str) -> None:
        self._session_repository.delete_session_by_token(session_token.strip())


class AccountService:
    def __init__(
        self,
        *,
        user_repository: UserRepository,
        session_repository: SessionRepository,
    ) -> None:
        self._user_repository = user_repository
        self._session_repository = session_repository

    def list_accounts(
        self,
        *,
        query: str | None,
        role: str | None,
        is_active: bool | None,
    ) -> list[UserRecord]:
        return self._user_repository.list_users(query=query, role=role, is_active=is_active)

    def save_account(
        self,
        *,
        account_id: str | None,
        username: str,
        role: str,
        is_active: bool,
        password: str | None,
        actor_user: UserRecord,
    ) -> UserRecord:
        normalized_username = _normalize_username(username)
        normalized_role = _normalize_role(role)
        now = _utc_now()
        if account_id is None:
            if password is None:
                raise AuthError("Password is required when creating an account.")
            try:
                self._user_repository.create_user(
                    UserRecord(
                        id=str(uuid.uuid4()),
                        username=normalized_username,
                        password_hash=hash_password(password),
                        role=normalized_role,
                        is_active=is_active,
                        created_at=now,
                        updated_at=now,
                        last_login_at=None,
                    )
                )
            except sqlite3.IntegrityError as exc:
                raise AuthError("Username already exists.") from exc
            created_user = self._user_repository.find_by_username(normalized_username)
            if created_user is None:
                raise AuthError("Created account could not be reloaded.")
            return created_user

        existing_user = self._user_repository.get_user(account_id)
        if existing_user is None:
            raise AuthError("Account was not found.")
        if actor_user.id == existing_user.id and not is_active:
            raise AuthError("You cannot disable your current account.")
        if not is_active and existing_user.role == "admin":
            active_admin_count = self._user_repository.count_admin_users(active_only=True)
            if active_admin_count <= 1:
                raise AuthError("The last active admin account cannot be disabled.")
        password_hash = existing_user.password_hash
        if password is not None and password.strip():
            password_hash = hash_password(password)
        try:
            self._user_repository.update_user(
                user_id=existing_user.id,
                username=normalized_username,
                password_hash=password_hash,
                role=normalized_role,
                is_active=is_active,
                updated_at=now,
                last_login_at=existing_user.last_login_at,
            )
        except sqlite3.IntegrityError as exc:
            raise AuthError("Username already exists.") from exc
        updated_user = self._user_repository.get_user(existing_user.id)
        if updated_user is None:
            raise AuthError("Updated account could not be reloaded.")
        return updated_user

    def delete_account(self, *, account_id: str, actor_user: UserRecord) -> None:
        if actor_user.id == account_id:
            raise AuthError("You cannot delete your own account.")
        existing_user = self._user_repository.get_user(account_id)
        if existing_user is None:
            raise AuthError("Account was not found.")
        if existing_user.role == "admin":
            active_admin_count = self._user_repository.count_admin_users(active_only=True)
            if existing_user.is_active and active_admin_count <= 1:
                raise AuthError("The last active admin account cannot be deleted.")
        self._session_repository.delete_sessions_for_user(account_id)
        self._user_repository.delete_user(account_id)


def _normalize_username(username: str) -> str:
    normalized_username = username.strip().lower()
    if not USERNAME_RE.fullmatch(normalized_username):
        raise AuthError(
            "Username must be 3-50 characters and use only lowercase letters, numbers, dot, dash, or underscore."
        )
    return normalized_username


def _normalize_role(role: str) -> str:
    normalized_role = role.strip().lower()
    if normalized_role not in {"admin", "user"}:
        raise AuthError("Role must be admin or user.")
    return normalized_role
