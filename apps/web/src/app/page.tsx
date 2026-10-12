import Link from "next/link";
import {isPublicPilot} from "@/lib/environment";

export default function Home() {
  const production = process.env.APP_ENV === "production";
  const pilot = isPublicPilot();
  const research = process.env.MOCK_CHECKOUT_ENABLED === "false";
  return <section className="max-w-2xl">
    <p className="mb-6 text-xs font-medium uppercase tracking-[0.2em] text-[#537462]">Phase 2 · {production ? "Deployment foundation" : "Development"}</p>
    <h1 className="text-4xl font-medium tracking-tight sm:text-6xl">Auvylen Analysis.</h1>
    <p className="mt-7 max-w-xl text-base leading-7 text-[#63706a] sm:text-lg">
      {research ? "Use the authorized research workspace for asynchronous synthetic testing without spending Credits." : pilot ? "Sign in, redeem the code you received after purchase, and use Credits to test synthetic analysis." : production ? "The Auvylen platform is being prepared. Commercial analysis and checkout are currently unavailable." : "Explore the development transaction flow with a mock payment and a clearly synthetic result."}
    </p>
    <Link href={research ? "/research" : production ? "/status" : "/analyze"} className="mt-10 inline-flex items-center gap-5 rounded-md bg-[#253e34] px-5 py-3 text-sm text-white hover:bg-[#355546]">
      {research ? "Research workspace" : production ? "System status" : "Start Analysis"} <span aria-hidden="true">↗</span>
    </Link>
    <div className="mt-16 border-t border-black/10 pt-6 text-sm leading-6 text-[#63706a]">
      {production ? "Commercial analysis is not available in this deployment." : "Development environment. No facial analysis is available. The only scoring engine produces synthetic test data."}
    </div>
  </section>;
}

export const dynamic = "force-dynamic";
