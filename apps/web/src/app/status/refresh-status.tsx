"use client";
import {useI18n} from "@/components/i18n/provider";

import {useTransition} from "react";
import {useRouter} from "next/navigation";

export function RefreshStatus() {
  const {t} = useI18n();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return <button type="button" disabled={pending}
    onClick={() => startTransition(() => router.refresh())}
    className="cursor-pointer underline underline-offset-4 disabled:opacity-50">
    {pending ? t("Checking…") : t("Check again")}
  </button>;
}
