import Link from "next/link";
import {cookies} from "next/headers";
import {OwnerDashboard} from "@/components/owner-dashboard";
import {getApiUrl} from "@/lib/environment";
import {sessionSchema} from "@/lib/account-api";

export const dynamic = "force-dynamic";
export default async function OwnerPage() {
  const token = (await cookies()).get("auvylen_session")?.value;
  if (!token || !/^[A-Za-z0-9_-]{1,100}$/.test(token)) return <p>Owner sign-in required. <Link href="/login" className="underline">Sign in</Link></p>;
  let allowed = false;
  let unavailable = false;
  try {
    const response = await fetch(new URL("/api/v1/auth/me", getApiUrl()), {
      headers: {cookie: `auvylen_session=${token}`}, cache: "no-store", signal: AbortSignal.timeout(5000),
    });
    allowed = response.ok && sessionSchema.parse(await response.json()).user.role === "owner";
  } catch {
    unavailable = true;
  }
  if (unavailable) return <p>Account verification is temporarily unavailable. Reload to retry.</p>;
  if (allowed) return <OwnerDashboard/>;
  return <p>Owner access required. <Link href="/account" className="underline">Return to account</Link></p>;
}
