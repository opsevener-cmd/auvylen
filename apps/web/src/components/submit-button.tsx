"use client";
import {useFormStatus} from "react-dom";

export function SubmitButton({children}: {children: React.ReactNode}) {
  const {pending} = useFormStatus();
  return <button disabled={pending} className="mt-8 w-full cursor-pointer rounded-md bg-[#253e34] px-5 py-3 text-sm text-white hover:bg-[#355546] disabled:cursor-wait disabled:opacity-60 sm:w-auto">
    {pending ? "Processing…" : children}
  </button>;
}
