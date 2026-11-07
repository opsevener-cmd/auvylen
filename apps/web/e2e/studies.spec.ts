import {test, expect, type APIRequestContext} from "@playwright/test";
import {execFileSync} from "node:child_process";
import path from "node:path";

test.skip(process.env.E2E_STUDY_FIXTURES !== "true", "Requires the disposable SQLite study-fixture server");
const origin = "http://127.0.0.1:3148";
const base = "/api/v1/research/studies";
const password = "synthetic-study-fixture-password-only";
const command = () => ({idempotency_key: crypto.randomUUID()});
async function post(api: APIRequestContext, endpoint: string, data: object) {
  const csrf = await (await api.get("/api/v1/auth/csrf")).json();
  return api.post(endpoint,{data,headers:{Origin:origin,"X-CSRF-Token":csrf.csrf_token}});
}
async function login(api: APIRequestContext, name: string) {
  const response = await post(api,"/api/v1/auth/login",{login_identifier:name,password});
  expect(response.status()).toBe(200);
}

// A generated colour pattern, never a private photograph or a synthetic model score.
const image = () => Buffer.from(execFileSync("uv",["run","python","-c","import base64, random; from PIL import Image; from io import BytesIO; i=Image.frombytes('RGB',(768,768),random.Random(714).randbytes(768*768*3)); o=BytesIO(); i.save(o,'PNG'); print(base64.b64encode(o.getvalue()).decode())"],{cwd:path.resolve(__dirname,"../../.."),encoding:"utf8",maxBuffer:4*1024*1024}).trim(),"base64");

