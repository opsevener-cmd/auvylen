"""Bounded, revocable DEVELOPMENT snapshots. Holdouts are never exportable here."""

import csv
import hashlib
import json
import math
from datetime import timedelta
from io import BytesIO, StringIO
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import ZIP_STORED, ZipFile

from aevyra_contracts.studies import ExportView
from aevyra_inference.native_data import Collection, Rights
from aevyra_inference.rating_quality import fit_rater_model, reliability
from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from aevyra_api.administration import audit
from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.credits.codes import aware
from aevyra_api.credits.models import User
from aevyra_api.entitlements import require_owner
from aevyra_api.studies.models import (
    Assignment,
    ConsentVersion,
    Member,
    Photo,
    Receipt,
    Study,
    StudyExport,
)
from aevyra_api.studies.service import Studies

MAX_EXPORT = 64 * 1024**2


def export_view(row: StudyExport) -> ExportView:
    return ExportView(
        id=row.id,
        status=row.status,
        sha256=row.sha256,
        images=row.images,
        subjects=row.subjects,
        expires_at=row.expires_at,
    )


def eligible(session: Session, study: Study) -> list[tuple[Photo, list[Assignment]]]:
    photos = session.scalars(
        select(Photo)
        .join(Member, Photo.member_id == Member.id)
        .where(
            Photo.study_id == study.id,
            Photo.review == "APPROVED",
            Photo.expires_at > now(),
            Member.active.is_(True),
            Member.approved.is_(True),
        )
        .order_by(Photo.id)
    )
    ratings = list(
        session.scalars(
            select(Assignment)
            .join(Member, Assignment.member_id == Member.id)
            .where(
                Assignment.study_id == study.id,
                Assignment.status == "SAVED",
                Assignment.repeat.is_(False),
                Assignment.score.is_not(None),
                Member.active.is_(True),
                Member.approved.is_(True),
            )
            .order_by(Assignment.id)
        )
    )
    grouped: dict[UUID, list[Assignment]] = {}
    for rating in ratings:
        grouped.setdefault(rating.photo_id, []).append(rating)
    return [(p, grouped[p.id]) for p in photos if len(grouped.get(p.id, [])) >= 3]


