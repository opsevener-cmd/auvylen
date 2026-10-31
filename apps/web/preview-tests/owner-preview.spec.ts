import {expect, test} from "@playwright/test";
import {execFileSync} from "node:child_process";
import {randomBytes} from "node:crypto";
import {readFileSync, unlinkSync} from "node:fs";
import path from "node:path";

const root = path.resolve(__dirname, "../../..");
const composeArgs = ["compose", "-p", "auvylen-owner-test", "-f", ".devcontainer/compose.yml", "-f", ".devcontainer/compose.test.yml", "-f", ".devcontainer/compose.owner-test.yml"];
function compose(...args: string[]) {return execFileSync("docker", [...composeArgs, ...args], {cwd: root, stdio: "pipe", timeout: 90000}).toString();}
function control(action: string) {return compose("exec", "-T", "workspace", "python", "scripts/codespaces-preview.py", action);}

test("Owner private HTTPS administration, MobileNet research, isolation and restart", async ({page, browser}) => {
  test.setTimeout(240000);
  await page.setViewportSize({width: 390, height: 844});
  const api = page.request;
  const password = randomBytes(24).toString("base64url");
  const fixtureName = `Synthetic owner fixture ${Date.now()}`;
  const projectName = `Owner private preview ${Date.now()}`;
  const username = `owner-browser-fixture-${Date.now()}`;
  await page.goto("/register");
  await page.getByLabel("Username or email-like identifier").fill(username);
  await page.getByLabel("Password", {exact: true}).fill(password);
  await page.getByRole("button", {name: "Create account", exact: true}).click();
  await expect(page.getByText("Balance: 0 Credits", {exact: true})).toBeVisible();
  const ordinary = await page.request.get("/api/v1/auth/me").then(r => r.json());
  const ordinaryCookie = (await page.context().cookies()).find(c => c.name === "auvylen_session")!;
  await page.goto("/owner");
  await expect(page.getByText("Owner access required.", {exact: false})).toBeVisible();
  expect((await page.request.get("/api/v1/owner/users")).status()).toBe(403);
  // Fixture credentials never leave this isolated cloud test process or appear in argv/logs.
  execFileSync("docker", [...composeArgs, "exec", "-T", "workspace", "private-data/owner-test/venv/bin/python", "-c", `
import importlib.util,os,sys
spec=importlib.util.spec_from_file_location('preview','scripts/codespaces-preview.py'); p=importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
data,origin,secrets=p.context(); assert data.name=='owner-test' and os.environ.get('AUVYLEN_PREVIEW_TEST')=='1'
os.environ.update(p.environment(data,origin,secrets))
from aevyra_api.config import Settings
from aevyra_api.database import DependencyChecks
from aevyra_api.owner import provision,rotate
from aevyra_api.credits.models import User
from sqlalchemy import select
c=DependencyChecks(Settings())
with c.sessions() as s: existing=s.scalar(select(User).where(User.role=='owner')); public=existing.public_user_id if existing else None
password=sys.stdin.read()
if public: rotate(c.sessions,password,recovery_confirmation='RECOVER '+public)
else: provision(c.sessions,password)
c.close()
`], {cwd: root, stdio: "pipe", input: password, timeout: 30000});
  await page.goto("/login");
  await page.getByLabel("Username or email-like identifier").fill("owner_god");
  await page.getByLabel("Password", {exact: true}).fill(password);
  await page.getByRole("button", {name: "Sign in", exact: true}).click();
  await page.getByRole("link", {name: "Owner dashboard"}).click();
  await expect(page.getByRole("heading", {name: "Owner workspace"})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Platform overview"})).toBeVisible();
  const cookie = (await page.context().cookies()).find(c => c.name === "auvylen_session")!;
  expect(cookie.secure && cookie.httpOnly && cookie.sameSite === "Lax").toBe(true);
  const overview = await page.request.get("/api/v1/owner/overview").then(r => r.json());
  expect(overview.health.database).toBe("ok"); expect(overview.health.redis).toBe("ok");
  expect(overview.extractors.find((x: {id: string}) => x.id.includes("mobilenet")).available).toBe(true);
  expect(overview.providers.find((x: {slug: string}) => x.slug === "comboloss").available).toBe(false);
  const csrf = await page.request.get("/api/v1/auth/csrf").then(r => r.json());
  const target = `/api/v1/owner/users/${ordinary.user.public_user_id}/credits`;
  const command = {idempotency_key: crypto.randomUUID(), reason: "Synthetic browser test", amount: 1};
  expect((await page.request.post(target, {data: command})).status()).toBe(403);
  expect((await page.request.post(target, {data: command, headers: {Origin: "https://evil.example", "X-CSRF-Token": csrf.csrf_token}})).status()).toBe(403);
  await page.getByRole("button", {name: "Users & Credits", exact: true}).click();
  await page.getByLabel("Search users", {exact: true}).fill(username);
  await page.getByRole("button", {name: "Search", exact: true}).click();
  const row = page.getByRole("row").filter({hasText: username});
  await row.getByRole("button", {name: "Issue Credits", exact: true}).click();
  await page.getByLabel("Promotional Credits", {exact: true}).fill("25");
  await page.getByLabel("Audit reason", {exact: false}).fill("Synthetic promotion verification");
  await page.getByRole("button", {name: "Confirm change", exact: true}).click();
  await expect(page.getByText("Change saved and audited.", {exact: true})).toBeVisible();
  await row.getByRole("button", {name: "View ledger", exact: true}).click();
  await expect(page.getByRole("region", {name: "User Credits ledger"})).toContainText("25");
  for (const action of ["Grant research", "Disable", "Restore", "Revoke research"]) {
    await row.getByRole("button", {name: action, exact: true}).click();
    await page.getByLabel("Audit reason", {exact: false}).fill("Synthetic account controls verification");
    await page.getByRole("button", {name: "Confirm change", exact: true}).click();
    await expect(page.getByRole("region", {name: "Confirm administrative change"})).toHaveCount(0);
  }
  expect((await page.request.get("/api/v1/account", {headers: {Cookie: `auvylen_session=${ordinaryCookie.value}`}})).status()).toBe(401);
  await page.getByRole("button", {name: "Redemption", exact: true}).click();
  await page.getByRole("button", {name: "Create batch", exact: true}).click();
  await page.getByLabel("Batch name", {exact: true}).fill("Browser synthetic batch");
  await page.getByLabel("Number of codes", {exact: true}).fill("2");
  await page.getByLabel("Audit reason", {exact: false}).fill("Synthetic code security verification");
  await page.getByRole("button", {name: "Confirm change", exact: true}).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", {name: "Download codes once", exact: true}).click();
  const download = await downloadPromise;
  const downloaded = await download.path();
  const exported = JSON.parse(readFileSync(downloaded!, "utf8")); unlinkSync(downloaded!);
  expect(exported.codes.length).toBe(2);
  const auditText = await page.request.get("/api/v1/owner/audit").then(r => r.text());
  expect(auditText).not.toContain(exported.codes[0]);
  expect(await page.request.get("/api/v1/owner/batches").then(r => r.text())).not.toContain(exported.codes[0]);
  await page.getByRole("button", {name: "Clear codes from this page", exact: true}).click();
  const ordinaryContext = await browser.newContext({ignoreHTTPSErrors: true, baseURL: "https://localhost:19443"});
  const ordinaryPage = await ordinaryContext.newPage();
  await ordinaryPage.goto("/login");
  await ordinaryPage.getByLabel("Username or email-like identifier").fill(username);
  await ordinaryPage.getByLabel("Password", {exact: true}).fill(password);
  await ordinaryPage.getByRole("button", {name: "Sign in", exact: true}).click();
  await ordinaryPage.getByRole("link", {name: "Redeem Code", exact: true}).click();
  await ordinaryPage.getByLabel("Redemption Code", {exact: true}).fill(exported.codes[0]);
  await ordinaryPage.getByRole("button", {name: "Redeem", exact: true}).click();
  await expect(ordinaryPage.getByText("10 Credits added", {exact: true})).toBeVisible();
  await ordinaryContext.close();
  const batchRow = page.getByRole("row").filter({hasText: exported.public_batch_id});
  await batchRow.getByRole("button", {name: "Disable batch", exact: true}).click();
  await page.getByLabel("Audit reason", {exact: false}).fill("Synthetic batch completed");
  await page.getByRole("button", {name: "Confirm change", exact: true}).click();
  await expect(batchRow).toContainText("false");
  await page.getByRole("button", {name: "Audit trail", exact: true}).click();
  await expect(page.getByRole("row").filter({hasText: exported.public_batch_id}).getByRole("cell", {name: "batch.disable", exact: true})).toBeVisible();
  await page.getByText("Confirm fresh authentication", {exact: true}).click();
  await page.getByLabel("Current password", {exact: true}).fill(password);
  await page.getByRole("button", {name: "Confirm password", exact: true}).click();
  await expect(page.getByText("Fresh sign-in confirmed.", {exact: true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({width: 1365, height: 900});
  await page.goto("/research/preferences");
  await page.getByLabel("Project name", {exact: true}).fill(projectName);
  await page.getByRole("button", {name: "Create project", exact: true}).click();
  await page.getByLabel("Dataset name", {exact: true}).fill(fixtureName);
  await page.getByLabel("Source", {exact: true}).fill("Generated synthetic colors");
  await page.getByLabel("License and restrictions").fill("Synthetic software fixtures; no real faces");
  await page.getByLabel("I confirm every subject").check();
  await page.getByRole("button", {name: "Save dataset"}).click();
  const pictures: string[] = JSON.parse(compose("exec", "-T", "workspace", "private-data/owner-test/venv/bin/python", "-c", "import base64,json; from PIL import Image; from io import BytesIO; result=[]\nfor value in list(range(20,220,20))+[125]:\n b=BytesIO(); Image.new('RGB',(80,80),(value,40,50)).save(b,'PNG'); result.append(base64.b64encode(b.getvalue()).decode())\nprint(json.dumps(result))"));
  const files = pictures.map((value, i) => ({name: `synthetic-${i}.png`, mimeType: "image/png", buffer: Buffer.from(value, "base64")}));
  await page.getByLabel("Adult photographs", {exact: true}).setInputFiles(files.slice(0, 10));
  await page.getByLabel("I confirm every subject").last().check();
  await page.getByRole("button", {name: "Upload photographs", exact: true}).click();
  await expect(page.getByText("10 photographs saved · 10 awaiting rating", {exact: false})).toBeVisible();
  await page.getByRole("button", {name: "Continue to rating", exact: true}).click();
  for (let i = 0; i < 10; i++) {
    await page.getByLabel("Your rating").fill(String(1 + i * 0.8));
    await page.getByRole("button", {name: i < 9 ? "Save and next" : "Save rating", exact: true}).click();
    if (i < 9) await expect(page.getByText(`Image ${i + 2} of 10`, {exact: true})).toBeVisible();
  }
  await expect(page.getByRole("heading", {name: "Every photograph has been processed."})).toBeVisible();
  await page.getByRole("combobox", {name: "Visual feature extractor", exact: true}).selectOption("mobilenetv3-small-imagenet-onnx-v1");
  await page.getByRole("button", {name: "Train new version", exact: true}).click();
  await expect(page.getByText("Version 1 · READY · mobilenetv3-small-imagenet-onnx-v1", {exact: true})).toBeVisible({timeout: 30000});
  await page.getByRole("button", {name: "Previous step", exact: true}).click();
  await page.getByLabel("Adult photographs", {exact: true}).setInputFiles(files[10]);
  await page.getByLabel("I confirm every subject").last().check();
  await page.getByRole("button", {name: "Upload photographs", exact: true}).click();
  await expect(page.getByText("11 photographs saved · 1 awaiting rating", {exact: false})).toBeVisible();
  await page.getByRole("button", {name: "Continue to rating", exact: true}).click();
  await page.getByLabel("Photograph to predict").selectOption({label: "Image 11 · unrated"});
  await page.getByRole("button", {name: "Predict personal rating", exact: true}).click();
  await expect(page.getByText("Predicted personal rating:", {exact: false})).toBeVisible({timeout: 30000});
  await expect(page.getByText("This photograph was unseen in the model's annotation snapshot.", {exact: true})).toBeVisible();
  const jobs = await api.get("/api/v1/research/jobs").then(r => r.json());
  const before = jobs.find((j: {result?: {prediction_type?: string; raw_score?: number}}) => j.result?.prediction_type === "subjective_rating" && typeof j.result?.raw_score === "number").result;
  expect(Number.isFinite(before.raw_score)).toBe(true);
  await page.getByRole("button", {name: "Select image 11", exact: true}).click();
  await page.getByLabel("Your rating").fill("5.5");
  await page.getByRole("button", {name: "Save rating", exact: true}).click();
  await expect(page.getByText("Ready to train with 11 valid ratings", {exact: false})).toBeVisible();
  await page.getByRole("button", {name: "Train new version", exact: true}).click();
  await expect(page.getByText("Version 2 · READY · mobilenetv3-small-imagenet-onnx-v1", {exact: true})).toBeVisible({timeout: 30000});
  expect((await api.get("/private-data/owner-test/models/pretrained/mobilenetv3-small-100-lamb-embedding-v1.onnx")).status()).toBe(404);
  expect((await page.request.get("/api/v1/account").then(r => r.json())).wallet.balance).toBe(0);
  control("stop"); control("start");
  await page.reload(); // The wizard restores the same dataset and step from the URL.
  await expect(page.getByText("Version 2 · READY · mobilenetv3-small-imagenet-onnx-v1", {exact: true})).toBeVisible();
  await page.goto("/owner");
  await expect(page.getByRole("heading", {name: "Platform overview"})).toBeVisible();
  expect((await page.request.get("/api/v1/auth/me").then(r => r.json())).user.role).toBe("owner");
  if (process.env.OWNER_TEST_SCREENSHOT) await page.screenshot({path: process.env.OWNER_TEST_SCREENSHOT, fullPage: true});
});

test("Owner encrypted backup restores role, audit, ledger and private model files", async () => {
  test.setTimeout(120000);
  const backup = execFileSync("docker", [...composeArgs, "exec", "-T", "workspace", "python", "scripts/codespaces-preview.py", "backup"], {cwd: root, stdio: "pipe", input: "synthetic-backup-passphrase-only\n", timeout: 90000}).toString();
  expect(backup).toContain("Encrypted consistent backup:");
  // Decrypt internally without printing archive bytes/secrets; restore the dump into a
  // disposable DB and compare private file bytes with the live synthetic fixture.
  const verification = compose("exec", "-T", "workspace", "private-data/owner-test/venv/bin/python", "-c", `
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
  def query(sql):
   return subprocess.check_output(['psql','-h','postgres','-U','aevyra','-d',name,'-Atc',sql],env=env).strip()
  assert query("select count(*) from users where role='owner' and login_identifier='owner_god'")==b'1'
  assert int(query("select count(*) from admin_audit where action='credits.grant'"))>=1
  assert query("select count(*) from wallets w where w.cached_balance != (select coalesce(sum(amount),0) from credit_transactions t where t.wallet_id=w.id)")==b'0'
  assert query("select count(*) from pg_trigger where tgname='guard_owner'")==b'1'
 finally: subprocess.run(['dropdb','-h','postgres','-U','aevyra',name],env=env,check=True)
print('Encrypted backup, private files and database restore verified')
`);
  expect(verification).toContain("database restore verified");
});
