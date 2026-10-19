"use client";
import {useI18n} from "@/components/i18n/provider";
import {useFormStatus} from "react-dom";

export function SubmitButton({children}: {children: React.ReactNode}) {
  const {t} = useI18n();
  const {pending} = useFormStatus();
  return <button disabled={pending} className="mt-8 w-full cursor-pointer rounded-md bg-[#253e34] px-5 py-3 text-sm text-white hover:bg-[#355546] disabled:cursor-wait disabled:opacity-60 sm:w-auto">
    {pending ? t("Processing…") : children}
  </button>;
}
