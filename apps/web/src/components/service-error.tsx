import {Text} from "@/components/i18n/provider";
import Link from "next/link";

export function ServiceError() {
  return <div role="alert" className="rounded-lg border border-black/10 bg-white p-6">
    <h1 className="text-2xl font-medium"><Text>{"Service unavailable"}</Text></h1>
    <p className="mt-4 leading-7 text-[#63706a]"><Text>{"Start the API and database, then apply the latest migrations before trying again."}</Text></p>
    <Link href="/status" className="mt-5 inline-block underline underline-offset-4"><Text>{"View system status"}</Text></Link>
  </div>;
}
