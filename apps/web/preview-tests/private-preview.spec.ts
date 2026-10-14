import {expect, test} from "@playwright/test";
import {execFileSync} from "node:child_process";
import path from "node:path";

const root = path.resolve(__dirname, "../../..");
const composeArgs = ["compose", "-p", "auvylen-codespaces-test", "-f", ".devcontainer/compose.yml", "-f", ".devcontainer/compose.test.yml"];
function compose(...args: string[]) {return execFileSync("docker", [...composeArgs, ...args], {cwd: root, stdio: "pipe", timeout: 90000}).toString();}
function control(action: string, value?: string) {return compose("exec", "-T", "workspace", "python", "scripts/codespaces-preview.py", action, ...(value ? [value] : []));}

test("private HTTPS preview: consent, annotations, MobileNet versions, prediction, resume and encrypted backup", async ({page}) => {
  test.setTimeout(240000);
  const api = page.request;
  expect((await api.get("/api/v1/research/preferences/projects")).status()).toBe(401);
  const username = `private-preview-${Date.now()}`;
  await page.goto("/register");
  await page.getByLabel("Username or email-like identifier").fill(username);
  await page.getByLabel("Password", {exact: true}).fill("synthetic-preview-test-password");
  await page.getByRole("button", {name: "Create account", exact: true}).click();
  await expect(page.getByText("Balance: 0 Credits", {exact: true})).toBeVisible();
  const cookie = (await page.context().cookies()).find(c => c.name === "auvylen_session");
  expect(cookie?.secure).toBe(true); expect(cookie?.httpOnly).toBe(true); expect(cookie?.sameSite).toBe("Lax");
  expect((await api.get("/api/v1/research/preferences/projects")).status()).toBe(403);
  control("grant", username);
  expect((await api.get("/api/v1/research/preferences/projects")).status()).toBe(200);
  const csrf = await api.get("/api/v1/auth/csrf").then(r => r.json());
  expect((await api.post("/api/v1/research/preferences/projects", {data: {name: "rejected"}, headers: {Origin: "https://localhost:19443"}})).status()).toBe(403);
  expect((await api.post("/api/v1/research/preferences/projects", {data: {name: "rejected"}, headers: {Origin: "https://attacker.example", "X-CSRF-Token": csrf.csrf_token}})).status()).toBe(403);
  await page.goto("/research/preferences");
  await page.getByLabel("Project name", {exact: true}).fill("Private preview");
  await page.getByRole("button", {name: "Create project", exact: true}).click();
  await page.getByText("Create a dataset", {exact: true}).click();
  await page.getByLabel("Dataset name", {exact: true}).fill("Synthetic preview fixture");
  await page.getByLabel("Source", {exact: true}).fill("Generated synthetic colors");
  await page.getByLabel("License and restrictions").fill("Synthetic software fixtures; no real faces");
  await page.getByLabel("I confirm every subject").check();
  await page.getByRole("button", {name: "Save dataset"}).click();
  const pictures: string[] = JSON.parse(compose("exec", "-T", "workspace", "private-data/codespaces-test/venv/bin/python", "-c", "import base64,json; from PIL import Image; from io import BytesIO; result=[]\nfor value in list(range(20,220,20))+[125]:\n b=BytesIO(); Image.new('RGB',(80,80),(value,40,50)).save(b,'PNG'); result.append(base64.b64encode(b.getvalue()).decode())\nprint(json.dumps(result))"));
  const files = pictures.map((value, i) => ({name: `synthetic-${i}.png`, mimeType: "image/png", buffer: Buffer.from(value, "base64")}));
  await page.getByLabel("Adult photographs", {exact: true}).setInputFiles(files.slice(0, 10));
  await page.getByLabel("I confirm every subject").last().check();
  await page.getByRole("button", {name: "Upload photographs"}).click();
  await expect(page.getByText("10 images · 0 rated · 0 comparisons · 10 awaiting rating", {exact: true})).toBeVisible();
  for (let i = 0; i < 10; i++) {
    await page.getByLabel("Your rating").fill(String(1 + i * 0.8));
    await page.getByRole("button", {name: "Save and next", exact: true}).click();
    if (i < 9) await expect(page.getByText(`Image ${i + 2} of 10`, {exact: true})).toBeVisible();
  }
  await page.getByRole("combobox", {name: "Visual feature extractor", exact: true}).selectOption("mobilenetv3-small-imagenet-onnx-v1");
  await page.getByRole("button", {name: "Train new version", exact: true}).click();
  await expect(page.getByText("Version 1 · READY · mobilenetv3-small-imagenet-onnx-v1", {exact: true})).toBeVisible({timeout: 30000});
  await page.getByLabel("Adult photographs", {exact: true}).setInputFiles(files[10]);
  await page.getByLabel("I confirm every subject").last().check();
  await page.getByRole("button", {name: "Upload photographs"}).click();
  await expect(page.getByText("11 images · 10 rated · 0 comparisons · 1 awaiting rating", {exact: true})).toBeVisible();
  await page.getByLabel("Photograph to predict").selectOption({label: "Image 11 · unrated"});
  await page.getByRole("button", {name: "Predict personal rating", exact: true}).click();
  await expect(page.getByText("Predicted personal rating:", {exact: false})).toBeVisible({timeout: 30000});
  await expect(page.getByText("This photograph was unseen in the model's annotation snapshot.", {exact: true})).toBeVisible();
  const jobs = await api.get("/api/v1/research/jobs").then(r => r.json());
  const before = jobs.find((j: {result?: {prediction_type?: string; raw_score?: number}}) => j.result?.prediction_type === "subjective_rating" && typeof j.result?.raw_score === "number").result;
  expect(Number.isFinite(before.raw_score)).toBe(true);
  await page.getByRole("button", {name: "Select image 11", exact: true}).click();
  await page.getByLabel("Your rating").fill("5.5");
  await page.getByRole("button", {name: "Save and next", exact: true}).click();
  await page.getByRole("button", {name: "Train new version", exact: true}).click();
  await expect(page.getByText("Version 2 · READY · mobilenetv3-small-imagenet-onnx-v1", {exact: true})).toBeVisible({timeout: 30000});
  expect((await api.get("/private-data/codespaces-test/models/pretrained/mobilenetv3-small-100-lamb-embedding-v1.onnx")).status()).toBe(404);
  control("stop");
  compose("restart", "postgres", "redis");
  compose("up", "-d", "--wait", "postgres", "redis");
  control("start");
  // Recreate while running, including recovery of a stale supervisor socket.
  compose("up", "-d", "--no-deps", "--force-recreate", "workspace");
  control("start");
  await page.reload();
  await page.getByRole("button", {name: "Synthetic preview fixture · 11 images · 11 rated", exact: true}).click();
  await expect(page.getByText("Version 1 · READY · mobilenetv3-small-imagenet-onnx-v1", {exact: true})).toBeVisible();
  await expect(page.getByText("Version 2 · READY · mobilenetv3-small-imagenet-onnx-v1", {exact: true})).toBeVisible();
  await page.getByLabel("Model version").selectOption({index: 2});
  await page.getByLabel("Photograph to predict").selectOption({label: "Image 11 · rated"});
  await page.getByRole("button", {name: "Predict personal rating", exact: true}).click();
  await expect(page.getByText("Predicted personal rating:", {exact: false})).toBeVisible({timeout: 30000});
  const afterJobs = await api.get("/api/v1/research/jobs").then(r => r.json());
  const after = afterJobs.find((j: {result?: {model_version?: number; raw_score?: number}}) => j.result?.model_version === 1 && typeof j.result?.raw_score === "number").result;
  expect(after.raw_score).toBe(before.raw_score);
  const backup = execFileSync("docker", [...composeArgs, "exec", "-T", "workspace", "python", "scripts/codespaces-preview.py", "backup"], {cwd: root, stdio: "pipe", input: "synthetic-backup-passphrase-only\n", timeout: 90000}).toString();
  expect(backup).toContain("Encrypted consistent backup:");
  // Decrypt internally without printing archive bytes/secrets; restore the dump into a
  // disposable DB and compare private file bytes with the live synthetic fixture.
  const verification = compose("exec", "-T", "workspace", "private-data/codespaces-test/venv/bin/python", "-c", `
import io,json,subprocess,tarfile,tempfile,uuid,importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('preview', 'scripts/codespaces-preview.py'); p=importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
data,origin,secrets=p.context(); env=p.environment(data,origin,secrets)
backup=sorted(Path('backups/codespaces').glob('*.gpg'))[-1]
raw=subprocess.check_output(['gpg','--batch','--pinentry-mode','loopback','--passphrase-fd','0','--decrypt',str(backup)],input=b'synthetic-backup-passphrase-only\\n',stderr=subprocess.DEVNULL)
tar=tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz')
for member in tar.getmembers():
 if member.isfile() and (member.name.startswith('uploads/') or member.name.startswith('models/')):
  assert tar.extractfile(member).read()==(data/member.name).read_bytes()
env['PGPASSWORD']=json.loads((data/'credentials.json').read_text())['postgres_password']
name='preview_restore_'+uuid.uuid4().hex
with tempfile.TemporaryDirectory() as temp:
 dump=Path(temp)/'database.dump'; dump.write_bytes(tar.extractfile('database.dump').read())
 subprocess.run(['createdb','-h','postgres','-U','aevyra',name],env=env,check=True,stdout=subprocess.DEVNULL)
 try:
  subprocess.run(['pg_restore','--exit-on-error','--no-owner','--no-acl','-h','postgres','-U','aevyra','-d',name,str(dump)],env=env,check=True,stdout=subprocess.DEVNULL)
  count=subprocess.check_output(['psql','-h','postgres','-U','aevyra','-d',name,'-Atc',"select count(*) from custom_preference_models where state='READY'"],env=env).strip()
  assert int(count)>=2
 finally: subprocess.run(['dropdb','-h','postgres','-U','aevyra',name],env=env,check=True)
print('Encrypted backup, private files and database restore verified')
`);
  expect(verification).toContain("database restore verified");
  await page.goto("/account");
  await expect(page.getByText("Balance: 0 Credits", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "Sign out", exact: true}).click();
  await page.goto("/login");
  await page.getByLabel("Username or email-like identifier").fill(username);
  await page.getByLabel("Password", {exact: true}).fill("synthetic-preview-test-password");
  await page.getByRole("button", {name: "Sign in", exact: true}).click();
  await expect(page.getByText("Balance: 0 Credits", {exact: true})).toBeVisible();
});
