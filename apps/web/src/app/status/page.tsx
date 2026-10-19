import {Text} from "@/components/i18n/provider";
import type {Metadata} from "next";
import {getApiStatus} from "@/lib/api-status";
import {RefreshStatus} from "./refresh-status";
import {getApiUrl} from "@/lib/environment";

export const metadata: Metadata = {title: "System status"};
export const dynamic = "force-dynamic";

export default async function Status() {
  const state = await getApiStatus(getApiUrl());
  const ready = state.readiness?.status === "ready";
  const rows = [
    {name: "Web application", ok: true, label: "Available"},
    {name: "API connection", ok: state.reachable, label: state.reachable ? "Connected" : "Unavailable"},
    {name: "PostgreSQL", ok: state.readiness?.dependencies.database === "ok", label: state.reachable ? state.readiness.dependencies.database : "Unknown"},
    {name: "Redis", ok: state.readiness?.dependencies.redis === "ok", label: state.reachable ? state.readiness.dependencies.redis : "Unknown"},
  ];
  return <section className="max-w-2xl">
    <p className="mb-5 text-xs font-medium uppercase tracking-[0.2em] text-[#537462]"><Text>{"Environment / Status"}</Text></p>
    <h1 className="text-4xl font-medium tracking-tight"><Text>{"System status"}</Text></h1>
    <p className="mt-5 leading-7 text-[#63706a]">{ready ? <Text>{"The API and its dependencies are ready."}</Text> : <Text>{"Some services need attention. Check the local development processes."}</Text>}</p>
    <dl className="mt-9 divide-y divide-black/10 rounded-lg border border-black/10 bg-white/70 px-5 sm:px-7">
      {rows.map(row => <div key={row.name} className="flex items-center justify-between gap-4 py-5 text-sm">
        <dt><Text>{row.name}</Text></dt><dd className="flex items-center gap-2 capitalize text-[#63706a]">
          <span aria-hidden="true" className={`h-2 w-2 rounded-full ${row.ok ? "bg-[#537462]" : "bg-[#a37b43]"}`} /><Text>{row.label}</Text>
        </dd>
      </div>)}
    </dl>
    <div className="mt-6 flex flex-wrap items-center justify-between gap-4 text-xs text-[#68736d]">
      <span><Text>{"Checked on page load ·"}</Text> {new Date().toISOString()}</span>
      <RefreshStatus />
    </div>
    <p className="mt-10 text-sm leading-6 text-[#63706a]"><Text>{"These checks confirm service connectivity. They do not validate a production model or provide facial analysis."}</Text></p>
  </section>;
}
