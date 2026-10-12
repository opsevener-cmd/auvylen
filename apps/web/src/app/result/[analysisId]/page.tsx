import {ServiceError} from "@/components/service-error";
import {cookies} from "next/headers";
import {getApiUrl} from "@/lib/environment";
import {z} from "zod";
import {analysisSchema, apiRequest, resultSchema, unavailable} from "@/lib/commercial-api";

export const dynamic = "force-dynamic";

export default async function Result({params, searchParams}: {params: Promise<{analysisId: string}>, searchParams: Promise<{funding?: string}>}) {
  const {analysisId} = await params;
  const creditFunded = (await searchParams).funding === "credits";
  const path = `/${creditFunded ? "credit-analyses" : "analyses"}/${encodeURIComponent(analysisId)}`;
  async function load<T>(url: string, schema: z.ZodType<T>): Promise<T> {
    if (!creditFunded) return apiRequest(url, schema);
    const cookieStore = await cookies();
    const token = cookieStore.get("auvylen_session")?.value;
    const response = await fetch(new URL(`/api/v1${url}`, getApiUrl()), {
      cache: "no-store", headers: token ? {Cookie: `auvylen_session=${token}`} : {},
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) throw new Error("Analysis unavailable");
    return schema.parse(await response.json());
  }
  const analysis = await load(path, analysisSchema).catch(unavailable);
  if (!analysis) return <ServiceError />;
  const result = analysis.status === "COMPLETED" ? await load(`${path}/result`, resultSchema).catch(unavailable) : null;
  return <section className="max-w-2xl">
    <p className="mb-5 text-xs uppercase tracking-[0.2em] text-[#537462]">Development / Synthetic Result</p>
    <h1 className="text-4xl font-medium tracking-tight">Auvylen Analysis</h1>
    <p className="mt-5 leading-7 text-[#63706a]">Synthetic test output. This score does not measure a face and is not a real AI assessment.</p>
    <div className="mt-8 rounded-lg border border-black/10 bg-white/70 p-6">
      <p className="text-sm text-[#63706a]">Analysis status: {analysis.status}</p>
      {result ? <>
        <p className="mt-5 text-5xl font-medium">{result.display_score.toFixed(2)} <span className="text-lg text-[#63706a]">/ 10</span></p>
        <dl className="mt-7 space-y-3 text-sm">
          <div className="flex justify-between"><dt>Raw score</dt><dd>{result.raw_score.toFixed(6)}</dd></div>
          <div className="flex justify-between"><dt>Engine</dt><dd>{result.engine_slug}</dd></div>
          <div className="flex justify-between"><dt>Version</dt><dd>{result.engine_version}</dd></div>
          <div className="flex justify-between"><dt>Synthetic</dt><dd>Yes</dd></div>
        </dl>
      </> : <p className="mt-5 leading-7 text-[#63706a]">{analysis.failure_reason ?? "Result is not yet available. Reload to check again."}</p>}
    </div>
  </section>;
}
