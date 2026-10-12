import base64
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from aevyra_api.commercial.models import now
from aevyra_api.preferences.images import MAX_REQUEST_BYTES, decode_image
from aevyra_api.preferences.models import (
    PreferenceDataset,
    PreferenceImage,
    PreferencePair,
    PreferenceRating,
)
from aevyra_api.preferences.service import PreferenceService
from aevyra_api.research.models import ResearchAccess
from PIL import Image
from sqlalchemy import func, select
from test_credits import credits as credits
from test_credits import csrf_headers, register, user_id
from test_research import enable

BASE = "/api/v1/research/preferences"


def encoded(color="red", size=(100, 80), format="PNG"):
    output = BytesIO()
    image = Image.new("RGB", size, color)
    image.save(output, format=format)
    return base64.b64encode(output.getvalue()).decode()


def post(fixture, path, body):
    return fixture.client.post(BASE + path, json=body, headers=csrf_headers(fixture.client))


def setup_dataset(fixture):
    register(fixture.client)
    enable(fixture)
    fixture.client.app.state.settings.private_upload_root = (
        fixture.client.app.state.settings.private_model_root
    ) = Path.cwd() / "private"
    project = post(fixture, "/projects", {"name": "My preferences"}).json()
    dataset = post(
        fixture,
        "/datasets",
        {
            "project_id": project["id"],
            "name": "Synthetic test",
            "source": "Generated solid colors",
            "license": "Test-only generated fixture",
            "adult_authorized_consent": True,
        },
    )
    assert dataset.status_code == 200, dataset.text
    return dataset.json()["id"]


def upload(fixture, dataset, color="red", **extra):
    return post(
        fixture,
        f"/datasets/{dataset}/images",
        {
            "content_base64": encoded(color),
            "adult_authorized_consent": True,
            **extra,
        },
    )


def service(fixture):
    return PreferenceService(fixture.sessions, fixture.client.app.state.settings)


def test_dataset_upload_annotations_persist_without_credits(credits):
    dataset = setup_dataset(credits)
    one = upload(credits, dataset, subject_group="person-a")
    assert one.status_code == 200, one.text
    one = one.json()
    two = upload(credits, dataset, "blue").json()
    assert upload(credits, dataset).json()["id"] == one["id"]
    prefix = f"/datasets/{dataset}"
    assert post(credits, prefix + f"/images/{one['id']}/rating", {"score": 8.2}).status_code == 200
    pair = post(
        credits, prefix + "/pairs", {"left_id": one["id"], "right_id": two["id"], "choice": "left"}
    ).json()
    revised = post(
        credits, prefix + "/pairs", {"left_id": two["id"], "right_id": one["id"], "choice": "right"}
    ).json()
    assert revised["id"] == pair["id"] and revised["choice"] == pair["choice"]
    # Reconstructed service sees persisted annotations and private bytes.
    detail = service(credits).detail(user_id(credits), UUID(dataset))
    assert detail.dataset.image_count == 2 and detail.dataset.rated_count == 1
    assert detail.images[0].score == 8.2 and detail.images[0].subject_group == "person-a"
    assert len(detail.pairs) == 1
    assert (
        service(credits)
        .read(user_id(credits), UUID(dataset), UUID(one["id"]), False)
        .startswith(b"\xff\xd8")
    )
    wallet = credits.client.get("/api/v1/account").json()["wallet"]
    assert wallet == {"balance": 0, "transactions": []}


def test_private_content_auth_csrf_ownership_and_revocation(credits):
    dataset = setup_dataset(credits)
    owner = user_id(credits)
    photo = upload(credits, dataset).json()
    url = BASE + f"/datasets/{dataset}/images/{photo['id']}/content"
    content = credits.client.get(url + "?thumbnail=true")
    assert content.status_code == 200
    assert content.headers["content-type"] == "image/jpeg"
    assert "no-store" in content.headers["cache-control"]
    assert content.headers["x-content-type-options"] == "nosniff"
    assert credits.client.post(BASE + f"/datasets/{dataset}/delete", json={}).status_code == 403
    assert credits.client.get(f"/uploads/{photo['id']}").status_code == 404
    with credits.sessions.begin() as session:
        session.get(ResearchAccess, owner).enabled = False
    assert credits.client.get(url).status_code == 403
    with credits.sessions.begin() as session:
        session.get(ResearchAccess, owner).enabled = True
    register(credits.client, "other-dataset-owner")
    with credits.sessions.begin() as session:
        from aevyra_api.credits.models import User

        other = session.scalar(select(User).where(User.id != owner))
        session.add(ResearchAccess(user_id=other.id, enabled=True, reason="test"))
    assert credits.client.get(url).status_code == 404
    assert credits.client.get(BASE + f"/datasets/{dataset}").status_code == 404
    assert upload(credits, dataset).status_code == 404
    assert post(credits, f"/datasets/{dataset}/delete", {}).status_code == 404
    assert credits.client.get(BASE + "/datasets").json() == []
    credits.client.cookies.clear()
    assert credits.client.get(url).status_code == 401


