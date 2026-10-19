import {Text} from "@/components/i18n/provider";
import Link from "next/link";
import {cookies} from "next/headers";
import {OwnerDashboard} from "@/components/owner-dashboard";
import {getApiUrl} from "@/lib/environment";
import {sessionSchema} from "@/lib/account-api";

export const dynamic = "force-dynamic";
export default async function OwnerPage() {
  const token = (await cookies()).get("auvylen_session")?.value;
  if (!token || !/^[A-Za-z0-9_-]{1,100}$/.test(token)) return <p><Text>{"Owner sign-in required."}</Text> <Link href="/login" className="underline"><Text>{"Sign in"}</Text></Link></p>;
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
  if (unavailable) return <p><Text>{"Account verification is temporarily unavailable. Reload to retry."}</Text></p>;
  if (allowed) return <OwnerDashboard/>;
  return <p><Text>{"Owner access required."}</Text> <Link href="/account" className="underline"><Text>{"Return to account"}</Text></Link></p>;
}
