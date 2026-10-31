"""Owner-scoped research data; user locks serialize quota and annotation mutations."""

import logging
from datetime import timedelta
from uuid import UUID

from aevyra_contracts.preferences import (
    DatasetCreate,
    DatasetDetail,
    DatasetEdit,
    DatasetView,
    ImageEdit,
    ImageUploadMetadata,
    ImageView,
    PairInput,
    PairView,
    ProjectView,
)
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.models import User
from aevyra_api.entitlements import research_limits
from aevyra_api.preferences.images import CONSENT_VERSION, DecodedImage
from aevyra_api.preferences.models import (
    PreferenceDataset as Dataset,
)
from aevyra_api.preferences.models import (
    PreferenceImage as Image,
)
from aevyra_api.preferences.models import (
    PreferencePair as Pair,
)
from aevyra_api.preferences.models import (
    PreferenceProject as Project,
)
from aevyra_api.preferences.models import (
    PreferenceRating as Rating,
)
from aevyra_api.research.jobs import authorized
from aevyra_api.research.storage import PrivateArtifactStore

logger = logging.getLogger("aevyra.preferences")


class PreferenceService:
    def __init__(self, sessions: sessionmaker[Session], settings: Settings):
        self.sessions = sessions
        self.settings = settings
        # Separate namespace from Phase 4A artifacts; never mounted in web/proxy.
        self.store = PrivateArtifactStore(settings.private_upload_root / "preferences")

    def access(self, session: Session, user: UUID, *, lock: bool = False) -> None:
        if lock:
            session.scalar(select(User).where(User.id == user).with_for_update())
        if not self.settings.research_mode or not authorized(session, user):
            raise DomainError("Research access required", 403)

    def dataset(self, session: Session, user: UUID, id: UUID, *, writable: bool = False) -> Dataset:
        dataset = session.scalar(
            select(Dataset)
            .join(Project)
            .where(
                Dataset.id == id,
                Project.user_id == user,
                Dataset.deleted_at.is_(None),
                Dataset.expires_at > now(),
            )
            .with_for_update()
        )
        if dataset is None:
            raise DomainError("Dataset not found or expired", 404)
        if writable and dataset.archived:
            raise DomainError(
                "Restore the archived dataset before editing annotations or images", 409
            )
        return dataset

    def image(self, session: Session, dataset: UUID, id: UUID) -> Image:
        image = session.scalar(
            select(Image).where(
                Image.id == id, Image.dataset_id == dataset, Image.deleted_at.is_(None)
            )
        )
        if image is None:
            raise DomainError("Image not found", 404)
        return image

    def projects(self, user: UUID) -> list[ProjectView]:
        with self.sessions() as session:
            self.access(session, user)
            return [
                ProjectView.model_validate(row)
                for row in session.scalars(
                    select(Project).where(Project.user_id == user).order_by(Project.created_at)
                )
            ]

    def create_project(self, user: UUID, name: str) -> ProjectView:
        with self.sessions.begin() as session:
            self.access(session, user, lock=True)
            if (
                session.scalar(
                    select(func.count()).select_from(Project).where(Project.user_id == user)
                )
                or 0
            ) >= research_limits(session, user, self.settings).projects:
                raise DomainError("Project resource limit reached", 429)
            row = Project(user_id=user, name=name)
            session.add(row)
            session.flush()
            return ProjectView.model_validate(row)

    def view(self, session: Session, row: Dataset) -> DatasetView:
        count = (
            session.scalar(
                select(func.count())
                .select_from(Image)
                .where(Image.dataset_id == row.id, Image.deleted_at.is_(None))
            )
            or 0
        )
        rated = (
            session.scalar(
                select(func.count())
                .select_from(Rating)
                .join(Image)
                .where(
                    Image.dataset_id == row.id,
                    Image.deleted_at.is_(None),
                    Image.excluded.is_(False),
                    Rating.score.is_not(None),
                )
            )
            or 0
        )
        compared = (
            session.scalar(
                select(func.count())
                .select_from(Pair)
                .where(Pair.dataset_id == row.id, Pair.choice != "skip")
            )
            or 0
        )
        return DatasetView(
            id=row.id,
            project_id=row.project_id,
            name=row.name,
            source=row.source,
            source_url=row.source_url,
            license=row.license,
            rating_min=row.rating_min,
            rating_max=row.rating_max,
            archived=row.archived,
            expires_at=row.expires_at,
            created_at=row.created_at,
            image_count=count,
            rated_count=rated,
            compared_count=compared,
        )

    def datasets(self, user: UUID) -> list[DatasetView]:
        with self.sessions() as session:
            self.access(session, user)
            return [
                self.view(session, row)
                for row in session.scalars(
                    select(Dataset)
                    .join(Project)
                    .where(
                        Project.user_id == user,
                        Dataset.deleted_at.is_(None),
                        Dataset.expires_at > now(),
                    )
                    .order_by(Dataset.created_at)
                )
            ]

    def create_dataset(self, user: UUID, body: DatasetCreate) -> DatasetView:
        with self.sessions.begin() as session:
            self.access(session, user, lock=True)
            project = session.scalar(
                select(Project).where(Project.id == body.project_id, Project.user_id == user)
            )
            if project is None:
                raise DomainError("Project not found", 404)
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(Dataset)
                    .join(Project)
                    .where(Project.user_id == user)
                )
                or 0
            )
            if count >= research_limits(session, user, self.settings).datasets:
                raise DomainError("Dataset resource limit reached", 429)
            row = Dataset(
                project_id=project.id,
                name=body.name,
                source=body.source,
                source_url=body.source_url,
                license=body.license,
                rating_min=body.rating_min,
                rating_max=body.rating_max,
                consent_version=CONSENT_VERSION,
                expires_at=now() + timedelta(days=body.retention_days),
            )
            session.add(row)
            session.flush()
            return self.view(session, row)

    def edit_dataset(self, user: UUID, id: UUID, body: DatasetEdit) -> DatasetView:
        with self.sessions.begin() as session:
            self.access(session, user, lock=True)
            row = self.dataset(session, user, id)
            row.name, row.archived = body.name, body.archived
            session.flush()
            return self.view(session, row)

    def image_view(self, session: Session, row: Image) -> ImageView:
        rating = session.get(Rating, row.id)
        return ImageView(
            id=row.id,
            dataset_id=row.dataset_id,
            width=row.width,
            height=row.height,
            subject_group=row.subject_group,
            excluded=row.excluded,
            created_at=row.created_at,
            score=rating.score if rating else None,
            rating_recorded=rating is not None,
            purpose="prediction" if row.purpose == "prediction" else "annotation",
        )

    def detail(self, user: UUID, id: UUID) -> DatasetDetail:
        with self.sessions() as session:
            self.access(session, user)
            row = self.dataset(session, user, id)
            images = [
                self.image_view(session, image)
                for image in session.scalars(
                    select(Image)
                    .where(Image.dataset_id == id, Image.deleted_at.is_(None))
                    .order_by(Image.created_at, Image.id)
                )
            ]
            pairs = [
                PairView.model_validate(pair)
                for pair in session.scalars(
                    select(Pair).where(Pair.dataset_id == id).order_by(Pair.updated_at)
                )
            ]
            return DatasetDetail(dataset=self.view(session, row), images=images, pairs=pairs)

    def check_upload(self, user: UUID, id: UUID) -> None:
        with self.sessions() as session:
            self.access(session, user)
            self.dataset(session, user, id, writable=True)

    def upload(
        self, user: UUID, id: UUID, body: ImageUploadMetadata, decoded: DecodedImage
    ) -> ImageView:
        artifacts: list[UUID] = []
        try:
            with self.sessions.begin() as session:
                self.access(session, user, lock=True)
                dataset = self.dataset(session, user, id, writable=True)
                # Coordinate with retention cleanup before creating any files.
                session.scalar(select(Dataset).where(Dataset.id == dataset.id).with_for_update())
                existing = session.scalar(
                    select(Image).where(
                        Image.dataset_id == id, Image.content_hash == decoded.content_hash
                    )
                )
                if existing:
                    if existing.deleted_at is not None:
                        raise DomainError(
                            "Duplicate image is pending deletion; retry after cleanup", 409
                        )
                    # A prediction-only photograph never silently becomes training data. An
                    # existing annotation photograph may be reused for prediction as-is.
                    if existing.purpose == "prediction" and body.purpose == "annotation":
                        raise DomainError(
                            "This photograph is saved for prediction only; delete it to annotate",
                            409,
                        )
                    return self.image_view(session, existing)
                count, used = session.execute(
                    select(func.count(Image.id), func.coalesce(func.sum(Image.byte_size), 0))
                    .select_from(Image)
                    .join(Dataset)
                    .join(Project)
                    .where(Project.user_id == user)
                ).one()
                size = len(decoded.image) + len(decoded.thumbnail)
                limits = research_limits(session, user, self.settings)
                if count >= limits.images or used + size > limits.storage_bytes:
                    raise DomainError("Private image resource quota reached", 429)
                artifact, _ = self.store.put(user, decoded.image)
                artifacts.append(artifact)
                thumbnail, _ = self.store.put(user, decoded.thumbnail)
                artifacts.append(thumbnail)
                row = Image(
                    dataset_id=id,
                    artifact_id=artifact,
                    thumbnail_id=thumbnail,
                    original_hash=decoded.original_hash,
                    content_hash=decoded.content_hash,
                    byte_size=size,
                    width=decoded.width,
                    height=decoded.height,
                    subject_group=body.subject_group,
                    purpose=body.purpose,
                    consent_version=CONSENT_VERSION,
                )
                session.add(row)
                session.flush()
                result = self.image_view(session, row)
            return result
        except Exception:
            for artifact in artifacts:
                try:
                    self.store.delete(user, artifact)
                except OSError as exc:
                    logger.error(
                        "image_rollback_cleanup_failed", extra={"error_type": type(exc).__name__}
                    )
            raise

    def read(self, user: UUID, dataset_id: UUID, image_id: UUID, thumbnail: bool) -> bytes:
        with self.sessions() as session:
            self.access(session, user)
            self.dataset(session, user, dataset_id)
            row = self.image(session, dataset_id, image_id)
            try:
                return self.store.read(user, row.thumbnail_id if thumbnail else row.artifact_id)
            except FileNotFoundError:
                raise DomainError("Image unavailable", 404) from None

    def edit_image(self, user: UUID, dataset_id: UUID, id: UUID, body: ImageEdit) -> ImageView:
        with self.sessions.begin() as session:
            self.access(session, user, lock=True)
            self.dataset(session, user, dataset_id, writable=True)
            row = self.image(session, dataset_id, id)
            row.subject_group, row.excluded = body.subject_group, body.excluded
            session.flush()
            return self.image_view(session, row)

    def rate(self, user: UUID, dataset_id: UUID, id: UUID, score: float | None) -> ImageView:
        with self.sessions.begin() as session:
            self.access(session, user, lock=True)
            dataset = self.dataset(session, user, dataset_id, writable=True)
            row = self.image(session, dataset_id, id)
            if row.excluded or row.purpose == "prediction":
                raise DomainError("Image is excluded from annotation", 409)
            if score is not None and not dataset.rating_min <= score <= dataset.rating_max:
                raise DomainError("Rating outside this dataset's scale", 422)
            rating = session.get(Rating, id)
            if rating is None:
                session.add(Rating(image_id=id, score=score))
            else:
                rating.score, rating.updated_at = score, now()
            session.flush()
            return self.image_view(session, row)

    def pair(self, user: UUID, dataset_id: UUID, body: PairInput) -> PairView:
        with self.sessions.begin() as session:
            self.access(session, user, lock=True)
            self.dataset(session, user, dataset_id, writable=True)
            if body.left_id == body.right_id:
                raise DomainError("Choose two distinct images", 422)
            for id in (body.left_id, body.right_id):
                image = self.image(session, dataset_id, id)
                if image.excluded or image.purpose == "prediction":
                    raise DomainError("Image is excluded from annotation", 409)
            left, right = sorted((body.left_id, body.right_id))
            choice = body.choice
            if left != body.left_id and choice in {"left", "right"}:
                choice = "right" if choice == "left" else "left"
            row = session.scalar(select(Pair).where(Pair.left_id == left, Pair.right_id == right))
            if row is None:
                if (
                    session.scalar(
                        select(func.count()).select_from(Pair).where(Pair.dataset_id == dataset_id)
                    )
                    or 0
                ) >= research_limits(session, user, self.settings).pairs:
                    raise DomainError("Pair annotation resource limit reached", 429)
                row = Pair(dataset_id=dataset_id, left_id=left, right_id=right, choice=choice)
                session.add(row)
            else:
                row.choice, row.updated_at = choice, now()
            session.flush()
            return PairView.model_validate(row)

    def delete(self, user: UUID, dataset_id: UUID, image_id: UUID | None = None) -> None:
        # Owners retain deletion rights even after a research grant is revoked.
        with self.sessions.begin() as session:
            session.scalar(select(User).where(User.id == user).with_for_update())
            row = session.scalar(
                select(Dataset)
                .join(Project)
                .where(Dataset.id == dataset_id, Project.user_id == user)
                .with_for_update()
            )
            if row is None:
                raise DomainError("Dataset not found", 404)
            if image_id is None:
                row.deleted_at = now()
            else:
                image = session.scalar(
                    select(Image).where(Image.id == image_id, Image.dataset_id == row.id)
                )
                if image is None:
                    raise DomainError("Image not found", 404)
                image.deleted_at = now()
                session.execute(delete(Rating).where(Rating.image_id == image_id))
                session.execute(
                    delete(Pair).where(or_(Pair.left_id == image_id, Pair.right_id == image_id))
                )

    def purge(self) -> int:
        """Retryable filesystem cleanup; DB references remain until files are gone."""
        removed = 0
        with self.sessions.begin() as session:
            rows = list(
                session.scalars(
                    select(Dataset)
                    .where(
                        or_(
                            Dataset.deleted_at.is_not(None),
                            Dataset.expires_at <= now(),
                            Dataset.id.in_(
                                select(Image.dataset_id).where(Image.deleted_at.is_not(None))
                            ),
                        )
                    )
                    .order_by(Dataset.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(20)
                )
            )
            for row in rows:
                owner = session.scalar(select(Project.user_id).where(Project.id == row.project_id))
                assert owner is not None
                # Query in SQL to keep timestamp handling consistent on SQLite fixtures.
                all_images = (
                    session.scalar(
                        select(Dataset.id).where(
                            Dataset.id == row.id,
                            or_(Dataset.deleted_at.is_not(None), Dataset.expires_at <= now()),
                        )
                    )
                    is not None
                )
                query = select(Image).where(Image.dataset_id == row.id)
                if not all_images:
                    query = query.where(Image.deleted_at.is_not(None))
                for image in session.scalars(query):
                    self.store.delete(owner, image.artifact_id)
                    self.store.delete(owner, image.thumbnail_id)
                    session.execute(
                        delete(Pair).where(or_(Pair.left_id == image.id, Pair.right_id == image.id))
                    )
                    session.execute(delete(Rating).where(Rating.image_id == image.id))
                    session.delete(image)
                    removed += 1
                session.flush()
                if all_images:
                    session.delete(row)
        self.purge_orphans()
        return removed

    def purge_orphans(self) -> None:
        """Recover files left by process death before the upload DB transaction committed."""
        if not self.store.root.exists():
            return
        cutoff = (now() - timedelta(hours=1)).timestamp()
        for directory in self.store.root.iterdir():
            if directory.is_symlink() or not directory.is_dir():
                continue
            try:
                owner = UUID(directory.name)
            except ValueError:
                continue
            with self.sessions.begin() as session:
                # All upload commits take this same lock. Never delete an in-flight write.
                session.scalar(select(User).where(User.id == owner).with_for_update())
                references = session.execute(
                    select(Image.artifact_id, Image.thumbnail_id)
                    .join(Dataset)
                    .join(Project)
                    .where(Project.user_id == owner)
                )
                live = {artifact for row in references for artifact in row}
                for path in directory.iterdir():
                    if path.is_symlink() or not path.is_file():
                        continue
                    try:
                        artifact = UUID(path.name)
                    except ValueError:
                        continue
                    if artifact not in live and path.stat().st_mtime < cutoff:
                        self.store.delete(owner, artifact)
