import {expect, test} from "@playwright/test";
import {execFileSync} from "node:child_process";
import path from "node:path";

const root = path.resolve(__dirname, "../../..");
function compose(...args: string[]) {
  return execFileSync("docker", ["compose", "--env-file", ".env.cloud.local", "-p", "auvylen-phase4a-test",
    "-f", "docker-compose.prod.yml", "-f", "docker-compose.cloud.yml", "-f", "docker-compose.cloud.local.yml",
    "--profile", "research", ...args], {cwd: root, stdio: "pipe", maxBuffer: 8 * 1024 * 1024}).toString();
}

test("private images and annotations survive container recreation and worker deletion", async ({page}) => {
  const origin = "https://localhost:18443";
  const api = page.request;
  async function post(route: string, data: object) {
    const csrf = await api.get("/api/v1/auth/csrf").then(r => r.json());
    const response = await api.post(`/api/v1${route}`, {data, headers: {Origin: origin, "X-CSRF-Token": csrf.csrf_token}});
    expect(response.status()).toBe(200);
    return response.json();
  }
  const account = await post("/auth/register", {login_identifier: `cloud-preferences-${Date.now()}`, password: "test-only-private-image-password"});
  compose("exec", "-T", "api", "python", "-m", "aevyra_api.research.operator", "grant", account.user.public_user_id, "--reason", "Synthetic preference persistence test");
  const base = "/research/preferences";
  const project = await post(`${base}/projects`, {name: "Cloud persistence"});
  const dataset = await post(`${base}/datasets`, {project_id: project.id, name: "Private noise fixture", source: "Generated noise", license: "Test fixture", adult_authorized_consent: true});
  const encoded = compose("exec", "-T", "api", "python", "-c", "import base64; from io import BytesIO; from PIL import Image; b=BytesIO(); Image.effect_noise((1200,1200),100).convert('RGB').save(b,'PNG'); print(base64.b64encode(b.getvalue()).decode())").trim();
  expect(encoded.length).toBeGreaterThan(1024 * 1024); // Exercises the upload-specific Caddy limit.
  const photo = await post(`${base}/datasets/${dataset.id}/images`, {content_base64: encoded, adult_authorized_consent: true, subject_group: "synthetic-person-group"});
  await post(`${base}/datasets/${dataset.id}/images/${photo.id}/rating`, {score: 7.5});
  const url = `/api/v1${base}/datasets/${dataset.id}/images/${photo.id}/content`;
  const before = await api.get(url);
  expect(before.headers()["cache-control"]).toContain("no-store");
  const bytes = await before.body();
  compose("up", "-d", "--force-recreate", "--no-deps", "--wait", "api", "worker");
  expect((await api.get(url)).status()).toBe(200);
  expect(await api.get(url).then(r => r.body())).toEqual(bytes);
  const detail = await api.get(`/api/v1${base}/datasets/${dataset.id}`).then(r => r.json());
  expect(detail.images[0].score).toBe(7.5);
  expect(detail.images[0].subject_group).toBe("synthetic-person-group");
  await page.goto("/research/preferences");
  await page.getByRole("button", {name: "Private noise fixture · 1 images · 1 rated", exact: true}).click();
  await expect(page.getByLabel("Your rating")).toHaveValue("7.5");
  const artifacts = JSON.parse(compose("exec", "-T", "api", "python", "-c",
    "import json,sys; from uuid import UUID; from sqlalchemy import select; from aevyra_api.config import Settings; from aevyra_api.database import DependencyChecks; from aevyra_api.preferences.models import PreferenceImage,PreferenceDataset,PreferenceProject; c=DependencyChecks(Settings());\nwith c.sessions() as s:\n i=s.get(PreferenceImage,UUID(sys.argv[1])); owner=s.scalar(select(PreferenceProject.user_id).join(PreferenceDataset).where(PreferenceDataset.id==i.dataset_id)); print(json.dumps([str(owner),str(i.artifact_id),str(i.thumbnail_id)]))\nc.close()", photo.id));
  await post(`${base}/datasets/${dataset.id}/delete`, {});
  expect((await api.get(url)).status()).toBe(404);
  compose("restart", "worker");
  compose("up", "-d", "--wait");
  const deleted = compose("exec", "-T", "worker", "python", "-c", "import sys; from pathlib import Path; from aevyra_api.config import Settings; root=Settings().private_upload_root/'preferences'/sys.argv[1]; print(all(not (root / name).exists() for name in sys.argv[2:]))", ...artifacts).trim();
  expect(deleted).toBe("True");
  const balance = await api.get("/api/v1/account").then(r => r.json());
  expect(balance.wallet).toEqual({balance: 0, transactions: []});
});
