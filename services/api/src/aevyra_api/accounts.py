"""First-party opaque sessions; Redis limits fail closed if infrastructure is unavailable."""

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Protocol
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.codes import aware
from aevyra_api.credits.models import AccountSession, User, Wallet

OWNER_LOGIN = "owner_god"  # Reserved; only the terminal can provision this identity.
COOKIE = "auvylen_session"
CSRF_COOKIE = "auvylen_csrf"
HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
# Equal work for an unknown identifier; never use a fast path to expose account existence.
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))


def pepper(config: Settings) -> str:
    if config.redemption_code_pepper is not None:
        return config.redemption_code_pepper.get_secret_value()
    if config.api_environment == "test":
        return "test-only-pepper-not-for-a-deployment"
    raise DomainError("Account configuration unavailable", 503)


def csrf_token(token: str, config: Settings) -> str:
    return hmac.new(pepper(config).encode(), ("csrf:" + token).encode(), hashlib.sha256).hexdigest()


def session_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class RateLimiter(Protocol):
    def check(self, key: str, limit: int, seconds: int) -> None: ...


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    def check(self, key: str, limit: int, seconds: int) -> None:
        try:
            count = self.redis.eval(
                "local n=redis.call('INCR',KEYS[1]); "
                "if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
                1,
                "auvylen:rate:" + key,
                seconds,
            )
        except RedisError:
            raise DomainError("Please try again later", 503) from None
        if int(count) > limit:
            raise DomainError("Too many attempts; please try again later", 429)


class AccountService:
    def __init__(self, sessions: sessionmaker[Session], config: Settings) -> None:
        self.sessions = sessions
        self.config = config

    def authenticate(self, token: str | None) -> User:
        if token is None or len(token) > 100:
            raise DomainError("Sign in required", 401)
        with self.sessions() as session:
            stored = session.scalar(
                select(AccountSession).where(AccountSession.token_digest == session_digest(token))
            )
            user = session.get(User, stored.user_id) if stored else None
            if (
                stored is None
                or aware(stored.expires_at) <= now()
                or user is None
                or user.disabled_at is not None
            ):
                raise DomainError("Sign in required", 401)
            return user

    def register(self, identifier: str, password: str) -> tuple[User, str]:
        if identifier.strip().lower() == OWNER_LOGIN:
            raise DomainError("Account could not be created with this identifier", 409)
        hashed = HASHER.hash(password)
        try:
            with self.sessions.begin() as session:
                user = User(
                    public_user_id="usr_" + uuid4().hex,
                    login_identifier=identifier,
                    password_hash=hashed,
                )
                session.add(user)
                session.flush()
                session.add(Wallet(user_id=user.id))
                token = self._session(session, user.id)
            return user, token
        except IntegrityError:
            raise DomainError("Account could not be created with this identifier", 409) from None

    def login(self, identifier: str, password: str) -> tuple[User, str]:
        with self.sessions.begin() as session:
            user = session.scalar(select(User).where(User.login_identifier == identifier))
            try:
                HASHER.verify(user.password_hash if user else DUMMY_HASH, password)
            except VerificationError:
                raise DomainError("Invalid login credentials", 401) from None
            if user is None or user.disabled_at is not None:
                raise DomainError("Invalid login credentials", 401)
            if HASHER.check_needs_rehash(user.password_hash):
                user.password_hash = HASHER.hash(password)
            # Discard expired sessions for this user; logout removes the current session.
            session.execute(
                delete(AccountSession).where(
                    AccountSession.user_id == user.id, AccountSession.expires_at <= now()
                )
            )
            return user, self._session(session, user.id)

    def _session(self, session: Session, user_id: UUID) -> str:
        token = secrets.token_urlsafe(32)
        session.add(
            AccountSession(
                user_id=user_id,
                token_digest=session_digest(token),
                expires_at=now() + timedelta(seconds=self.config.session_lifetime_seconds),
            )
        )
        return token

    def logout(self, token: str) -> None:
        with self.sessions.begin() as session:
            session.execute(
                delete(AccountSession).where(AccountSession.token_digest == session_digest(token))
            )
