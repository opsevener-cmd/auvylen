"use client";

import {useTransition} from "react";
import {useRouter} from "next/navigation";

export function RefreshStatus() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return <button type="button" disabled={pending}
    onClick={() => startTransition(() => router.refresh())}
    className="cursor-pointer underline underline-offset-4 disabled:opacity-50">
    {pending ? "Checking…" : "Check again"}
  </button>;
}
