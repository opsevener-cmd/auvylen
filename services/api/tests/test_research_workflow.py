"""Wizard support: prediction-only photographs and server-side training readiness."""

from uuid import UUID, uuid4

from aevyra_api.preferences.training_models import CustomModel
from test_credits import credits as credits
from test_credits import csrf_headers, register
from test_custom_training import execute, models, populated, train_job
from test_preferences import BASE, encoded, post, setup_dataset, upload


def readiness(fixture, dataset, **query):
    response = fixture.client.get(f"{BASE}/datasets/{dataset}/readiness", params=query)
    assert response.status_code == 200, response.text
    return response.json()


def test_prediction_photographs_never_enter_annotation_or_training(credits):
    dataset = populated(credits)
    photo = upload(credits, dataset, (240, 10, 10), purpose="prediction")
    assert photo.status_code == 200, photo.text
    image = photo.json()
    assert image["purpose"] == "prediction" and image["rating_recorded"] is False
    rating = post(credits, f"/datasets/{dataset}/images/{image['id']}/rating", {"score": 5})
    assert rating.status_code == 409
    detail = credits.client.get(f"{BASE}/datasets/{dataset}").json()
    other = next(i for i in detail["images"] if i["purpose"] == "annotation")
    pair = post(
        credits,
        f"/datasets/{dataset}/pairs",
        {"left_id": image["id"], "right_id": other["id"], "choice": "left"},
    )
    assert pair.status_code == 409
    state = readiness(credits, dataset)
    assert (state["prediction_only"], state["rated"], state["awaiting"]) == (1, 10, 0)
    train_job(credits, dataset)
    execute(credits)
    model = models(credits)[0]
    with credits.sessions() as session:
        snapshot = session.get(CustomModel, UUID(model["id"])).snapshot
    assert image["id"] not in {e["image_id"] for e in snapshot["examples"]}
    assert len(snapshot["examples"]) == 10
    prediction = post(
        credits,
        "/predict",
        {
            "model_id": model["id"],
            "dataset_id": dataset,
            "image_id": image["id"],
            "idempotency_key": str(uuid4()),
        },
    )
    assert prediction.status_code == 202, prediction.text
    execute(credits)
    result = credits.client.get(f"/api/v1/research/jobs/{prediction.json()['id']}").json()
    assert result["status"] == "COMPLETED"
    assert result["result"]["seen_in_training_snapshot"] is False


def test_duplicates_never_silently_change_purpose(credits):
    dataset = setup_dataset(credits)
    prediction = upload(credits, dataset, (9, 99, 199), purpose="prediction").json()
    again = upload(credits, dataset, (9, 99, 199))
    assert again.status_code == 409 and "prediction only" in again.json()["detail"]
    annotation = upload(credits, dataset, (1, 2, 3)).json()
    reused = upload(credits, dataset, (1, 2, 3), purpose="prediction").json()
    assert reused["id"] == annotation["id"] and reused["purpose"] == "annotation"
    assert prediction["purpose"] == "prediction"
    bad = post(
        credits,
        f"/datasets/{dataset}/images",
        {"content_base64": encoded("blue"), "adult_authorized_consent": True, "purpose": "train"},
    )
    assert bad.status_code == 422


def test_readiness_mirrors_training_requirements(credits):
    dataset = setup_dataset(credits)
    empty = readiness(credits, dataset)
    assert empty["eligible"] is False
    assert {"too_few_ratings", "too_few_groups"} <= set(empty["reasons"])
    assert (empty["required_ratings"], empty["required_groups"]) == (8, 5)
    ids = [
        upload(credits, dataset, (10 + i * 20, 40, 50), subject_group=f"p{i % 3}").json()["id"]
        for i in range(10)
    ]
    for index, image in enumerate(ids[:8]):
        post(credits, f"/datasets/{dataset}/images/{image}/rating", {"score": 1 + index})
    post(credits, f"/datasets/{dataset}/images/{ids[8]}/rating", {"score": None})
    post(
        credits,
        f"/datasets/{dataset}/images/{ids[9]}/edit",
        {"subject_group": None, "excluded": True},
    )
    grouped = readiness(credits, dataset)
    assert grouped["rated"] == 8 and grouped["groups"] == 3
    assert grouped["reasons"] == ["too_few_groups"]
    assert (grouped["awaiting"], grouped["skipped"], grouped["excluded"]) == (0, 1, 1)
    refused = post(credits, "/train", {"dataset_id": dataset, "idempotency_key": str(uuid4())})
    assert refused.status_code == 422  # The server agrees with the readiness answer.
    for index, image in enumerate(ids[:8]):
        post(
            credits,
            f"/datasets/{dataset}/images/{image}/edit",
            {"subject_group": f"person-{index}", "excluded": False},
        )
    ready = readiness(credits, dataset)
    assert ready["eligible"] is True and ready["reasons"] == []
    assert (
        credits.client.get(
            f"{BASE}/datasets/{dataset}/readiness", params={"validation_fraction": 0.9}
        ).status_code
        == 422
    )
    post(credits, f"/datasets/{dataset}/edit", {"name": "Synthetic test", "archived": True})
    assert readiness(credits, dataset)["reasons"] == ["archived"]


def test_readiness_is_private_to_the_dataset_owner(credits):
    dataset = setup_dataset(credits)
    credits.client.post("/api/v1/auth/logout", json={}, headers=csrf_headers(credits.client))
    assert credits.client.get(f"{BASE}/datasets/{dataset}/readiness").status_code == 401
    register(credits.client, "other@example.test")
    assert credits.client.get(f"{BASE}/datasets/{dataset}/readiness").status_code in {403, 404}
