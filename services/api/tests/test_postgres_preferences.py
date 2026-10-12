from concurrent.futures import ThreadPoolExecutor

import pytest
from aevyra_api.accounts import AccountService
from aevyra_api.config import Settings
from aevyra_api.preferences.images import decode_image
from aevyra_api.preferences.models import PreferenceImage, PreferencePair
from aevyra_api.preferences.service import PreferenceService
from aevyra_api.research.models import ResearchAccess
from aevyra_contracts.preferences import DatasetCreate, ImageUpload, PairInput
from sqlalchemy import func, select
from test_postgres_commercial import postgres_services
from test_preferences import encoded

pytestmark = pytest.mark.integration


def test_concurrent_upload_pair_update_and_service_restart(tmp_path):
    with postgres_services() as (sessions, *_):
        settings = Settings(
            api_environment="test", research_mode=True, private_upload_root=tmp_path, _env_file=None
        )
        user, _ = AccountService(sessions, settings).register(
            "preference-owner", "test-preference-password"
        )
        with sessions.begin() as session:
            session.add(ResearchAccess(user_id=user.id, enabled=True, reason="test"))
        data = PreferenceService(sessions, settings)
        project = data.create_project(user.id, "Concurrent project")
        dataset = data.create_dataset(
            user.id,
            DatasetCreate(
                project_id=project.id,
                name="Concurrent dataset",
                source="Synthetic",
                license="Generated fixture",
                adult_authorized_consent=True,
            ),
        )
        upload = ImageUpload(content_base64=encoded(), adult_authorized_consent=True)
        decoded = decode_image(upload.content_base64)
        with ThreadPoolExecutor(max_workers=6) as pool:
            ids = list(
                pool.map(lambda _: data.upload(user.id, dataset.id, upload, decoded).id, range(6))
            )
        assert len(set(ids)) == 1
        other_upload = ImageUpload(content_base64=encoded("blue"), adult_authorized_consent=True)
        other = data.upload(
            user.id, dataset.id, other_upload, decode_image(other_upload.content_base64)
        )
        with ThreadPoolExecutor(max_workers=6) as pool:
            pairs = list(
                pool.map(
                    lambda _: (
                        data.pair(
                            user.id,
                            dataset.id,
                            PairInput(left_id=ids[0], right_id=other.id, choice="equal"),
                        ).id
                    ),
                    range(6),
                )
            )
        assert len(set(pairs)) == 1
        data.rate(user.id, dataset.id, ids[0], 7.5)
        restarted = PreferenceService(sessions, settings)
        assert restarted.detail(user.id, dataset.id).dataset.rated_count == 1
        assert restarted.read(user.id, dataset.id, ids[0], False).startswith(b"\xff\xd8")
        assert len(list(data.store.root.glob("*/*"))) == 4
        with sessions() as session:
            assert session.scalar(select(func.count()).select_from(PreferenceImage)) == 2
            assert session.scalar(select(func.count()).select_from(PreferencePair)) == 1
        restarted.delete(user.id, dataset.id)
        assert restarted.purge() == 2
        assert list(data.store.root.glob("*/*")) == []
