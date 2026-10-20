"use client";
import {useI18n} from "@/components/i18n/provider";

import Link from "next/link";
import {useEffect, useState} from "react";
import type {AdminPage, AdminValue, OwnerOverview} from "@auvylen/contracts";
import {AccountError, accountRequest, sessionSchema} from "@/lib/account-api";
import {adminPageSchema, adminResultSchema, ownerOverviewSchema, ownerText as text} from "@/lib/owner-api";

const input = "mt-1 w-full rounded-lg border border-black/20 bg-white px-3 py-2";
const button = "rounded-lg bg-[#253e34] px-4 py-2 text-sm text-white disabled:opacity-40";
const secondary = "rounded-lg border border-black/20 px-3 py-2 text-sm disabled:opacity-40";
const panel = "rounded-2xl border border-black/10 bg-white p-5 sm:p-6";
type Row = Record<string, AdminValue>;
type Action = {path: string; title: string; titleValues?: Record<string, string>; fields?: "credits" | "batch"; values?: object};
function display(value: AdminValue | undefined): string {return value === null || value === undefined ? "Unavailable" : typeof value === "object" ? JSON.stringify(value) : String(value);}
function label(key: string) {return key.replaceAll("_", " ");}
function measured(key: string, value: AdminValue) {
  if (typeof value !== "number") return display(value);
  if (key.endsWith("_bytes")) {
    const unit = value >= 1024 ** 3 ? "GiB" : "MiB";
    return `${(value / (unit === "GiB" ? 1024 ** 3 : 1024 ** 2)).toFixed(1)} ${unit}`;
  }
  return new Intl.NumberFormat("en", {maximumFractionDigits: 2}).format(value);
}
function errorMessage(error: unknown) {
  if (error instanceof AccountError && (error.status === 403 || error.status === 409)) return text.mutationErrors[error.status];
  return error instanceof Error ? error.message : "Request failed. Review records before retrying.";
}
function Summary({values}: {values: Record<string, AdminValue>}) {
  const {t} = useI18n();
  return <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(values).map(([key, value]) => <div key={key} className="min-w-0"><dt className="text-xs capitalize text-[#68736d]">{t(label(key))}</dt><dd className="mt-1 break-words text-lg font-medium">{t(measured(key, value))}</dd></div>)}</dl>;
}
function Table({rows, columns, actions}: {rows: Row[]; columns: string[]; actions?: (row: Row) => React.ReactNode}) {
  const {t} = useI18n();
  return <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b border-black/10">{columns.map(c => <th key={c} scope="col" className="p-3 font-medium capitalize">{t(label(c))}</th>)}{actions && <th scope="col" className="p-3">{t("Actions")}</th>}</tr></thead><tbody>{rows.map((row, i) => <tr key={String(row.id ?? row.public_user_id ?? row.public_batch_id ?? i)} className="border-b border-black/5">{columns.map(c => <td key={c} className="max-w-sm break-words p-3 align-top">{["status", "role", "kind", "available", "active", "disabled", "research_enabled", "reason", "display_name", "transaction_type"].includes(c) ? t(display(row[c])) : display(row[c])}</td>)}{actions && <td className="p-3"><div className="flex flex-wrap gap-2">{actions(row)}</div></td>}</tr>)}</tbody></table>{!rows.length && <p className="p-4 text-sm">{t("No records found.")}</p>}</div>;
}

