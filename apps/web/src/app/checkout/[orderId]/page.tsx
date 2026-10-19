import {Text} from "@/components/i18n/provider";
import Link from "next/link";
import {SubmitButton} from "@/components/submit-button";
import {ServiceError} from "@/components/service-error";
import {apiRequest, formatMoney, orderSchema, unavailable} from "@/lib/commercial-api";
import {simulatePayment} from "../../actions";

export const dynamic = "force-dynamic";

export default async function Checkout({params, searchParams}: {
  params: Promise<{orderId: string}>; searchParams: Promise<{error?: string}>;
}) {
  const {orderId} = await params;
  const query = await searchParams;
  const order = await apiRequest(`/orders/${encodeURIComponent(orderId)}`, orderSchema).catch(unavailable);
  if (!order) return <ServiceError />;
  const rows = [["Order reference", order.public_order_id], ["Product", order.product.name],
    ["Amount", formatMoney(order.amount, order.currency)], ["Payment status", order.paid_at ? "Payment confirmed" : "Awaiting payment"],
    ["Order status", order.status], ["Payment method", "Mock Payment"]];
  return <section className="max-w-2xl">
    <p className="mb-5 text-xs uppercase tracking-[0.2em] text-[#537462]"><Text>{"Development / Checkout"}</Text></p>
    <h1 className="text-4xl font-medium tracking-tight"><Text>{"Checkout"}</Text></h1>
    <dl className="mt-8 divide-y divide-black/10 rounded-lg border border-black/10 bg-white/70 px-5">
      {rows.map(([label, value]) => <div key={label} className="flex flex-wrap justify-between gap-2 py-4 text-sm"><dt><Text>{label}</Text></dt><dd className="break-all text-[#63706a]"><Text>{value}</Text></dd></div>)}
    </dl>
    <p className="mt-5 text-sm leading-6 text-[#63706a]"><Text>{"Mock Payment is a server-side simulation. No money is charged and no real payment provider is connected."}</Text></p>
    {order.status === "PENDING_PAYMENT" && <form action={simulatePayment.bind(null, order.public_order_id)}><SubmitButton><Text>{"Simulate successful payment"}</Text></SubmitButton></form>}
    {order.analysis_id && <Link href={`/result/${order.analysis_id}`} className="mt-6 inline-block underline underline-offset-4"><Text>{"View analysis result"}</Text></Link>}
    {order.status === "PAID" && <p className="mt-5 text-sm"><Text>{"Payment is recorded. Fulfillment is pending; an operator can resume it safely."}</Text></p>}
    {query.error && <p role="alert" className="mt-5 text-sm text-[#8c513c]"><Text>{"The request failed. Payment may already be recorded; check this order before trying again."}</Text></p>}
  </section>;
}
