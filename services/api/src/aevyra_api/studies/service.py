"""Transactional consent collection. External holdouts have no development export path."""

import hashlib
import hmac
import json
import logging
import secrets
from datetime import timedelta
from typing import Literal, cast
from uuid import UUID, uuid4

from aevyra_contracts.studies import (
    AssignmentView,
    ConsentPublish,
    ConsentView,
    MemberReview,
    MemberView,
    PhotoReview,
    PhotoUpload,
    PhotoView,
    RatingSubmit,
    StudyAction,
    StudyCreate,
    StudyJoin,
    StudyView,
)
from pydantic import JsonValue
from sqlalchemy import func, literal, or_, select, text
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.accounts import pepper, session_digest
from aevyra_api.admin_models import AdminAudit
from aevyra_api.administration import audit
from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.codes import aware
from aevyra_api.credits.models import AccountSession, User
from aevyra_api.entitlements import is_owner, product_access, require_owner
from aevyra_api.preferences.images import DecodedImage
from aevyra_api.research.storage import PrivateArtifactStore
from aevyra_api.studies.models import (
    Assignment,
    ConsentVersion,
    Member,
    Person,
    Photo,
    Receipt,
    Study,
    StudyAudit,
    StudyExport,
    StudyGarbage,
)


class Studies:
    def __init__(self, sessions: sessionmaker[Session], settings: Settings):
        self.sessions, self.settings = sessions, settings

    def actor_ref(self, study_id: UUID, user_id: UUID) -> str:
        return hmac.new(
            pepper(self.settings).encode(),
            f"study-actor-v1:{study_id}:{user_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

    def log(
        self,
        session: Session,
        user_id: UUID,
        study_id: UUID,
        action: str,
        details: dict[str, object],
        request_key: UUID | None = None,
    ) -> None:
        session.add(
            StudyAudit(
                study_id=study_id,
                actor_ref=self.actor_ref(study_id, user_id),
                action=action,
                request_key=None if request_key is None else str(request_key),
                details=details,
            )
        )

    def retire(self, session: Session, study: Study, namespace: str, artifact: UUID) -> None:
        if not session.scalar(select(StudyGarbage.id).where(StudyGarbage.artifact_id == artifact)):
            session.add(StudyGarbage(study_id=study.id, namespace=namespace, artifact_id=artifact))

    def drain(self, study_id: UUID | None = None) -> int:
        with self.sessions.begin() as session:
            query = (
                select(StudyGarbage)
                .order_by(StudyGarbage.id)
                .limit(1000)
                .with_for_update(skip_locked=True)
            )
            if study_id is not None:
                query = query.where(StudyGarbage.study_id == study_id)
            for row in session.scalars(query):
                if row.namespace not in {"study-development", "study-holdout", "study-exports"}:
                    raise ValueError("Invalid erasure namespace")
                try:
                    PrivateArtifactStore(self.settings.private_upload_root / row.namespace).delete(
                        row.study_id, row.artifact_id
                    )
                except OSError as exc:
                    logging.getLogger("aevyra.collection").warning(
                        "study_erasure_retry", extra={"error_type": type(exc).__name__}
                    )
                else:
                    session.delete(row)
            session.flush()
            count = select(func.count()).select_from(StudyGarbage)
            if study_id is not None:
                count = count.where(StudyGarbage.study_id == study_id)
            return session.scalar(count) or 0

    def collection_lock(self, session: Session) -> None:
        # Serialize global proof/duplicate checks and the disk budget across studies.
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_xact_lock(714001)"))

    def enabled(self) -> None:
        if (
            not self.settings.study_collection_enabled
            or not self.settings.research_mode
            or self.settings.public_pilot
        ):
            raise DomainError("study_disabled", 503)

    def collection_open(self, study: Study) -> None:
        if not study.fixture_only and not self.settings.study_real_collection_enabled:
            raise DomainError("study_real_paused", 503)

    def store(self, study: Study) -> PrivateArtifactStore:
        return PrivateArtifactStore(
            self.settings.private_upload_root / ("study-" + study.partition)
        )

    def export_store(self) -> PrivateArtifactStore:
        return PrivateArtifactStore(
            self.settings.private_upload_root / "study-exports", 64 * 1024**2
        )

    def lock_user(self, session: Session, user_id: UUID) -> User:
        user = session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None or user.disabled_at is not None:
            raise DomainError("Sign in required", 401)
        return user

    def fresh(self, session: Session, user: User, token: str) -> None:
        auth = session.scalar(
            select(AccountSession).where(
                AccountSession.user_id == user.id,
                AccountSession.token_digest == session_digest(token),
            )
        )
        if auth is None or aware(auth.expires_at) <= now():
            raise DomainError("Sign in required", 401)
        if aware(auth.created_at) < now() - timedelta(
            seconds=self.settings.owner_fresh_auth_seconds
        ):
            raise DomainError("study_fresh_signin", 403)

    def study(self, session: Session, study_id: UUID) -> Study:
        study = session.scalar(select(Study).where(Study.id == study_id).with_for_update())
        if study is None:
            raise DomainError("study_not_found", 404)
        return study

    def consent(self, session: Session, study_id: UUID) -> ConsentVersion:
        item = session.scalar(
            select(ConsentVersion)
            .where(ConsentVersion.study_id == study_id)
            .order_by(ConsentVersion.version.desc())
            .limit(1)
        )
        if item is None:
            raise DomainError("study_consent_required", 409)
        return item

    def person(self, session: Session, user_id: UUID) -> Person | None:
        return session.scalar(select(Person).where(Person.user_id == user_id))

    def memberships(self, session: Session, study: Study, user: User) -> list[Member]:
        return list(
            session.scalars(
                select(Member)
                .join(Person)
                .where(Member.study_id == study.id, Person.user_id == user.id)
            )
        )

    def manages(self, session: Session, study: Study, user: User) -> bool:
        if study.partition == "development":
            return is_owner(user)
        # The Owner privilege is deliberately insufficient for holdout contents/labels.
        return bool(
            not is_owner(user)
            and study.custodian_id == user.id
            and any(
                m.role == "custodian" and m.active and m.approved
                for m in self.memberships(session, study, user)
            )
        )

    def manager(self, session: Session, study: Study, user: User, token: str | None = None) -> None:
        if not self.manages(session, study, user):
            raise DomainError("study_custody_required", 403)
        if token is not None:
            self.fresh(session, user, token)

    def member(
        self, session: Session, study: Study, user: User, role: str, *, current: bool = True
    ) -> Member:
        members = self.memberships(session, study, user)
        item = next((m for m in members if m.role == role and m.active), None)
        if item is None or not product_access(user, standard_allowed=True) or not item.approved:
            raise DomainError("study_member_approval_required", 403)
        if current and item.consent_id != self.consent(session, study.id).id:
            raise DomainError("study_consent_changed", 409)
        return item

    def recorded(
        self,
        session: Session,
        user: User,
        key: UUID,
        action: str,
        body: object,
        details: dict[str, JsonValue] | None = None,
    ) -> AdminAudit | None:
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
        old = session.scalar(select(AdminAudit).where(AdminAudit.request_key == str(key)))
        if old is not None:
            if old.actor_id != user.id or old.action != action or old.fingerprint != digest:
                raise DomainError("study_request_conflict", 409)
            return old
        session.add(
            AdminAudit(
                actor_id=user.id,
                action=action,
                target="collection",
                outcome="success",
                request_key=str(key),
                fingerprint=digest,
                details=details or {},
            )
        )
        return None

    def invalidate(self, session: Session, study: Study, reason: str) -> None:
        study.revision += 1
        if study.seal_sha256:
            audit(
                session,
                None,
                "study.seal_invalidated",
                str(study.id),
                details={"seal": study.seal_sha256, "reason": reason},
            )
            session.add(
                StudyAudit(
                    study_id=study.id,
                    actor_ref="system",
                    action="study.seal_invalidated",
                    details={"seal_sha256": study.seal_sha256, "reason": reason},
                )
            )
            study.seal_sha256 = None
            study.status = "CLOSED"
        for export in session.scalars(
            select(StudyExport).where(
                StudyExport.study_id == study.id, StudyExport.status == "ACTIVE"
            )
        ):
            if export.artifact_id:
                self.retire(session, study, "study-exports", export.artifact_id)
            export.artifact_id, export.status = None, "REVOKED"

    def create(self, user_id: UUID, token: str, body: StudyCreate) -> UUID:
        self.enabled()
        if not body.fixture_only and not self.settings.study_real_collection_enabled:
            raise DomainError("study_fixture_only", 403)
        with self.sessions.begin() as session:
            user = self.lock_user(session, user_id)
            require_owner(user)
            self.fresh(session, user, token)
            new_id = uuid4()
            old = self.recorded(
                session,
                user,
                body.idempotency_key,
                "study.create",
                body.model_dump(mode="json"),
                {"study_id": str(new_id)},
            )
            if old:
                return UUID(str(old.details["study_id"]))
            if (session.scalar(select(func.count()).select_from(Study)) or 0) >= 30:
                raise DomainError("study_limit", 429)
            custodian = None
            if body.partition == "holdout":
                custodian = session.scalar(
                    select(User).where(User.public_user_id == body.custodian_public_id)
                )
                if custodian is None or is_owner(custodian) or custodian.disabled_at is not None:
                    raise DomainError("study_custodian_required", 422)
                person = self.person(session, custodian.id)
                if person and person.partition != "holdout":
                    raise DomainError("study_partition_locked", 409)
            study = Study(
                id=new_id,
                owner_id=user.id,
                title=body.title,
                partition=body.partition,
                custodian_id=None if custodian is None else custodian.id,
                fixture_only=body.fixture_only,
                retention_days=body.retention_days,
            )
            session.add(study)
            session.flush()
            return study.id

    def publish(self, user_id: UUID, study_id: UUID, token: str, body: ConsentPublish) -> None:
        self.enabled()
        with self.sessions.begin() as session:
            user = self.lock_user(session, user_id)
            require_owner(user)
            self.fresh(session, user, token)
            study = self.study(session, study_id)
            if study.sealed_at is not None:
                raise DomainError("study_sealed", 409)
            if self.recorded(
                session,
                user,
                body.idempotency_key,
                "study.consent",
                {"study": str(study.id), **body.model_dump(mode="json")},
            ):
                return
            number = (
                session.scalar(
                    select(func.max(ConsentVersion.version)).where(
                        ConsentVersion.study_id == study.id
                    )
                )
                or 0
            ) + 1
            texts = body.model_dump(exclude={"idempotency_key"})
            policy = {
                "study_id": str(study.id),
                "partition": study.partition,
                "fixture_only": study.fixture_only,
                "retention_days": study.retention_days,
                "version": number,
                **texts,
            }
            digest = hashlib.sha256(
                json.dumps(policy, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            session.add(ConsentVersion(study_id=study.id, version=number, sha256=digest, **texts))
            self.log(
                session,
                user.id,
                study.id,
                "study.consent_published",
                {"version": number, "sha256": digest},
            )
            study.status = "PAUSED"
            # New work must capture the newly accepted version, never an old pending lease.
            for assignment in session.scalars(
                select(Assignment).where(
                    Assignment.study_id == study.id, Assignment.status == "ASSIGNED"
                )
            ):
                assignment.status = "CANCELLED"
            self.invalidate(session, study, "consent_version")

    def action(self, user_id: UUID, study_id: UUID, token: str, body: StudyAction) -> str | None:
        self.enabled()
        with self.sessions.begin() as session:
            user = self.lock_user(session, user_id)
            study = self.study(session, study_id)
            self.fresh(session, user, token)
            if body.action == "seal":
                self.manager(session, study, user)
                if study.partition != "holdout" or study.status != "CLOSED" or study.sealed_at:
                    raise DomainError("study_seal_requires_closed_holdout", 409)
            else:
                require_owner(user)
                if study.sealed_at:
                    raise DomainError("study_sealed", 409)
            if self.recorded(
                session,
                user,
                body.idempotency_key,
                "study.action",
                {"study": str(study.id), **body.model_dump(mode="json")},
            ):
                if body.action == "rotate_invite":
                    raise DomainError("study_invite_already_issued", 409)
                return study.seal_sha256
            self.log(
                session,
                user.id,
                study.id,
                "study.governance",
                {"action": body.action, "reason": body.reason},
            )
            if body.action == "rotate_invite":
                code = secrets.token_urlsafe(36)
                study.invite_digest = self.invite_digest(code)
                return code
            if body.action == "open":
                self.consent(session, study.id)
                if study.partition == "holdout":
                    custodian = session.get(User, study.custodian_id)
                    if custodian is None or not self.manages(session, study, custodian):
                        raise DomainError("study_custodian_required", 409)
                study.status = "OPEN"
            elif body.action in {"pause", "close"}:
                study.status = "PAUSED" if body.action == "pause" else "CLOSED"
                for assignment in session.scalars(
                    select(Assignment).where(
                        Assignment.study_id == study.id, Assignment.status == "ASSIGNED"
                    )
                ):
                    assignment.status = "CANCELLED"
            else:
                from aevyra_api.studies.exports import eligible

                eligible_rows = eligible(session, study)
                rows = [p for p, _ in eligible_rows]
                ratings = [a for _, votes in eligible_rows for a in votes]
                if not rows or not ratings:
                    raise DomainError("study_no_eligible_data", 409)
                # Only the digest is returned; no holdout labels/identities leave custody.
                snapshot = {
                    "study": str(study.id),
                    "revision": study.revision,
                    "photos": [
                        (
                            str(p.id),
                            str(cast(Member, session.get(Member, p.member_id)).person_id),
                            p.sha256,
                            p.artifact_sha256,
                            str(p.consent_id),
                            p.pose,
                            p.lighting,
                        )
                        for p in rows
                    ],
                    "ratings": [
                        (
                            str(a.id),
                            str(a.photo_id),
                            str(cast(Member, session.get(Member, a.member_id)).person_id),
                            a.score,
                            str(a.consent_id),
                        )
                        for a in ratings
                    ],
                }
                digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
                self.log(
                    session,
                    user.id,
                    study.id,
                    "study.sealed",
                    {"sha256": digest, "images": len(rows), "ratings": len(ratings)},
                )
                study.seal_sha256, study.sealed_at, study.status = digest, now(), "SEALED"
                audit(
                    session,
                    user.id,
                    "study.seal",
                    str(study.id),
                    details={"sha256": digest, "images": len(rows), "ratings": len(ratings)},
                )
                return digest
            self.invalidate(session, study, "state_changed")
            return None

    def invite_digest(self, code: str) -> str:
        return hmac.new(
            pepper(self.settings).encode(), ("study-invite-v1:" + code).encode(), hashlib.sha256
        ).hexdigest()

    def resolve(self, user_id: UUID, code: str) -> StudyView:
        self.enabled()
        with self.sessions() as session:
            user = session.get(User, user_id)
            assert user is not None
            study = session.scalar(
                select(Study).where(Study.invite_digest == self.invite_digest(code))
            )
            if study is None or study.status not in {"OPEN", "PAUSED", "DRAFT"}:
                raise DomainError("study_invite_invalid", 404)
            return self.view(session, study, user, invited=True)

    def join(self, user_id: UUID, body: StudyJoin) -> UUID:
        self.enabled()
        with self.sessions.begin() as session:
            user = self.lock_user(session, user_id)
            study = session.scalar(
                select(Study)
                .where(Study.invite_digest == self.invite_digest(body.invite_code))
                .with_for_update()
            )
            if study is None or (
                study.status != "OPEN"
                and not (body.role == "custodian" and study.status in {"DRAFT", "PAUSED"})
            ):
                raise DomainError("study_invite_invalid", 404)
            if study.fixture_only and not body.fixture_confirmed:
                raise DomainError("study_fixture_only", 422)
            if not study.fixture_only and not self.settings.study_real_collection_enabled:
                raise DomainError("study_fixture_only", 403)
            consent = self.consent(session, study.id)
            if consent.id != body.consent_id or not hmac.compare_digest(
                consent.sha256, body.consent_sha256
            ):
                raise DomainError("study_consent_changed", 409)
            if study.partition == "holdout" and is_owner(user):
                raise DomainError("study_custody_required", 403)
            if body.role == "custodian" and (
                study.partition != "holdout" or study.custodian_id != user.id
            ):
                raise DomainError("study_custody_required", 403)
            person = self.person(session, user.id)
            if person and person.partition != study.partition:
                raise DomainError("study_partition_locked", 409)
            if person is None:
                person = Person(user_id=user.id, partition=study.partition)
                session.add(person)
                session.flush()
            item = session.scalar(
                select(Member).where(
                    Member.study_id == study.id,
                    Member.person_id == person.id,
                    Member.role == body.role,
                )
            )
            if item and not item.active:
                raise DomainError("study_withdrawn", 409)
            if item is None:
                if (
                    session.scalar(
                        select(func.count()).select_from(Member).where(Member.study_id == study.id)
                    )
                    or 0
                ) >= 1000:
                    raise DomainError("study_limit", 429)
                item = Member(
                    study_id=study.id,
                    person_id=person.id,
                    role=body.role,
                    consent_id=consent.id,
                    approved=body.role == "custodian",
                )
                session.add(item)
                session.flush()
            if item.consent_id != consent.id or not session.scalar(
                select(Receipt.id).where(
                    Receipt.member_id == item.id, Receipt.consent_id == consent.id
                )
            ):
                item.consent_id = consent.id
                session.add(Receipt(member_id=item.id, consent_id=consent.id))
                self.log(
                    session,
                    user.id,
                    study.id,
                    "study.consent_accepted",
                    {"member": str(item.id), "consent": consent.sha256, "role": body.role},
                )
            return item.id

    def view(
        self, session: Session, study: Study, user: User, *, invited: bool = False
    ) -> StudyView:
        own = self.memberships(session, study, user)
        admin = is_owner(user)
        manages = self.manages(session, study, user)
        if not (invited or own or admin or study.custodian_id == user.id):
            raise DomainError("study_not_found", 404)
        consent = session.scalar(
            select(ConsentVersion)
            .where(ConsentVersion.study_id == study.id)
            .order_by(ConsentVersion.version.desc())
            .limit(1)
        )
        photos = list(
            session.scalars(
                select(Photo)
                .where(
                    Photo.study_id == study.id,
                    Photo.review != "DELETED",
                    or_(Photo.member_id.in_([m.id for m in own]), literal(manages)),
                )
                .order_by(Photo.created_at)
            )
        )
        members = (
            list(session.scalars(select(Member).where(Member.study_id == study.id)))
            if manages
            else []
        )

        def member_view(m: Member) -> MemberView:
            return MemberView(
                id=m.id,
                role=m.role,
                approved=m.approved,
                active=m.active,
                verification_reference=m.verification_reference if manages else None,
            )

        rating_counts = dict(
            session.execute(
                select(Assignment.photo_id, func.count())
                .where(
                    Assignment.study_id == study.id,
                    Assignment.status == "SAVED",
                    Assignment.repeat.is_(False),
                )
                .group_by(Assignment.photo_id)
            ).all()
        )
        return StudyView(
            id=study.id,
            title=study.title,
            partition=cast(Literal["development", "holdout"], study.partition),
            status=study.status,
            fixture_only=study.fixture_only,
            retention_days=study.retention_days,
            can_manage=manages,
            can_administer=admin,
            revision=study.revision,
            consent=None
            if consent is None
            else ConsentView(**{k: getattr(consent, k) for k in ConsentView.model_fields}),
            memberships=[member_view(m) for m in own],
            members=[member_view(m) for m in members],
            photos=[
                PhotoView(
                    id=p.id,
                    review=p.review,
                    pose=p.pose,
                    lighting=p.lighting,
                    rating_count=rating_counts.get(p.id, 0),
                    created_at=p.created_at,
                )
                for p in photos
            ],
            seal_sha256=study.seal_sha256,
            photo_count=session.scalar(
                select(func.count())
                .select_from(Photo)
                .where(Photo.study_id == study.id, Photo.artifact_id.is_not(None))
            )
            or 0,
            rating_count=sum(rating_counts.values()),
        )

    def list_studies(self, user_id: UUID) -> list[StudyView]:
        with self.sessions() as session:
            user = session.get(User, user_id)
            assert user is not None
            own = select(Member.study_id).join(Person).where(Person.user_id == user.id)
            studies = session.scalars(
                select(Study)
                .where(
                    or_(Study.id.in_(own), Study.custodian_id == user.id, literal(is_owner(user)))
                )
                .order_by(Study.created_at.desc())
                .limit(30)
            )
            return [self.view(session, s, user) for s in studies]

    def get(self, user_id: UUID, study_id: UUID) -> StudyView:
        with self.sessions() as session:
            user = session.get(User, user_id)
            assert user is not None
            return self.view(session, self.study(session, study_id), user)

    def review_member(
        self, user_id: UUID, study_id: UUID, member_id: UUID, token: str, body: MemberReview
    ) -> None:
        self.enabled()
        with self.sessions.begin() as session:
            user = self.lock_user(session, user_id)
            study = self.study(session, study_id)
            self.manager(session, study, user, token)
            if study.sealed_at:
                raise DomainError("study_sealed", 409)
            member = session.get(Member, member_id)
            if (
                member is None
                or member.study_id != study.id
                or not member.active
                or member.role == "custodian"
            ):
                raise DomainError("study_not_found", 404)
            if self.recorded(
                session,
                user,
                body.idempotency_key,
                "study.member_review",
                {"member": str(member.id), **body.model_dump(mode="json")},
            ):
                return
            self.collection_lock(session)
            person = session.get(Person, member.person_id)
            assert person is not None
            if body.approved:
                digest = hmac.new(
                    pepper(self.settings).encode(),
                    ("study-person-v1:" + body.verification_reference.casefold()).encode(),
                    hashlib.sha256,
                ).hexdigest()
                duplicate = session.scalar(
                    select(Person.id).where(
                        Person.identity_digest == digest, Person.id != person.id
                    )
                )
                if duplicate or (person.identity_digest and person.identity_digest != digest):
                    raise DomainError("study_duplicate_person", 409)
                person.identity_digest = digest
            member.approved, member.verification_reference = (
                body.approved,
                body.verification_reference,
            )
            if not body.approved:
                photo_ids = select(Photo.id).where(Photo.member_id == member.id)
                for a in session.scalars(
                    select(Assignment).where(
                        Assignment.status == "ASSIGNED",
                        or_(Assignment.member_id == member.id, Assignment.photo_id.in_(photo_ids)),
                    )
                ):
                    a.status = "CANCELLED"
            self.log(
                session,
                user.id,
                study.id,
                "study.member_review",
                {"member": str(member.id), "approved": body.approved},
            )
            self.invalidate(session, study, "member_review")

    def check_upload(self, user_id: UUID, study_id: UUID, body: PhotoUpload) -> None:
        self.enabled()
        with self.sessions() as session:
            user = session.get(User, user_id)
            assert user is not None
            study = self.study(session, study_id)
            self.collection_open(study)
            if study.status != "OPEN":
                raise DomainError("study_closed", 409)
            self.member(session, study, user, "contributor")
            if study.fixture_only and not body.fixture_confirmed:
                raise DomainError("study_fixture_only", 422)

    def upload(
        self, user_id: UUID, study_id: UUID, body: PhotoUpload, decoded: DecodedImage
    ) -> PhotoView:
        self.enabled()
        if min(decoded.width, decoded.height) < 224:
            raise DomainError("study_image_size", 422)
        artifact = None
        with self.sessions.begin() as session:
            user = self.lock_user(session, user_id)
            study = self.study(session, study_id)
            self.collection_open(study)
            if study.status != "OPEN":
                raise DomainError("study_closed", 409)
            member = self.member(session, study, user, "contributor")
            if study.fixture_only and not body.fixture_confirmed:
                raise DomainError("study_fixture_only", 422)
            previous = session.scalar(
                select(Photo).where(
                    Photo.member_id == member.id, Photo.request_key == str(body.idempotency_key)
                )
            )
            if previous:
                if (
                    previous.sha256 != decoded.content_hash
                    or previous.pose != body.pose
                    or previous.lighting != body.lighting
                ):
                    raise DomainError("study_request_conflict", 409)
                return PhotoView(
                    id=previous.id,
                    review=previous.review,
                    pose=previous.pose,
                    lighting=previous.lighting,
                    rating_count=0,
                    created_at=previous.created_at,
                )
            self.collection_lock(session)
            count = (
                session.scalar(
                    select(func.count()).select_from(Photo).where(Photo.artifact_id.is_not(None))
                )
                or 0
            )
            own = (
                session.scalar(
                    select(func.count())
                    .select_from(Photo)
                    .where(Photo.member_id == member.id, Photo.artifact_id.is_not(None))
                )
                or 0
            )
            # Physically pending erasures still consume disk budget until the outbox drains.
            pending = (
                session.scalar(
                    select(func.count())
                    .select_from(StudyGarbage)
                    .where(StudyGarbage.namespace.in_(["study-development", "study-holdout"]))
                )
                or 0
            )
            if count + pending >= self.settings.study_max_photos or own >= 6:
                raise DomainError("study_limit", 429)
            if session.scalar(select(Photo.id).where(Photo.sha256 == decoded.content_hash)):
                raise DomainError("study_duplicate_image", 409)
            artifact, artifact_sha = self.store(study).put(study.id, decoded.image)
            try:
                photo = Photo(
                    study_id=study.id,
                    member_id=member.id,
                    consent_id=member.consent_id,
                    request_key=str(body.idempotency_key),
                    artifact_id=artifact,
                    sha256=decoded.content_hash,
                    artifact_sha256=artifact_sha,
                    pose=body.pose,
                    lighting=body.lighting,
                    expires_at=now() + timedelta(days=study.retention_days),
                )
                session.add(photo)
                session.flush()
                self.log(
                    session,
                    user.id,
                    study.id,
                    "study.photo_submitted",
                    {"photo": str(photo.id)},
                )
                self.invalidate(session, study, "photo_submitted")
                view = PhotoView(
                    id=photo.id,
                    review=photo.review,
                    pose=photo.pose,
                    lighting=photo.lighting,
                    rating_count=0,
                    created_at=photo.created_at,
                )
            except Exception:
                self.store(study).delete(study.id, artifact)
                raise
        return view

    def review_photo(
        self, user_id: UUID, study_id: UUID, photo_id: UUID, token: str, body: PhotoReview
    ) -> None:
        self.enabled()
        with self.sessions.begin() as session:
            user = self.lock_user(session, user_id)
            study = self.study(session, study_id)
            self.manager(session, study, user, token)
            if study.sealed_at:
                raise DomainError("study_sealed", 409)
            photo = session.get(Photo, photo_id)
            if photo is None or photo.study_id != study.id or photo.review == "DELETED":
                raise DomainError("study_not_found", 404)
            if self.recorded(
                session,
                user,
                body.idempotency_key,
                "study.photo_review",
                {"photo": str(photo.id), **body.model_dump(mode="json")},
            ):
                return
            if body.approved and photo.artifact_id is None:
                raise DomainError("study_not_found", 404)
            if not body.approved:
                self.erase_photo(session, study, photo)
            photo.review = "APPROVED" if body.approved else "REJECTED"
            for a in session.scalars(
                select(Assignment).where(
                    Assignment.photo_id == photo.id, Assignment.status == "ASSIGNED"
                )
            ):
                a.status = "CANCELLED"
            self.log(
                session,
                user.id,
                study.id,
                "study.photo_review",
                {"photo": str(photo.id), "approved": body.approved, "reason": body.reason},
            )
            self.invalidate(session, study, "photo_review")

    def assignment(self, user_id: UUID, study_id: UUID) -> AssignmentView | None:
        self.enabled()
        with self.sessions.begin() as session:
            user = self.lock_user(session, user_id)
            study = self.study(session, study_id)
            self.collection_open(study)
            if study.status != "OPEN":
                raise DomainError("study_closed", 409)
            member = self.member(session, study, user, "rater")
            live = session.scalar(
                select(Assignment).where(
                    Assignment.member_id == member.id, Assignment.status == "ASSIGNED"
                )
            )
            if live and aware(live.expires_at) <= now():
                live.status = "CANCELLED"
                session.flush()
                live = None
            if live is None:
                seen = select(Assignment.photo_id).where(
                    Assignment.member_id == member.id, Assignment.status.in_(["SAVED", "SKIPPED"])
                )
                query = (
                    select(Photo)
                    .join(Member, Photo.member_id == Member.id)
                    .join(Person, Member.person_id == Person.id)
                    .where(
                        Photo.study_id == study.id,
                        Photo.review == "APPROVED",
                        Photo.expires_at > now(),
                        Member.active.is_(True),
                        Member.approved.is_(True),
                        Person.user_id != user.id,
                    )
                )
                slots = (
                    select(func.count())
                    .select_from(Assignment)
                    .join(Member, Assignment.member_id == Member.id)
                    .where(
                        Assignment.photo_id == Photo.id,
                        Assignment.repeat.is_(False),
                        Member.active.is_(True),
                        Member.approved.is_(True),
                        or_(
                            Assignment.status == "SAVED",
                            (Assignment.status == "ASSIGNED") & (Assignment.expires_at > now()),
                        ),
                    )
                    .correlate(Photo)
                    .scalar_subquery()
                )
                # Balanced coverage: the least-rated eligible portrait first, ties broken at
                # random. Balance is conditional on this rater's eligibility and includes live
                # reservations. There is no arbitrary 1000-row truncation.
                least_covered = session.scalar(
                    query.where(Photo.id.not_in(seen), slots < 30)
                    .order_by(slots, func.random())
                    .limit(1)
                )
                candidates = [] if least_covered is None else [least_covered]
                repeat = False
                # A blind consistency repeat never counts as another independent rating.
                saved = (
                    session.scalar(
                        select(func.count())
                        .select_from(Assignment)
                        .where(
                            Assignment.member_id == member.id,
                            Assignment.status == "SAVED",
                            Assignment.repeat.is_(False),
                        )
                    )
                    or 0
                )
                repeated = select(Assignment.photo_id).where(
                    Assignment.member_id == member.id, Assignment.repeat.is_(True)
                )
                repeat_count = (
                    session.scalar(
                        select(func.count())
                        .select_from(Assignment)
                        .where(
                            Assignment.member_id == member.id,
                            Assignment.repeat.is_(True),
                            Assignment.status.in_(["SAVED", "SKIPPED"]),
                        )
                    )
                    or 0
                )
                if saved and repeat_count < saved // 5:
                    choices = list(
                        session.scalars(
                            query.where(
                                Photo.id.in_(
                                    select(Assignment.photo_id).where(
                                        Assignment.member_id == member.id,
                                        Assignment.status == "SAVED",
                                        Assignment.repeat.is_(False),
                                    )
                                ),
                                Photo.id.not_in(repeated),
                            ).limit(1000)
                        )
                    )
                    if choices:
                        candidates, repeat = choices, True
                if not candidates:
                    return None
                photo = secrets.choice(candidates)
                live = Assignment(
                    study_id=study.id,
                    member_id=member.id,
                    photo_id=photo.id,
                    consent_id=member.consent_id,
                    repeat=repeat,
                    expires_at=now() + timedelta(minutes=15),
                )
                session.add(live)
                session.flush()
                self.log(
                    session,
                    user.id,
                    study.id,
                    "study.assignment",
                    {"assignment": str(live.id), "repeat": repeat},
                )
            return AssignmentView(
                id=live.id,
                expires_at=live.expires_at,
                not_before=live.created_at + timedelta(seconds=2),
            )

    def owned_assignment(
        self, session: Session, study: Study, user: User, assignment_id: UUID
    ) -> Assignment:
        member = self.member(session, study, user, "rater")
        assignment = session.get(Assignment, assignment_id)
        if (
            assignment is None
            or assignment.study_id != study.id
            or assignment.member_id != member.id
        ):
            raise DomainError("study_not_found", 404)
        if (
            study.status != "OPEN"
            or assignment.status != "ASSIGNED"
            or aware(assignment.expires_at) <= now()
        ):
            raise DomainError("study_assignment_expired", 409)
        return assignment

    def viewed(self, user_id: UUID, study_id: UUID, assignment_id: UUID) -> AssignmentView:
        self.enabled()
        with self.sessions.begin() as session:
            user = self.lock_user(session, user_id)
            study = self.study(session, study_id)
            self.collection_open(study)
            assignment = self.owned_assignment(session, study, user, assignment_id)
            if assignment.viewed_at is None:
                assignment.viewed_at = now()
            return AssignmentView(
                id=assignment.id,
                expires_at=assignment.expires_at,
                not_before=aware(assignment.viewed_at) + timedelta(seconds=2),
            )

    def save_rating(
        self, user_id: UUID, study_id: UUID, assignment_id: UUID, body: RatingSubmit
    ) -> None:
        self.enabled()
        if body.skip == (body.score is not None):
            raise DomainError("study_rating_required", 422)
        with self.sessions.begin() as session:
            user = self.lock_user(session, user_id)
            study = self.study(session, study_id)
            self.collection_open(study)
            member = self.member(session, study, user, "rater")
            old = session.get(Assignment, assignment_id)
            if (
                old
                and old.study_id == study.id
                and old.member_id == member.id
                and old.status in {"SAVED", "SKIPPED"}
            ):
                if old.score == body.score and (old.status == "SKIPPED") == body.skip:
                    return
                raise DomainError("study_request_conflict", 409)
            assignment = self.owned_assignment(session, study, user, assignment_id)
            photo = session.get(Photo, assignment.photo_id)
            contributor = None if photo is None else session.get(Member, photo.member_id)
            if (
                photo is None
                or photo.review != "APPROVED"
                or aware(photo.expires_at) <= now()
                or contributor is None
                or not contributor.active
                or not contributor.approved
            ):
                raise DomainError("study_assignment_expired", 409)
            if not body.skip and (
                assignment.viewed_at is None
                or now() < aware(assignment.viewed_at) + timedelta(seconds=2)
            ):
                raise DomainError("study_too_fast", 429)
            assignment.status, assignment.score = (
                ("SKIPPED", None) if body.skip else ("SAVED", body.score)
            )
            self.invalidate(session, study, "rating_saved")
            self.log(
                session,
                user.id,
                study.id,
                "study.rating_saved",
                {"assignment": str(assignment.id), "skip": body.skip},
            )

    def image(
        self,
        user_id: UUID,
        study_id: UUID,
        *,
        photo_id: UUID | None = None,
        assignment_id: UUID | None = None,
    ) -> bytes:
        self.enabled()
        with self.sessions() as session:
            user = session.get(User, user_id)
            assert user is not None
            study = self.study(session, study_id)
            self.collection_open(study)
            if assignment_id is not None:
                assignment = self.owned_assignment(session, study, user, assignment_id)
                photo_id = assignment.photo_id
            else:
                own = {m.id for m in self.memberships(session, study, user)}
                candidate = session.get(Photo, photo_id) if photo_id else None
                if (
                    candidate is None
                    or candidate.study_id != study.id
                    or candidate.member_id not in own
                ):
                    self.manager(session, study, user)
            photo = session.get(Photo, photo_id) if photo_id else None
            if (
                photo is None
                or photo.study_id != study.id
                or photo.artifact_id is None
                or aware(photo.expires_at) <= now()
            ):
                raise DomainError("study_not_found", 404)
            content = self.store(study).read(study.id, photo.artifact_id)
            if hashlib.sha256(content).hexdigest() != photo.artifact_sha256:
                raise DomainError("study_image_integrity", 503)
            return content

    def erase_photo(self, session: Session, study: Study, photo: Photo) -> None:
        if photo.artifact_id:
            self.retire(session, study, "study-" + study.partition, photo.artifact_id)
        photo.artifact_id, photo.sha256, photo.artifact_sha256, photo.review = (
            None,
            None,
            None,
            "DELETED",
        )
        photo.pose, photo.lighting = "removed", "removed"
        for a in session.scalars(select(Assignment).where(Assignment.photo_id == photo.id)):
            a.score, a.status = None, "CANCELLED"

    def delete_photo(
        self, user_id: UUID, study_id: UUID, photo_id: UUID, token: str, key: UUID
    ) -> None:
        with self.sessions.begin() as session:
            user = self.lock_user(session, user_id)
            study = self.study(session, study_id)
            photo = session.get(Photo, photo_id)
            own = self.memberships(session, study, user)
            if photo is None or photo.study_id != study.id:
                raise DomainError("study_not_found", 404)
            if photo.member_id not in {m.id for m in own}:
                self.manager(session, study, user, token)
            old = session.scalar(select(StudyAudit).where(StudyAudit.request_key == str(key)))
            if old:
                if (
                    old.study_id != study.id
                    or old.actor_ref != self.actor_ref(study.id, user.id)
                    or old.action != "study.photo_deleted"
                    or old.details.get("photo") != str(photo.id)
                ):
                    raise DomainError("study_request_conflict", 409)
                return
            self.erase_photo(session, study, photo)
            self.invalidate(session, study, "photo_deleted")
            self.log(
                session, user.id, study.id, "study.photo_deleted", {"photo": str(photo.id)}, key
            )

    def withdraw(self, user_id: UUID, study_id: UUID, key: UUID) -> None:
        # Withdrawal remains available when collection is disabled, paused, closed or sealed.
        with self.sessions.begin() as session:
            user = self.lock_user(session, user_id)
            study = self.study(session, study_id)
            members = self.memberships(session, study, user)
            if not members:
                raise DomainError("study_not_found", 404)
            old = session.scalar(select(StudyAudit).where(StudyAudit.request_key == str(key)))
            actor = self.actor_ref(study.id, user.id)
            if old:
                if (
                    old.study_id != study.id
                    or old.actor_ref != actor
                    or old.action != "study.withdraw"
                ):
                    raise DomainError("study_request_conflict", 409)
                return
            session.add(
                StudyAudit(
                    study_id=study.id,
                    actor_ref=actor,
                    action="study.withdraw",
                    request_key=str(key),
                    details={},
                )
            )
            for member in members:
                member.active, member.approved, member.verification_reference = False, False, None
                for photo in session.scalars(select(Photo).where(Photo.member_id == member.id)):
                    self.erase_photo(session, study, photo)
                for a in session.scalars(
                    select(Assignment).where(Assignment.member_id == member.id)
                ):
                    a.score, a.status = None, "CANCELLED"
            self.invalidate(session, study, "withdrawal")

    def quality(self, user_id: UUID, study_id: UUID) -> list[dict[str, object]]:
        self.enabled()
        with self.sessions() as session:
            user = session.get(User, user_id)
            assert user is not None
            study = self.study(session, study_id)
            self.manager(session, study, user)
            result: list[dict[str, object]] = []
            for member in session.scalars(
                select(Member).where(Member.study_id == study.id, Member.role == "rater")
            ):
                ratings = list(
                    session.scalars(
                        select(Assignment).where(
                            Assignment.member_id == member.id, Assignment.status == "SAVED"
                        )
                    )
                )
                primary = {a.photo_id: a.score for a in ratings if not a.repeat}
                diffs = []
                for a in ratings:
                    original = primary.get(a.photo_id)
                    if a.repeat and a.score is not None and original is not None:
                        diffs.append(abs(a.score - original))
                result.append(
                    {
                        "member_id": str(member.id),
                        "primary_ratings": len(primary),
                        "repeat_checks": len(diffs),
                        "mean_absolute_repeat_difference": None
                        if not diffs
                        else sum(diffs) / len(diffs),
                        "automatic_exclusion": False,
                    }
                )
            return result

    def purge(self) -> None:
        # Always run, including after the collection capability is switched off.
        with self.sessions.begin() as session:
            study_ids = session.scalars(
                select(Photo.study_id)
                .where(Photo.expires_at <= now(), Photo.review != "DELETED")
                .distinct()
            )
            for study_id in list(study_ids):
                study = self.study(session, study_id)
                for photo in session.scalars(
                    select(Photo).where(
                        Photo.study_id == study.id,
                        Photo.expires_at <= now(),
                        Photo.review != "DELETED",
                    )
                ):
                    self.erase_photo(session, study, photo)
                self.invalidate(session, study, "retention")
                audit(session, None, "study.retention", str(study.id))
            for export in session.scalars(
                select(StudyExport).where(
                    StudyExport.status == "ACTIVE", StudyExport.expires_at <= now()
                )
            ):
                if export.artifact_id:
                    study = self.study(session, export.study_id)
                    self.retire(session, study, "study-exports", export.artifact_id)
                export.artifact_id, export.status = None, "EXPIRED"
        self.drain()
        # Reconcile artifacts left by crashed/rolled-back uploads, without following symlinks.
        for root_name in ("study-development", "study-holdout", "study-exports"):
            store = PrivateArtifactStore(self.settings.private_upload_root / root_name)
            if not store.root.exists():
                continue
            for namespace in store.root.iterdir():
                if namespace.is_symlink() or not namespace.is_dir():
                    continue
                for path in namespace.iterdir():
                    if (
                        path.is_symlink()
                        or not path.is_file()
                        or path.stat().st_mtime > now().timestamp() - 3600
                    ):
                        continue
                    try:
                        artifact, study_id = UUID(path.name), UUID(namespace.name)
                    except ValueError:
                        continue
                    with self.sessions() as session:
                        model = StudyExport if root_name == "study-exports" else Photo
                        referenced = session.scalar(
                            select(model.id).where(
                                model.artifact_id == artifact, model.study_id == study_id
                            )
                        )
                    if not referenced:
                        store.delete(study_id, artifact)