function Mutation({action, done, close}: {action: Action; done: (data: Row) => void; close: () => void}) {
  const {t} = useI18n();
  const [key, setKey] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<object | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <section className={panel + " border-[#537462]"} aria-label={t("Confirm administrative change")}>
    <h2 className="text-xl font-medium">{t(action.title, action.titleValues)}</h2>
    <p className="mt-2 text-sm">{t("Review this change before confirming. It will be recorded in the audit trail.")}</p>
    <form className="mt-4 grid gap-4 sm:grid-cols-2" onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError("");
      const values = new FormData(event.currentTarget);
      const requestKey = key ?? crypto.randomUUID(); setKey(requestKey);
      const body = submitted ?? {idempotency_key: requestKey, reason: String(values.get("reason")), ...action.values,
        ...(action.fields === "credits" ? {amount: Number(values.get("amount"))} : {}),
        ...(action.fields === "batch" ? {name: String(values.get("name")), quantity: Number(values.get("quantity")), credits: Number(values.get("credits")), expires_days: Number(values.get("expires_days"))} : {})};
      setSubmitted(body);
      try {const result = await accountRequest(action.path, adminResultSchema, body); done(result.data);}
      catch (error) {setError(errorMessage(error));} finally {setBusy(false);}
    }}>
      <fieldset disabled={busy || submitted !== null} className="contents">
        {action.fields === "credits" && <label>{t("Promotional Credits")}<input className={input} name="amount" type="number" min={1} max={1000000} required/></label>}
        {action.fields === "batch" && <><label>{t("Batch name")}<input className={input} name="name" pattern="[A-Za-z0-9][A-Za-z0-9 _.-]*" maxLength={100} required/></label><label>{t("Number of codes")}<input className={input} name="quantity" type="number" min={1} max={100} defaultValue={5} required/></label><label>{t("Credits per code")}<input className={input} name="credits" type="number" min={1} max={1000000} defaultValue={10} required/></label><label>{t("Expires in days")}<input className={input} name="expires_days" type="number" min={1} max={365} defaultValue={30} required/></label></>}
        <label className="sm:col-span-2">{t(text.reason)}<input className={input} name="reason" minLength={3} maxLength={200} required/></label>
      </fieldset>
      <div className="flex gap-3 sm:col-span-2"><button disabled={busy} className={button}>{submitted ? t("Retry same request") : t("Confirm change")}</button><button type="button" disabled={busy} onClick={close} className={secondary}>{t("Close")}</button></div>
    </form>{error && <p role="alert" className="mt-4">{t(error)}</p>}
  </section>;
}

