import {z} from "zod";
import {AccountAnalyze} from "@/components/account-pages";
import {SubmitButton} from "@/components/submit-button";
import {ServiceError} from "@/components/service-error";
import {apiRequest, formatMoney, productSchema, unavailable} from "@/lib/commercial-api";
import {createOrder} from "../actions";
import {isPublicPilot} from "@/lib/environment";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function Analyze({searchParams}: {searchParams: Promise<{error?: string}>}) {
  const params = await searchParams;
  if (isPublicPilot() || process.env.MOCK_CHECKOUT_ENABLED === "false") return <AccountAnalyze><section><h1 className="text-3xl">Auvylen Analysis</h1><p className="mt-5">Sign in to use Credits for a Synthetic / Development Analysis.</p><Link className="mt-5 inline-block underline" href="/login">Sign in</Link><p className="mt-4"><Link href="/register" className="underline">Create account</Link></p></section></AccountAnalyze>;
  const products = await apiRequest("/products", z.array(productSchema)).catch(unavailable);
  const product = products?.find(p => p.slug === "aevyra-test-analysis" && p.active);
  if (!product) return <AccountAnalyze><ServiceError /></AccountAnalyze>;
  return <AccountAnalyze><section className="max-w-2xl">
    <p className="mb-5 text-xs uppercase tracking-[0.2em] text-[#537462]">Development / Test product</p>
    <h1 className="text-4xl font-medium tracking-tight">{product.name}</h1>
    <p className="mt-5 leading-7 text-[#63706a]">{product.description}</p>
    <div className="mt-8 rounded-lg border border-black/10 bg-white/70 p-6">
      <p className="text-3xl font-medium">{formatMoney(product.price_amount, product.currency)}</p>
      <p className="mt-2 text-sm text-[#63706a]">Development price · Mock payment only · No real charge</p>
      <form action={createOrder}>
        <input type="hidden" name="product_slug" value={product.slug} />
        <SubmitButton>Create order</SubmitButton>
      </form>
    </div>
    {params.error && <p role="alert" className="mt-5 text-sm text-[#8c513c]">Order creation failed. Check system status and try again.</p>}
    <p className="mt-8 text-sm leading-6 text-[#63706a]">No image is requested. This flow produces a synthetic fixture score with no facial aesthetic meaning.</p>
  </section></AccountAnalyze>;
}
