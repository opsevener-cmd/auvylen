"""Generated pictures and generated ratings only. Never evidence about real people."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auvylen7b import data  # noqa: E402
from auvylen7b.encoders import embed  # noqa: E402
from auvylen7b.evaluate import REFERENCE, evaluate  # noqa: E402
from auvylen7b.heads import earth_movers, fit_distribution  # noqa: E402
from auvylen7b.store import Store  # noqa: E402


def fake_loader(encoder, device):
    """Deterministic generated features: mean colour plus encoder-specific noise dimensions."""
    rng = np.random.default_rng(len(encoder.name))

    def prepare(images):
        return np.stack(
            [np.asarray(i.resize((16, 16)), dtype=np.float64).mean((0, 1)) / 255 for i in images]
        )

    projection = rng.normal(size=(3, 24))

    def forward(x):
        signal = x @ projection
        noise = rng.normal(
            scale=0.5 if encoder.name == "mobilenetv3-small" else 0.05, size=signal.shape
        )
        return signal + noise

    return prepare, forward


def run(tmp_path, calls):
    def counting(encoder, device):
        calls.append(encoder.name)
        return fake_loader(encoder, device)

    dataset = data.synthetic(tmp_path / "work")
    store = Store(tmp_path / "store")
    shards = embed(
        store, dataset, ["mobilenetv3-small", "dinov2-small"], device="numpy", loader=counting
    )
    return store, dataset, shards


def test_pipeline_resumes_without_recomputing_finished_shards(tmp_path):
    calls: list[str] = []
    store, dataset, shards = run(tmp_path, calls)
    assert sorted(set(calls)) == ["dinov2-small", "mobilenetv3-small"]
    first = store.ledger.read_text().count("\n")
    calls.clear()
    run(tmp_path, calls)
    assert calls == [] and store.ledger.read_text().count("\n") == first
    # Simulate a disconnect that lost one shard: only that encoder is reloaded.
    store.path(shards["dinov2-small/crop"]).unlink()
    run(tmp_path, calls)
    assert calls == ["dinov2-small"]


def test_evaluation_is_paired_cached_and_marks_generated_data(tmp_path):
    store, dataset, shards = run(tmp_path, [])
    result = evaluate(store, dataset, shards, ["mobilenetv3-small", "dinov2-small"])
    assert result["synthetic"] is True and result["subjects"] == 48
    summary = result["summary"]
    assert summary["dinov2-small/ridge"]["mae"] < summary["train-mean"]["mae"]
    assert summary["dinov2-small/distribution"]["emd"] < summary["train-average-histogram"]["emd"]
    assert REFERENCE in summary and set(result["vs_reference"]) == {
        "mobilenetv3-small/distribution",
        "dinov2-small/ridge",
        "dinov2-small/distribution",
    }
    assert evaluate(store, dataset, shards, ["mobilenetv3-small", "dinov2-small"]) == result


def test_distribution_head_recovers_generated_histograms():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(120, 6))
    centre = 4 + 1.2 * x[:, 0]
    logits = -((np.arange(1, 8)[None, :] - centre[:, None]) ** 2) / 2
    targets = np.exp(logits) / np.exp(logits).sum(1, keepdims=True)
    head = fit_distribution(x[:90], targets[:90], 0.01)
    fitted = earth_movers(head.distribution(x[90:]), targets[90:])
    baseline = earth_movers(np.tile(targets[:90].mean(0), (30, 1)), targets[90:])
    assert fitted < 0.5 * baseline
    assert np.allclose(head.distribution(x[:3]).sum(1), 1)
    with pytest.raises(ValueError):
        fit_distribution(x, targets[:5], 0.1)


def test_store_writes_atomically_inside_its_root(tmp_path):
    store = Store(tmp_path)
    store.write_json("a/b.json", {"x": 1})
    assert store.read_json("a/b.json") == {"x": 1}
    assert not list(tmp_path.rglob("*.tmp"))
    with pytest.raises(ValueError):
        store.path("..", "escape.json")


# --- Dataset rights: the release gate's own rules --------------------------------------------

ROOT = Path(__file__).resolve().parents[3]


def test_london_is_admitted_for_research_but_can_never_pass_the_release_gate():
    from aevyra_inference.aesthetic_checkpoint import rights_failures

    data.admit(data.LONDON_RIGHTS)
    assert rights_failures(data.LONDON_RIGHTS) == ["commercial_use_not_permitted"]
    assert data.LONDON_RIGHTS.adult_age_verification == "documented"
    assert "CC BY 4.0" in data.LONDON_RIGHTS.license
    assert "signed consent" in (data.LONDON_RIGHTS.subject_consent_reference or "")


@pytest.mark.parametrize(
    ("changes", "failure"),
    [
        ({"name": "SCUT-FBP5500"}, "excluded_dataset"),
        (
            {"terms_url": "https://github.com/HCIILAB/SCUT-FBP5500-Database-Release"},
            "excluded_dataset",
        ),
        ({"name": "MEBeauty"}, "excluded_dataset"),
        ({"name": "Chicago Face Database"}, "excluded_dataset"),
        ({"license": "Non-commercial research use only"}, "restricted_license"),
        ({"license": "CC BY-NC 4.0"}, "restricted_license"),
        ({"subject_consent_reference": None}, "subject_consent_missing"),
        ({"adult_age_verification": None}, "adult_age_unverified"),
    ],
)
def test_restricted_or_undocumented_sources_are_refused(changes, failure):
    from dataclasses import replace

    with pytest.raises(ValueError, match=failure):
        data.admit(replace(data.LONDON_RIGHTS, **changes))


def test_a_refused_source_is_never_fetched(monkeypatch, tmp_path):
    from dataclasses import replace

    def no_network(*args, **kwargs):
        raise AssertionError("nothing may be cloned or read before admission")

    monkeypatch.setattr(data, "LONDON_RIGHTS", replace(data.LONDON_RIGHTS, name="SCUT-FBP5500"))
    monkeypatch.setattr(data.subprocess, "run", no_network)
    with pytest.raises(ValueError, match="excluded_dataset"):
        data.london(tmp_path)
    assert not (tmp_path / "london").exists() and not (tmp_path / "clones").exists()


def test_cli_offers_only_london_and_generated_data():
    source = (ROOT / "research/phase7b/auvylen7b/__main__.py").read_text()
    assert 'choices=["synthetic", "london"]' in source


def test_research_code_and_dependencies_stay_out_of_production_images():
    import tomllib

    for dockerfile in ("services/api/Dockerfile", "apps/web/Dockerfile"):
        text = (ROOT / dockerfile).read_text()
        assert "research" not in text, dockerfile
    for compose in ROOT.glob("docker-compose*.yml"):
        assert "research/" not in compose.read_text(), compose.name
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    members = project["tool"]["uv"]["workspace"]["members"]
    assert not any(member.startswith("research") for member in members)
    runtime = " ".join(project["project"].get("dependencies", []))
    for heavy in ("torch", "timm", "transformers", "open_clip"):
        assert heavy not in runtime
    # Heavy encoders are imported only inside functions, never at module import.
    import sys as system

    assert not any(name in system.modules for name in ("torch", "timm"))