export function OwnerDashboard() {
  const {t} = useI18n();
  const [tab, setTab] = useState(0);
  const [overview, setOverview] = useState<OwnerOverview | null>(null);
  const [records, setRecords] = useState<AdminPage | null>(null);
  const [page, setPage] = useState(1);
  const [revision, refresh] = useState(0);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [action, setAction] = useState<Action | null>(null);
  const [codes, setCodes] = useState<Row | null>(null);
  const [ledger, setLedger] = useState<Row | null>(null);
  const [ledgerTarget, setLedgerTarget] = useState<string | null>(null);
  const [ledgerPage, setLedgerPage] = useState(1);
  const [reauthBusy, setReauthBusy] = useState(false);
  useEffect(() => {
    let active = true;
    const path = ["", "/users", "/batches", "/jobs", "/audit"][tab];
    const params = new URLSearchParams({page: String(page), page_size: "20"});
    if (tab === 1) {params.set("search", search); params.set("status", filter);}
    if (tab === 3) params.set("status", filter);
    const promise = tab === 0
      ? accountRequest("/owner/overview", ownerOverviewSchema).then(v => {if (active) setOverview(v);})
      : accountRequest(`/owner${path}?${params}`, adminPageSchema).then(v => {if (active) setRecords(v);});
    promise.catch(e => {if (active) setError(errorMessage(e));}).finally(() => {if (active) setLoading(false);});
    return () => {active = false;};
  }, [tab, page, search, filter, revision]);
  function reload() {setLoading(true); setError(""); refresh(n => n + 1);}
  async function showLedger(target: string, requestedPage = 1) {
    try {
      const result = await accountRequest(`/owner/users/${target}/credits?page=${requestedPage}`, adminResultSchema);
      setLedger(result.data); setLedgerTarget(target); setLedgerPage(requestedPage);
    } catch (e) {setError(errorMessage(e));}
  }
  return <div className="space-y-6">
    <header className="rounded-2xl bg-[#253e34] p-6 text-white sm:p-8">
      <p className="text-xs tracking-[0.16em] text-[#c1d8c9]">{t(text.badge)}</p><h1 className="mt-3 text-3xl font-medium sm:text-4xl">{t(text.title)}</h1>
      <p className="mt-3 text-[#d4dfd8]">{t(text.subtitle)}</p><p className="mt-5 text-sm">{t(text.entitlement)}</p>
      <div className="mt-5 flex gap-5 text-sm"><Link className="underline" href="/research/preferences">{t("Personal research")}</Link><Link className="underline" href="/account">{t("My account")}</Link></div>
    </header>
    <details className={panel}><summary className="cursor-pointer font-medium">{t("Confirm fresh authentication")}</summary><p className="mt-3 text-sm">{t(text.fresh)}</p>
      <form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={async event => {
        event.preventDefault(); const form = event.currentTarget; const password = String(new FormData(form).get("password")); setReauthBusy(true);
        try {await accountRequest("/auth/login", sessionSchema, {login_identifier: "owner_god", password}); setNotice("Fresh sign-in confirmed."); setError("");}
        catch (e) {setError(errorMessage(e));} finally {form.reset(); setReauthBusy(false);}
      }}><label>{t("Current password")}<input className={input} type="password" name="password" autoComplete="current-password" required maxLength={128}/></label><button className={button} disabled={reauthBusy}>{t("Confirm password")}</button></form>
    </details>
    <nav aria-label={t("Owner sections")} className="flex flex-wrap gap-2">{text.tabs.map((name, i) => <button key={name} aria-current={tab === i ? "page" : undefined} className={tab === i ? button : secondary} onClick={() => {setTab(i); setPage(1); setFilter("all"); setSearch(""); setRecords(null); setLedger(null); setAction(null); setError(""); setLoading(true);}}>{t(name)}</button>)}<button className={secondary} onClick={reload}>{t("Refresh")}</button></nav>
    {notice && <p role="status" className="rounded-lg bg-[#e4ede6] p-4">{t(notice)}</p>}{error && <p role="alert" className="rounded-lg border border-red-200 p-4">{t(error)}</p>}
    {action && <Mutation key={action.path + action.title} action={action} close={() => setAction(null)} done={data => {if (data.codes) setCodes(data); setAction(null); setNotice("Change saved and audited."); reload(); if (ledgerTarget) void showLedger(ledgerTarget);}}/>}
    {codes && <section className={panel} aria-label={t("One-time redemption export")}><h2 className="text-xl">{t("Codes ready")}</h2><p className="mt-3">{t(text.secretNotice)}</p><p className="mt-3 text-sm">{display(codes.public_batch_id)} · {display(codes.quantity)} {t("codes")}</p><div className="mt-4 flex gap-3"><button className={button} onClick={() => {const blob = new Blob([JSON.stringify(codes, null, 2)], {type: "application/json"}); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = `${String(codes.public_batch_id)}.json`; a.click(); URL.revokeObjectURL(url);}}>{t("Download codes once")}</button><button className={secondary} onClick={() => setCodes(null)}>{t("Clear codes from this page")}</button></div></section>}
    {loading && <p role="status">{t("Loading current records…")}</p>}
    {!loading && tab === 0 && overview && <>
      <section className={panel}><h2 className="mb-5 text-xl font-medium">{t("Platform overview")}</h2><Summary values={overview.counts}/></section>
      <div className="grid gap-6 sm:grid-cols-2"><section className={panel}><h2 className="mb-5 text-xl font-medium">{t("Credits activity")}</h2><Summary values={overview.credits}/></section><section className={panel}><h2 className="mb-5 text-xl font-medium">{t("Research jobs")}</h2><Summary values={overview.jobs}/></section></div>
      <section className={panel}><h2 className="mb-5 text-xl font-medium">{t("Service availability")}</h2><p className="mb-4 text-sm">{t(overview.environment)} {t("· Research")} {overview.research_enabled ? t("enabled") : t("disabled")}{t(". Provider readiness does not bypass licensing or execution policy.")}</p><Table rows={overview.providers} columns={["display_name", "available", "reason"]}/><Table rows={overview.extractors} columns={["id", "available", "reason"]}/></section>
      <section className={panel}><h2 className="mb-5 text-xl font-medium">{t("Model usage")}</h2><Table rows={overview.usage} columns={["provider", "kind", "status", "jobs"]}/></section>
      <section className={panel}><h2 className="mb-5 text-xl font-medium">{t("System observations")}</h2><p className="mb-4 text-sm">{t("Filesystem capacity may be shared. API peak memory and host load are observations, not total workspace usage. Worker health uses a recent heartbeat or an active lease.")}</p><Summary values={overview.health}/></section>
      <section className={panel}><h2 className="mb-5 text-xl font-medium">{t("Owner resource limits")}</h2><Summary values={overview.quotas}/><p className="mt-4 text-sm">{t("Consent, retention, decoding limits, throttling and personal data isolation remain enforced.")}</p></section>
    </>}
    {tab === 1 && <form className="flex flex-wrap items-end gap-3" onSubmit={event => {event.preventDefault(); setSearch(String(new FormData(event.currentTarget).get("search"))); setPage(1); setLoading(true); refresh(n => n + 1);}}><label>{t("Search users")}<input name="search" className={input} maxLength={120}/></label><label>{t("Account status")}<select className={input} value={filter} onChange={e => {setFilter(e.target.value); setPage(1); setLoading(true);}}>{["all", "active", "disabled"].map(v => <option key={v} value={v}>{t(v)}</option>)}</select></label><button className={button}>{t("Search")}</button></form>}
    {tab === 2 && <button className={button} onClick={() => setAction({path: "/owner/batches", title: "Create redemption batch", fields: "batch"})}>{t("Create batch")}</button>}
    {tab === 3 && <label className="block max-w-xs">{t("Job status")}<select className={input} value={filter} onChange={e => {setFilter(e.target.value); setPage(1); setLoading(true);}}>{["all", "QUEUED", "RUNNING", "COMPLETED", "FAILED"].map(v => <option key={v} value={v}>{t(v)}</option>)}</select></label>}
    {!loading && tab > 0 && records && <section className={panel}>
      <Table rows={records.items} columns={tab === 1 ? ["login_identifier", "role", "disabled", "research_enabled", "balance"] : tab === 2 ? ["name", "public_batch_id", "active", "quantity", "redeemed", "credits_per_code", "expires_at"] : tab === 3 ? ["id", "provider", "kind", "status", "progress", "attempts", "created_at"] : ["created_at", "actor_id", "action", "target", "outcome", "details"]} actions={tab === 1 ? row => <>
        <button className={secondary} onClick={() => void showLedger(String(row.public_user_id))}>{t("View ledger")}</button>
        {row.role === "user" && <><button className={secondary} onClick={() => setAction({path: `/owner/users/${row.public_user_id}/status`, title: row.disabled ? "Restore account {name}" : "Disable account {name}", titleValues: {name: String(row.login_identifier)}, values: {disabled: !row.disabled}})}>{row.disabled ? t("Restore") : t("Disable")}</button><button className={secondary} onClick={() => setAction({path: `/owner/users/${row.public_user_id}/research`, title: row.research_enabled ? "Revoke research for {name}" : "Grant research for {name}", titleValues: {name: String(row.login_identifier)}, values: {enabled: !row.research_enabled}})}>{row.research_enabled ? t("Revoke research") : t("Grant research")}</button><button className={secondary} onClick={() => setAction({path: `/owner/users/${row.public_user_id}/credits`, title: "Issue promotional Credits to {name}", titleValues: {name: String(row.login_identifier)}, fields: "credits"})}>{t("Issue Credits")}</button></>}
      </> : tab === 2 ? row => row.active ? <button className={secondary} onClick={() => setAction({path: `/owner/batches/${row.public_batch_id}/disable`, title: "Disable batch {name}", titleValues: {name: String(row.name)}})}>{t("Disable batch")}</button> : null : undefined}/>
      <div className="mt-5 flex items-center gap-4"><button className={secondary} disabled={page <= 1} onClick={() => {setPage(p => p - 1); setLoading(true);}}>{t("Previous")}</button><span className="text-sm">{t("Page")} {page} · {records.total} {t("records")}</span><button className={secondary} disabled={page * records.page_size >= records.total} onClick={() => {setPage(p => p + 1); setLoading(true);}}>{t("Next")}</button></div>
    </section>}
    {tab === 1 && ledger && <section className={panel} aria-label={t("User Credits ledger")}><h2 className="mb-5 text-xl">{t("Credits ledger")}</h2><Summary values={{cached_balance: ledger.cached_balance, ledger_balance: ledger.ledger_balance, reconciled: ledger.reconciled}}/><Table rows={ledger.entries as Row[]} columns={["created_at", "transaction_type", "amount", "balance_after", "reference_type", "reference_id"]}/><div className="mt-4 flex gap-3"><button className={secondary} disabled={ledgerPage <= 1} onClick={() => void showLedger(ledgerTarget!, ledgerPage - 1)}>{t("Previous entries")}</button><button className={secondary} disabled={ledgerPage * Number(ledger.page_size) >= Number(ledger.total)} onClick={() => void showLedger(ledgerTarget!, ledgerPage + 1)}>{t("Next entries")}</button><button className={secondary} onClick={() => setLedger(null)}>{t("Close ledger")}</button></div></section>}
  </div>;
}