class Exports:
    def __init__(self, data: Studies):
        self.data = data

    def create(self, user_id: UUID, study_id: UUID, token: str, key: UUID) -> ExportView:
        self.data.enabled()
        artifact = None
        with self.data.sessions.begin() as session:
            user = self.data.lock_user(session, user_id)
            require_owner(user)
            self.data.fresh(session, user, token)
            study = self.data.study(session, study_id)
            if study.partition != "development":
                raise DomainError("study_holdout_not_exportable", 403)
            self.data.collection_open(study)
            if study.status != "CLOSED":
                raise DomainError("study_export_close_first", 409)
            previous = session.scalar(
                select(StudyExport).where(StudyExport.request_key == str(key))
            )
            if previous:
                if previous.study_id != study.id or previous.owner_id != user.id:
                    raise DomainError("study_request_conflict", 409)
                self.valid(previous, study)
                return export_view(previous)
            rows = eligible(session, study)
            if not rows:
                raise DomainError("study_no_eligible_data", 409)
            export_id = uuid4()
            bundle, subjects = self.bundle(session, study, rows, export_id)
            artifact, digest = self.data.export_store().put(study.id, bundle)
            try:
                row = StudyExport(
                    id=export_id,
                    owner_id=user.id,
                    study_id=study.id,
                    request_key=str(key),
                    artifact_id=artifact,
                    sha256=digest,
                    revision=study.revision,
                    images=len(rows),
                    subjects=subjects,
                    expires_at=now() + timedelta(hours=24),
                )
                session.add(row)
                session.flush()
                audit(
                    session,
                    user.id,
                    "study.export",
                    str(study.id),
                    details={
                        "export": str(export_id),
                        "images": len(rows),
                        "subjects": subjects,
                        "revision": study.revision,
                    },
                )
                result = export_view(row)
            except Exception:
                self.data.export_store().delete(study.id, artifact)
                raise
        return result

    def valid(self, row: StudyExport, study: Study) -> None:
        self.data.collection_open(study)
        if (
            study.partition != "development"
            or row.status != "ACTIVE"
            or row.artifact_id is None
            or row.revision != study.revision
            or aware(row.expires_at) <= now()
        ):
            raise DomainError("study_export_revoked", 410)

    def owned(
        self, session: Session, user: User, study_id: UUID, export_id: UUID
    ) -> tuple[Study, StudyExport]:
        require_owner(user)
        study = self.data.study(session, study_id)
        if study.partition != "development":
            raise DomainError("study_holdout_not_exportable", 403)
        row = session.get(StudyExport, export_id)
        if row is None or row.study_id != study.id or row.owner_id != user.id:
            raise DomainError("study_not_found", 404)
        self.valid(row, study)
        return study, row

    def info(self, user_id: UUID, study_id: UUID, export_id: UUID) -> ExportView:
        self.data.enabled()
        with self.data.sessions() as session:
            user = session.get(User, user_id)
            assert user is not None
            _, row = self.owned(session, user, study_id, export_id)
            return export_view(row)

    def read(self, user_id: UUID, study_id: UUID, export_id: UUID) -> bytes:
        self.data.enabled()
        with self.data.sessions() as session:
            user = session.get(User, user_id)
            assert user is not None
            study, row = self.owned(session, user, study_id, export_id)
            assert row.artifact_id is not None
            bundle = self.data.export_store().read(study.id, row.artifact_id)
            if hashlib.sha256(bundle).hexdigest() != row.sha256:
                raise DomainError("study_export_integrity", 503)
            return bundle

    def bundle(
        self,
        session: Session,
        study: Study,
        rows: list[tuple[Photo, list[Assignment]]],
        export_id: UUID,
    ) -> tuple[bytes, int]:
        output = BytesIO()
        means, annotations = StringIO(), StringIO()
        mw, aw = csv.writer(means), csv.writer(annotations)
        mw.writerow(["image", "subject_id", "rating", "rating_count", "rights_id", "cohort"])
        aw.writerow(["image", "subject_id", "rater_id", "rating", "rights_id", "cohort"])
        rights: dict[str, Rights] = {}
        grants: dict[str, dict[str, JsonValue]] = {}
        receipts: dict[str, dict[str, str]] = {}
        subjects: set[str] = set()
        hashes: dict[str, str] = {}
        votes: list[tuple[str, str, float]] = []
        label_rows: list[tuple[str, str, int, str]] = []
        total = 0
        with ZipFile(output, "w", compression=ZIP_STORED, allowZip64=False) as archive:
            for photo, ratings in rows:
                member = session.get(Member, photo.member_id)
                assert member is not None and photo.artifact_id is not None
                subject = str(member.person_id)
                subjects.add(subject)
                consent_ids = {photo.consent_id, *(a.consent_id for a in ratings)}
                versions = [session.get(ConsentVersion, key) for key in sorted(consent_ids)]
                assert all(v is not None for v in versions)
                digest = hashlib.sha256(
                    "".join(sorted(v.sha256 for v in versions if v)).encode()
                ).hexdigest()
                right = "consent-" + digest[:24]
                reference = f"consents.json#{right}"
                rights[right] = Rights(
                    image_license=reference,
                    annotation_license=reference,
                    subject_release=reference,
                    training_permission=reference,
                    derived_weight_permission=reference,
                    reviewer="Study staff verification and versioned electronic receipts",
                    adult_confirmed=True,
                    research_allowed=True,
                    commercial_allowed=False,
                )
                for version in versions:
                    assert version is not None
                    grants[version.sha256] = {
                        "study_id": str(study.id),
                        "partition": study.partition,
                        "fixture_only": study.fixture_only,
                        "retention_days": study.retention_days,
                        "version": version.version,
                        "text_en": version.text_en,
                        "text_zh": version.text_zh,
                        "rights_reference": version.rights_reference,
                        "contact_en": version.contact_en,
                        "contact_zh": version.contact_zh,
                    }
                grants_for = [(member, photo.consent_id)]
                for rating in ratings:
                    rater_member = session.get(Member, rating.member_id)
                    assert rater_member is not None
                    grants_for.append((rater_member, rating.consent_id))
                for accepted_member, consent_id in grants_for:
                    receipt = session.scalar(
                        select(Receipt).where(
                            Receipt.member_id == accepted_member.id,
                            Receipt.consent_id == consent_id,
                        )
                    )
                    version = session.get(ConsentVersion, consent_id)
                    if receipt is None or version is None:
                        raise DomainError("study_export_integrity", 503)
                    receipts[str(receipt.id)] = {
                        "person_ref": str(accepted_member.person_id),
                        "role": accepted_member.role,
                        "consent_sha256": version.sha256,
                        "accepted_at": aware(receipt.created_at).isoformat(),
                    }
                # Consent-id linkage is private inside the bundle, never account/login identifiers.
                grants[right] = {
                    "version_hashes": ",".join(sorted(v.sha256 for v in versions if v))
                }
                name = "images/" + str(photo.id) + ".jpg"
                image = self.data.store(study).read(study.id, photo.artifact_id)
                if hashlib.sha256(image).hexdigest() != photo.artifact_sha256:
                    raise DomainError("study_image_integrity", 503)
                total += len(image)
                if total > MAX_EXPORT - 2 * 1024**2:
                    raise DomainError("study_export_limit", 413)
                archive.writestr(name, image)
                hashes[name] = hashlib.sha256(image).hexdigest()
                score = sum(a.score for a in ratings if a.score is not None) / len(ratings)
                mw.writerow([name, subject, score, len(ratings), right, "not_reported"])
                label_rows.append((name, subject, len(ratings), right))
                for a in ratings:
                    rater = session.get(Member, a.member_id)
                    assert rater is not None and a.score is not None
                    votes.append((name, str(rater.person_id), float(a.score)))
                    aw.writerow(
                        [name, subject, str(rater.person_id), a.score, right, "not_reported"]
                    )
            # Rater-adjusted labels in the means.csv format, so the native trainer can use
            # either file unchanged. Offsets are fitted on this snapshot's primary votes only.
            model = fit_rater_model(votes)
            adjusted_labels = model.adjusted(1.0, 7.0)
            adjusted = StringIO()
            adjusted_writer = csv.writer(adjusted)
            adjusted_writer.writerow(
                ["image", "subject_id", "rating", "rating_count", "rights_id", "cohort"]
            )
            for name, subject, count, right in label_rows:
                adjusted_writer.writerow(
                    [name, subject, adjusted_labels[name], count, right, "not_reported"]
                )
            quality = {
                "agreement": reliability(votes),
                "rater_model": {
                    "method": "additive image + rater offsets; method-of-moments shrinkage",
                    "rater_variance": model.rater_var,
                    "noise_variance": model.noise_var if math.isfinite(model.noise_var) else None,
                    "shrinkage": model.shrinkage,
                    "adjusted": model.shrinkage is not None,
                },
                "caution": (
                    "Agreement among these raters, not model accuracy or validity. Offsets use "
                    "every exported image, so internal train/test splits share rater estimates."
                ),
            }
            collection = Collection(
                name="Auvylen consented development collection " + str(study.id),
                rights=rights,
                synthetic=study.fixture_only,
                rating_max=7,
                encoder_rights_review="Separate encoder review required; commercial use forbidden",
                annotator_population="Verified voluntary adult raters; repeats excluded",
                rating_protocol_reference=f"study-export:{export_id}; native 1–7, development only",
            )
            files = {
                "means.csv": means.getvalue().encode(),
                "adjusted.csv": adjusted.getvalue().encode(),
                "reliability.json": json.dumps(quality, sort_keys=True, allow_nan=False).encode(),
                "annotations.csv": annotations.getvalue().encode(),
                "collection.json": collection.model_dump_json(indent=2).encode(),
                "consents.json": json.dumps(grants, sort_keys=True, ensure_ascii=False).encode(),
                "receipts.json": json.dumps(receipts, sort_keys=True).encode(),
            }
            for name, payload in files.items():
                archive.writestr(name, payload)
                hashes[name] = hashlib.sha256(payload).hexdigest()
            manifest = {
                "format": "auvylen-study-export-v1",
                "partition": "development",
                "independent_external_holdout": False,
                "native_scale": [1, 7],
                "fixture_only": study.fixture_only,
                "study_id": str(study.id),
                "export_id": str(export_id),
                "revision": study.revision,
                "sha256": hashes,
                "deletion": "Recheck live status before every use; downloads cannot be recalled",
                "split_policy": (
                    "Internal splits are development diagnostics, not external holdouts"
                ),
            }
            archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True).encode())
        if output.tell() > MAX_EXPORT:
            raise DomainError("study_export_limit", 413)
        return output.getvalue(), len(subjects)