def test_consent_and_unknown_fields_rejected(credits):
    dataset = setup_dataset(credits)
    assert upload(credits, dataset, adult_authorized_consent=False).status_code == 422
    assert upload(credits, dataset, user_id=str(uuid4())).status_code == 422
    project = credits.client.get(BASE + "/projects").json()[0]
    body = {
        "project_id": project["id"],
        "name": "Missing consent",
        "source": "test",
        "license": "test",
    }
    assert post(credits, "/datasets", body).status_code == 422
    assert (
        post(
            credits, "/datasets", {**body, "adult_authorized_consent": True, "retention_days": 91}
        ).status_code
        == 422
    )
    assert (
        post(
            credits,
            "/datasets",
            {**body, "adult_authorized_consent": True, "rating_min": 10, "rating_max": 1},
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "payload",
    [
        "garbage",
        base64.b64encode(b"<svg></svg>").decode(),
        encoded(size=(4097, 1)),
        encoded(format="GIF"),
    ],
)
def test_malformed_oversized_or_unsupported_images_rejected(credits, payload):
    dataset = setup_dataset(credits)
    assert upload(credits, dataset, content_base64=payload).status_code == 422
    assert credits.client.get(BASE + f"/datasets/{dataset}").json()["images"] == []


def test_stream_request_limit_and_decode_slots(credits):
    dataset = setup_dataset(credits)
    response = credits.client.post(
        BASE + f"/datasets/{dataset}/images",
        content=b"x" * (MAX_REQUEST_BYTES + 1),
        headers=csrf_headers(credits.client),
    )
    assert response.status_code == 413
    from aevyra_api.routes.preferences import upload_slots

    with upload_slots, upload_slots:
        assert upload(credits, dataset).status_code == 429
    assert upload(credits, dataset).status_code == 200


def test_image_metadata_removed_and_thumbnails_bounded():
    output = BytesIO()
    photo = Image.new("RGB", (800, 600), "red")
    exif = Image.Exif()
    exif[0x010E] = "sensitive metadata"
    photo.save(output, "JPEG", exif=exif)
    decoded = decode_image(base64.b64encode(output.getvalue()).decode())
    for payload in (decoded.image, decoded.thumbnail):
        assert b"sensitive metadata" not in payload
        with Image.open(BytesIO(payload)) as image:
            assert not image.getexif()
    with Image.open(BytesIO(decoded.thumbnail)) as thumb:
        assert max(thumb.size) <= 256


def test_rating_scale_skips_exclusion_and_pair_membership(credits):
    dataset = setup_dataset(credits)
    one = upload(credits, dataset).json()["id"]
    two = upload(credits, dataset, "blue").json()["id"]
    prefix = f"/datasets/{dataset}"
    assert post(credits, prefix + f"/images/{one}/rating", {"score": 11}).status_code == 422
    assert (
        post(credits, prefix + f"/images/{one}/rating", {"score": None}).json()["rating_recorded"]
        is True
    )
    assert (
        post(
            credits, prefix + "/pairs", {"left_id": one, "right_id": one, "choice": "equal"}
        ).status_code
        == 422
    )
    assert (
        post(
            credits, prefix + "/pairs", {"left_id": one, "right_id": str(uuid4()), "choice": "skip"}
        ).status_code
        == 404
    )
    for choice in ("left", "right", "equal", "skip"):
        assert (
            post(
                credits, prefix + "/pairs", {"left_id": one, "right_id": two, "choice": choice}
            ).status_code
            == 200
        )
    assert (
        post(
            credits, prefix + f"/images/{one}/edit", {"excluded": True, "subject_group": "group-a"}
        ).status_code
        == 200
    )
    assert post(credits, prefix + f"/images/{one}/rating", {"score": 5}).status_code == 409
    assert (
        post(
            credits, prefix + "/pairs", {"left_id": one, "right_id": two, "choice": "equal"}
        ).status_code
        == 409
    )
    assert (
        post(credits, prefix + "/edit", {"name": "Archived", "archived": True}).status_code == 200
    )
    assert upload(credits, dataset, "green").status_code == 409
    assert (
        post(credits, prefix + "/edit", {"name": "Restored", "archived": False}).status_code == 200
    )
    assert upload(credits, dataset, "green").status_code == 200


def test_deletion_hides_immediately_then_worker_purges_and_retries(credits):
    dataset = setup_dataset(credits)
    photo = upload(credits, dataset).json()["id"]
    data = service(credits)
    assert (
        post(credits, f"/datasets/{dataset}/images/{photo}/rating", {"score": 7}).status_code == 200
    )
    assert post(credits, f"/datasets/{dataset}/images/{photo}/delete", {}).status_code == 200
    assert (
        credits.client.get(BASE + f"/datasets/{dataset}/images/{photo}/content").status_code == 404
    )
    with (
        patch.object(data.store, "delete", side_effect=OSError("sensitive path")),
        pytest.raises(OSError),
    ):
        data.purge()
    with credits.sessions() as session:
        assert session.get(PreferenceImage, UUID(photo)) is not None
    assert data.purge() == 1
    assert data.purge() == 0
    assert list(data.store.root.glob("*/*")) == []
    with credits.sessions() as session:
        assert session.get(PreferenceImage, UUID(photo)) is None
        assert session.get(PreferenceRating, UUID(photo)) is None
    assert upload(credits, dataset).status_code == 200
    with credits.sessions.begin() as session:
        session.get(ResearchAccess, user_id(credits)).enabled = False
    assert post(credits, f"/datasets/{dataset}/delete", {}).status_code == 200
    assert data.purge() == 1
    assert list(data.store.root.glob("*/*")) == []


def test_retention_expires_and_purges_without_access_grant(credits):
    dataset = setup_dataset(credits)
    one = upload(credits, dataset).json()["id"]
    two = upload(credits, dataset, "blue").json()["id"]
    assert (
        post(
            credits,
            f"/datasets/{dataset}/pairs",
            {"left_id": one, "right_id": two, "choice": "equal"},
        ).status_code
        == 200
    )
    with credits.sessions.begin() as session:
        session.get(PreferenceDataset, UUID(dataset)).expires_at = now() - timedelta(seconds=1)
    assert credits.client.get(BASE + f"/datasets/{dataset}").status_code == 404
    assert upload(credits, dataset).status_code == 404
    assert service(credits).purge() == 2
    with credits.sessions() as session:
        assert session.get(PreferenceDataset, UUID(dataset)) is None
        assert session.scalar(select(func.count()).select_from(PreferencePair)) == 0


def test_storage_failure_does_not_leave_committed_image_or_first_derivative(credits):
    dataset = setup_dataset(credits)
    from aevyra_api.research.storage import PrivateArtifactStore

    original = PrivateArtifactStore.put
    calls = 0

    def put(store, owner, payload):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("test second write failure")
        return original(store, owner, payload)

    with patch.object(PrivateArtifactStore, "put", put), pytest.raises(OSError):
        upload(credits, dataset)
    assert list(service(credits).store.root.glob("*/*")) == []
    assert credits.client.get(BASE + f"/datasets/{dataset}").json()["images"] == []


def test_orphan_cleanup_preserves_recent_and_referenced_artifacts(credits):
    import os

    dataset = setup_dataset(credits)
    upload(credits, dataset)
    data = service(credits)
    owner = user_id(credits)
    orphan, _ = data.store.put(owner, b"orphan")
    recent, _ = data.store.put(owner, b"recent")
    cutoff = (now() - timedelta(hours=2)).timestamp()
    for path in data.store.root.glob("*/*"):
        if path.name != str(recent):
            os.utime(path, (cutoff, cutoff))
    data.purge()
    assert data.store.read(owner, recent) == b"recent"
    with pytest.raises(FileNotFoundError):
        data.store.read(owner, orphan)
    assert len(list(data.store.root.glob("*/*"))) == 3
