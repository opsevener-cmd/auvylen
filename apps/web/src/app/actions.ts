"use server";

import {redirect} from "next/navigation";
import {apiRequest, orderSchema, paymentSchema} from "@/lib/commercial-api";
import {logFailure} from "@/lib/logging";

export async function createOrder(formData: FormData) {
  const slug = formData.get("product_slug");
  if (typeof slug !== "string") redirect("/analyze?error=1");
  let reference: string | undefined;
  try {
    const order = await apiRequest("/orders", orderSchema, {product_slug: slug});
    reference = order.public_order_id;
    // Establish the pending attempt before checkout; repeated submissions reuse it.
    await apiRequest(`/orders/${encodeURIComponent(reference)}/payments`, paymentSchema, {});
  } catch (error) {
    logFailure("create_order_failed", error);
    redirect(reference ? `/checkout/${encodeURIComponent(reference)}?error=1` : "/analyze?error=1");
  }
  redirect(`/checkout/${encodeURIComponent(reference)}`);
}

export async function simulatePayment(orderId: string) {
  let destination: string;
  try {
    const path = `/orders/${encodeURIComponent(orderId)}/payments`;
    const payment = await apiRequest(path, paymentSchema, {});
    const order = await apiRequest(`/dev/payments/${payment.payment_id}/simulate-success`, orderSchema, {});
    destination = order.analysis_id ? `/result/${order.analysis_id}` : `/checkout/${encodeURIComponent(orderId)}`;
  } catch (error) {
    logFailure("mock_payment_failed", error);
    redirect(`/checkout/${encodeURIComponent(orderId)}?error=1`);
  }
  redirect(destination);
}