def prepare(export_id: UUID, destination: Path) -> None:
    """Private operator CLI: recheck live revocation/integrity, then extract a new 0700 folder."""
    from aevyra_api.config import Settings
    from aevyra_api.database import DependencyChecks

    settings = Settings()
    checks = DependencyChecks(settings)
    try:
        data = Studies(checks.sessions, settings)
        with checks.sessions() as session:
            row = session.get(StudyExport, export_id)
            if row is None:
                raise ValueError("Export unavailable")
            user_id, study_id = row.owner_id, row.study_id
        bundle = Exports(data).read(user_id, study_id, export_id)
        if destination.exists():
            raise ValueError("Use a new private directory")
        with ZipFile(BytesIO(bundle)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            if manifest["partition"] != "development" or manifest["independent_external_holdout"]:
                raise ValueError("Holdout cannot enter training")
            for name, digest in manifest["sha256"].items():
                path = Path(name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or hashlib.sha256(archive.read(name)).hexdigest() != digest
                ):
                    raise ValueError("Export integrity failure")
            destination.mkdir(parents=True, mode=0o700)
            for name in [*manifest["sha256"], "manifest.json"]:
                path = destination / name
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with path.open("xb") as file:
                    path.chmod(0o600)
                    file.write(archive.read(name))
    finally:
        checks.close()


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(
        description="Validate a development study export against live revocation status"
    )
    p.add_argument("--export-id", type=UUID, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    prepare(args.export_id, args.output)
