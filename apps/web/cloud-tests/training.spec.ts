import {expect, test} from "@playwright/test";
import {execFileSync} from "node:child_process";
import path from "node:path";

const root = path.resolve(__dirname, "../../..");
function compose(...args: string[]) {
  return execFileSync("docker", ["compose", "--env-file", ".env.cloud.local", "-p", "auvylen-phase4a-test",
    "-f", "docker-compose.prod.yml", "-f", "docker-compose.cloud.yml", "-f", "docker-compose.cloud.local.yml",
    "--profile", "research", ...args], {cwd: root, stdio: "pipe"}).toString();
}

test("real model checkpoints and predictions persist across container recreation", async ({page}) => {
  const api = page.request;
  async function post(route: string, data: object, status = 200) {
    const csrf = await api.get("/api/v1/auth/csrf").then(r => r.json());
    const response = await api.post(`/api/v1${route}`, {data, headers: {Origin: "https://localhost:18443", "X-CSRF-Token": csrf.csrf_token}});
    expect(response.status(), route).toBe(status);
    return response.json();
  }
  async function completed(id: string) {
    await expect.poll(async () => (await api.get(`/api/v1/research/jobs/${id}`).then(r => r.json())).status, {timeout: 20000}).toBe("COMPLETED");
    return api.get(`/api/v1/research/jobs/${id}`).then(r => r.json());
  }
  const account = await post("/auth/register", {login_identifier: `cloud-training-${Date.now()}`, password: "test-only-cloud-training-password"});
  compose("exec", "-T", "api", "python", "-m", "aevyra_api.research.operator", "grant", account.user.public_user_id, "--reason", "Synthetic model persistence test");
  const base = "/research/preferences";
  const project = await post(`${base}/projects`, {name: "Cloud models"});
  const dataset = await post(`${base}/datasets`, {project_id: project.id, name: "Model persistence", source: "Generated colors", license: "Generated fixtures", adult_authorized_consent: true});
  const payloads: string[] = JSON.parse(compose("exec", "-T", "api", "python", "-c", "import json,base64; from io import BytesIO; from PIL import Image; result=[]\nfor value in list(range(20,220,20))+[125]:\n b=BytesIO(); Image.new('RGB',(80,80),(value,40,50)).save(b,'PNG'); result.append(base64.b64encode(b.getvalue()).decode())\nprint(json.dumps(result))"));
  for (let i = 0; i < 10; i++) {
    const image = await post(`${base}/datasets/${dataset.id}/images`, {content_base64: payloads[i], adult_authorized_consent: true, subject_group: `person-${Math.floor(i/2)}`});
    await post(`${base}/datasets/${dataset.id}/images/${image.id}/rating`, {score: 1 + i * 0.8});
  }
  const queued = await post(`${base}/train`, {dataset_id: dataset.id, idempotency_key: crypto.randomUUID()}, 202);
  const trained = await completed(queued.id);
  expect(trained.result.metrics.labeled_images).toBe(10);
  expect(trained.result.synthetic).toBe(false);
  const modelId = trained.result.model_id;
  const unseen = await post(`${base}/datasets/${dataset.id}/images`, {content_base64: payloads[10], adult_authorized_consent: true, subject_group: "person-unseen"});
  async function predict() {
    const job = await post(`${base}/predict`, {model_id: modelId, dataset_id: dataset.id, image_id: unseen.id, idempotency_key: crypto.randomUUID()}, 202);
    return (await completed(job.id)).result;
  }
  const before = await predict();
  expect(before.seen_in_training_snapshot).toBe(false);
  expect(before.synthetic).toBe(false);
  expect(Number.isFinite(before.raw_score)).toBe(true);
  compose("up", "-d", "--force-recreate", "--no-deps", "--wait", "api", "worker", "web");
  const after = await predict();
  expect(after.raw_score).toBe(before.raw_score);
  expect(after.model_id).toBe(modelId);
  await page.goto("/research/preferences");
  await page.getByRole("button", {name: "Model persistence · 11 images · 10 rated", exact: true}).click();
  await expect(page.getByText("Version 1 · READY · rgb-grid-texture-v1", {exact: true})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Validation for version 1"})).toBeVisible();
  await post(`${base}/datasets/${dataset.id}/images/${unseen.id}/rating`, {score: 5.5});
  const retrain = await post(`${base}/train`, {dataset_id: dataset.id, idempotency_key: crypto.randomUUID()}, 202);
  expect((await completed(retrain.id)).result.model_version).toBe(2);
  const versions = await api.get(`/api/v1${base}/models`).then(r => r.json());
  expect(versions.map((m: {version: number}) => m.version)).toEqual([2, 1]);
  const wallet = await api.get("/api/v1/account").then(r => r.json());
  expect(wallet.wallet).toEqual({balance: 0, transactions: []});
  // Remove generated test data through owner APIs; worker cleanup keeps volumes private.
  await post(`${base}/datasets/${dataset.id}/delete`, {});
  compose("restart", "worker");
  compose("up", "-d", "--wait");
  expect((await api.get(`/api/v1${base}/models`).then(r => r.json())).every((m: {state: string}) => m.state === "DELETED")).toBe(true);
});