test("real browser/API study workflow: consent, verification, upload, independent votes, export and removal", async ({page,browser}) => {
  test.setTimeout(120000);
  const errors: string[]=[];page.on("pageerror", e=>errors.push(e.message));
  await login(page.request,"owner_god");
  await page.goto("/research/studies");
  await page.getByText("Create an Owner-managed study",{exact:true}).click();
  await page.getByLabel("Study title",{exact:true}).fill("Phase 7A authorized fixture");
  await page.getByRole("button",{name:"Create study draft",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Phase 7A authorized fixture",exact:true})).toBeVisible();
  const study=new URL(page.url()).searchParams.get("study")!;
  await page.getByText("Publish a new consent version",{exact:true}).click();
  await page.getByLabel("Removal contact and operator · English",{exact:true}).fill("Test operator, no real contact");
  await page.getByLabel("Removal contact and operator · 简体中文",{exact:true}).fill("测试负责人，不进行真实联系");
  await page.getByLabel("Rights review reference",{exact:true}).fill("authorized-generated-fixtures-v1");
  await page.getByRole("button",{name:"Publish immutable consent version",exact:true}).click();
  await expect(page.getByText("Read the exact consent version: 1",{exact:true})).toBeVisible();
  const issued=page.waitForResponse(r=>r.url().endsWith(`/${study}/action`)&&r.request().method()==="POST");
  await page.getByRole("button",{name:"Create or rotate invitation",exact:true}).click();
  const code=(await (await issued).json()).value;
  await expect(page.getByText(code,{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Hide private invitation",exact:true}).click();
  await page.getByRole("button",{name:"Open collection",exact:true}).click();
  await expect(page.getByText("Study action saved.",{exact:true})).toBeVisible();
  const contributorContext=await browser.newContext({baseURL:origin,viewport:{width:390,height:844},reducedMotion:"reduce"});
  const contributor=await contributorContext.newPage();
  await login(contributor.request,"study-fixture-contributor");
  await contributor.goto("/research/studies");
  await contributor.getByLabel("Private invitation code",{exact:true}).fill(code);
  await contributor.getByRole("button",{name:"Read study invitation",exact:true}).click();
  await expect(contributor.getByRole("heading",{name:"Phase 7A authorized fixture",exact:true})).toBeVisible();
  await contributor.getByRole("button",{name:"中文",exact:true}).click();
  await contributor.getByLabel("我确认已年满 18 周岁。",{exact:true}).check();
  await contributor.getByLabel("我已阅读并理解本版本，且自愿参与。",{exact:true}).check();
  await contributor.getByLabel("我同意所述私密研究处理、人工评分及衍生研究模型使用，不授权商业使用或公开展示。",{exact:true}).check();
  await contributor.getByLabel("我确认这是已获授权的测试流程，不进行真实参与者采集。",{exact:true}).check();
  await contributor.getByRole("button",{name:"同意本版本",exact:true}).click();
  await expect(contributor.getByRole("button",{name:"下载我的同意回执"})).toBeVisible();
  const data=await (await page.request.get(`${base}/${study}`)).json();
  const member=data.members.find((m:{role:string})=>m.role==="contributor");
  expect((await post(page.request,`${base}/${study}/members/${member.id}/review`,{...command(),approved:true,verification_reference:"fixture-browser-independent-subject"})).status()).toBe(200);
  await contributor.getByRole("button",{name:"刷新研究状态",exact:true}).click();
  const fixtureImage=image();expect(fixtureImage.byteLength).toBeGreaterThan(1024*1024);
  await contributor.getByLabel("您本人的成人肖像",{exact:true}).setInputFiles({name:"authorized-generated-fixture.png",mimeType:"image/png",buffer:fixtureImage});
  await contributor.getByLabel("这是我本人的成人肖像，或测试研究中已获授权的生成素材。我拥有必要的照片使用权。",{exact:true}).check();
  const uploadButton=contributor.getByRole("button",{name:"上传肖像并等待审核",exact:true});
  // Fail before transmission, then retry the same file/key; never fabricate a saved response.
  await contributor.route(`**/studies/${study}/photos`,route=>route.fulfill({status:503,body:JSON.stringify({detail:"untrusted private failure text"}),contentType:"application/json"}),{times:1});
  await uploadButton.click();
  await expect(contributor.locator("p[role=alert]")).toContainText("服务暂时不可用");
  await expect(uploadButton).toBeEnabled();
  let release:()=>void=()=>{};const gate=new Promise<void>(resolve=>{release=resolve;});
  await contributor.route(`**/studies/${study}/photos`,async route=>{const response=await route.fetch();await gate;await route.fulfill({response});},{times:1});
  await uploadButton.click();
  await expect(uploadButton).toBeDisabled();
  await expect(contributor.getByText("肖像已私密保存，正在等待人工审核。",{exact:true})).toHaveCount(0);
  release();
  await expect(contributor.getByText("肖像已私密保存，正在等待人工审核。",{exact:true}).first()).toBeVisible();
  await page.getByRole("button",{name:"Refresh study status",exact:true}).click();
  await page.getByRole("button",{name:"Approve portrait",exact:true}).click();
  await expect(page.getByText("Portrait approved",{exact:false})).toBeVisible();
  for(let i=0;i<3;i++) {
    const context=await browser.newContext({baseURL:origin});
    await login(context.request,`study-fixture-rater-${i}`);
    const view=await (await post(context.request,`${base}/resolve-invite`,{invite_code:code})).json();
    const joined=await (await post(context.request,`${base}/join`,{invite_code:code,role:"rater",consent_id:view.consent.id,consent_sha256:view.consent.sha256,adult_confirmed:true,voluntary:true,understood:true,research_permission:true,fixture_confirmed:true})).json();
    expect((await post(page.request,`${base}/${study}/members/${joined.member_id}/review`,{...command(),approved:true,verification_reference:`fixture-browser-rater-${i}`})).status()).toBe(200);
    const rater=await context.newPage();
    await rater.goto(`/research/studies?study=${study}`);
    await rater.getByRole("button",{name:"Get a portrait to rate",exact:true}).click();
    await expect(rater.getByRole("img",{name:"Private study portrait",exact:true})).toBeVisible();
    await rater.getByRole("radio",{name:`Rating ${5+i}`,exact:true}).check();
    await expect(rater.getByRole("button",{name:"Save rating and continue",exact:true})).toBeEnabled({timeout:10000});
    await rater.getByRole("button",{name:"Save rating and continue",exact:true}).click();
    await expect(rater.getByText("There are no eligible portraits right now. Staff may still be reviewing submissions.",{exact:true})).toBeVisible();
    await context.close();
  }
  await page.getByRole("button",{name:"Refresh study status",exact:true}).click();
  await page.getByRole("button",{name:"Close collection",exact:true}).click();
  await page.getByRole("button",{name:"Create private development export",exact:true}).click();
  await expect(page.getByRole("button",{name:"Download verified private archive",exact:true})).toBeVisible();
  const archive=page.waitForEvent("download");await page.getByRole("button",{name:"Download verified private archive",exact:true}).click();
  expect((await archive).suggestedFilename()).toMatch(/^auvylen-development-/);
  // A screenshot of empty-state consent controls only: hide invitation and private fixture image.
  await contributor.getByRole("button",{name:"English",exact:true}).click();
  contributor.once("dialog",dialog=>dialog.accept());
  await contributor.getByRole("button",{name:"Withdraw and delete my study data",exact:true}).click();
  await expect(contributor.getByText("Participation withdrawn. Your portraits and ratings were removed and exports revoked.",{exact:true})).toBeVisible();
  expect(await contributor.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await expect(contributor.getByRole("button",{name:"Download my consent receipts",exact:true})).toBeEnabled();
  await contributor.evaluate(()=>{if(document.activeElement instanceof HTMLElement) document.activeElement.blur();window.scrollTo({top:0,behavior:"instant"});});
  if(process.env.AUVYLEN_STUDY_VISUAL_DIR) await contributor.screenshot({path:path.join(process.env.AUVYLEN_STUDY_VISUAL_DIR,"study-withdrawal-en-mobile.png"),fullPage:true,animations:"disabled"});
  await contributor.getByRole("button",{name:"中文",exact:true}).click();
  await contributor.evaluate(()=>{if(document.activeElement instanceof HTMLElement) document.activeElement.blur();window.scrollTo({top:0,behavior:"instant"});});
  if(process.env.AUVYLEN_STUDY_VISUAL_DIR) {
    await contributor.screenshot({path:path.join(process.env.AUVYLEN_STUDY_VISUAL_DIR,"study-withdrawal-zh-mobile.png"),fullPage:true,animations:"disabled"});
    await contributor.setViewportSize({width:1440,height:1000});
    await contributor.getByRole("button",{name:"English",exact:true}).click();
    await contributor.evaluate(()=>{if(document.activeElement instanceof HTMLElement) document.activeElement.blur();window.scrollTo({top:0,behavior:"instant"});});
    await contributor.screenshot({path:path.join(process.env.AUVYLEN_STUDY_VISUAL_DIR,"study-withdrawal-en-desktop.png"),fullPage:true,animations:"disabled"});
  }
  expect(errors).toEqual([]);
  await contributorContext.close();
});

test("a new consent version requires fresh checkbox confirmations",async({page,browser})=>{
  test.setTimeout(60000);
  await login(page.request,"owner_god");
  const created=await post(page.request,base,{...command(),title:"Consent version fixture"});
  expect(created.status()).toBe(201);
  const id=(await created.json()).id;
  const terms={text_en:"Authorized generated fixture research, voluntary adults and native 1–7 ratings. No real collection. Research only; no public display or consumer use. Withdrawal removes data and revokes exports.",text_zh:"这是已获授权的生成素材测试研究，不进行真实参与者采集。仅用于自愿成人研究评分，不公开展示或提供消费者评分。参与者可撤回并删除照片与评分，撤销导出。",contact_en:"Fixture contact only",contact_zh:"测试负责人",rights_reference:"generated-fixtures-only"};
  expect((await post(page.request,`${base}/${id}/consent`,{...command(),...terms})).status()).toBe(200);
  const code=(await (await post(page.request,`${base}/${id}/action`,{...command(),action:"rotate_invite",reason:"Generated version fixture"})).json()).value;
  expect((await post(page.request,`${base}/${id}/action`,{...command(),action:"open",reason:"Generated version fixture"})).status()).toBe(200);
  const context=await browser.newContext({baseURL:origin,reducedMotion:"reduce"});
  await login(context.request,"study-fixture-contributor");
  const participant=await context.newPage();
  await participant.goto("/research/studies");
  await participant.getByLabel("Private invitation code",{exact:true}).fill(code);
  await participant.getByRole("button",{name:"Read study invitation",exact:true}).click();
  await expect(participant.getByRole("checkbox")).toHaveCount(4);
  for(const checkbox of await participant.getByRole("checkbox").all()) await checkbox.check();
  await participant.getByRole("button",{name:"Accept this consent version",exact:true}).click();
  await expect(participant.getByRole("button",{name:"Download my consent receipts",exact:true})).toBeVisible();
  expect((await post(page.request,`${base}/${id}/consent`,{...command(),...terms,text_en:terms.text_en+" Version two.",text_zh:terms.text_zh+" 第二版。"})).status()).toBe(200);
  expect((await post(page.request,`${base}/${id}/action`,{...command(),action:"open",reason:"Reviewed fixture version two"})).status()).toBe(200);
  await participant.getByRole("button",{name:"Refresh study status",exact:true}).click();
  await participant.getByText("Read the exact consent version: 2",{exact:true}).click();
  const checkboxes=participant.getByRole("checkbox");
  await expect(checkboxes).toHaveCount(4);
  for(const checkbox of await checkboxes.all()) await expect(checkbox).not.toBeChecked();
  await expect(participant.getByRole("button",{name:"Accept this consent version",exact:true})).toBeDisabled();
  await context.close();
});


test("real browser/proxy native preview transport: private queue, withholding, history and deletion",async({page,browser})=>{
  test.setTimeout(60000);
  // No page.route mocks: the real proxy, auth, upload decoder, storage, queue and
  // result validation run. Only model execution in the isolated test server is a
  // withheld-result fixture; this test is NOT trained-model inference evidence.
  await login(page.request,"owner_god");
  await page.goto("/research/native-preview");
  await expect(page.getByText("TRANSPORT FIXTURE — NO MODEL INFERENCE",{exact:true})).toBeVisible();
  await page.getByLabel("Authorized adult portrait",{exact:true}).setInputFiles({name:"generated-native-transport.png",mimeType:"image/png",buffer:image()});
  await page.getByRole("checkbox").check();
  const saved=page.waitForResponse(r=>r.url().endsWith("/native-preview/jobs")&&r.request().method()==="POST");
  await page.getByRole("button",{name:"Run private native preview",exact:true}).click();
  const response=await saved;expect(response.status()).toBe(202);
  expect(response.headers()["cache-control"]).toBe("private, no-store");
  const id=(await response.json()).id;
  await expect(page.getByText("No score for this image",{exact:true})).toBeVisible({timeout:15000});
  await expect(page.locator(".score-hero")).toHaveCount(0);
  await expect(page.locator(".native-history-list li")).toHaveCount(1);
  await page.getByRole("button",{name:"中文",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Auvylen 原生模型研究预览",exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole("button",{name:"English",exact:true}).click();
  await page.getByRole("button",{name:"Delete this preview now",exact:true}).click();
  await expect(page.getByText("Preview deleted. Its image and result were removed.",{exact:true})).toBeVisible();
  await expect(page.locator(".native-history-list li")).toHaveCount(0);
  expect((await page.request.get(`/api/v1/research/native-preview/jobs/${id}`)).status()).toBe(404);
  const other=await browser.newContext({baseURL:origin});
  await login(other.request,"study-fixture-rater-0");
  expect((await other.request.get("/api/v1/research/native-preview/status")).status()).toBe(403);
  expect((await other.request.get(`/api/v1/research/native-preview/jobs/${id}`)).status()).toBe(403);
  await other.close();
});
