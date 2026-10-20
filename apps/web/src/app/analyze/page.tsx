import {Text} from "@/components/i18n/provider";
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
  if (isPublicPilot() || process.env.MOCK_CHECKOUT_ENABLED === "false") return <AccountAnalyze><section><h1 className="text-3xl"><Text>{"Auvylen Analysis"}</Text></h1><p className="mt-5"><Text>{"Sign in to use Credits for a Synthetic / Development Analysis."}</Text></p><Link className="mt-5 inline-block underline" href="/login"><Text>{"Sign in"}</Text></Link><p className="mt-4"><Link href="/register" className="underline"><Text>{"Create account"}</Text></Link></p></section></AccountAnalyze>;
  const products = await apiRequest("/products", z.array(productSchema)).catch(unavailable);
  const product = products?.find(p => p.slug === "aevyra-test-analysis" && p.active);
  if (!product) return <AccountAnalyze><ServiceError /></AccountAnalyze>;
  return <AccountAnalyze><section className="max-w-2xl">
    <p className="mb-5 text-xs uppercase tracking-[0.2em] text-[#537462]"><Text>{"Development / Test product"}</Text></p>
    <h1 className="text-4xl font-medium tracking-tight"><Text>{product.name}</Text></h1>
    <p className="mt-5 leading-7 text-[#63706a]"><Text>{product.description}</Text></p>
    <div className="mt-8 rounded-lg border border-black/10 bg-white/70 p-6">
      <p className="text-3xl font-medium">{formatMoney(product.price_amount, product.currency)}</p>
      <p className="mt-2 text-sm text-[#63706a]"><Text>{"Development price · Mock payment only · No real charge"}</Text></p>
      <form action={createOrder}>
        <input type="hidden" name="product_slug" value={product.slug} />
        <SubmitButton><Text>{"Create order"}</Text></SubmitButton>
      </form>
    </div>
    {params.error && <p role="alert" className="mt-5 text-sm text-[#8c513c]"><Text>{"Order creation failed. Check system status and try again."}</Text></p>}
    <p className="mt-8 text-sm leading-6 text-[#63706a]"><Text>{"No image is requested. This flow produces a synthetic fixture score with no facial aesthetic meaning."}</Text></p>
  </section></AccountAnalyze>;
}
