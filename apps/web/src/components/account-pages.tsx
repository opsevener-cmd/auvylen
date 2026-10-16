"use client";

import Link from "next/link";
import {useEffect, useState} from "react";
import {useRouter} from "next/navigation";
import {z} from "zod";
import type {Account, CreditProduct} from "@auvylen/contracts";
import {accountRequest, accountSchema, creditProductsSchema, redemptionSchema, sessionSchema} from "@/lib/account-api";
import {analysisSchema} from "@/lib/api-schemas";

const inputClass = "mt-2 w-full rounded-md border border-black/20 bg-white p-3";
const buttonClass = "mt-6 rounded-md bg-[#253e34] px-5 py-3 text-white disabled:opacity-50";

function message(error: unknown) {return error instanceof Error ? error.message : "Request failed.";}

export function AuthPage({mode}: {mode: "register" | "login"}) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return <section className="max-w-md">
    <h1 className="text-3xl font-medium">{mode === "register" ? "Create account" : "Sign in"}</h1>
    <form className="mt-8 space-y-5" onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError("");
      const form = new FormData(event.currentTarget);
      try {
        await accountRequest(`/auth/${mode}`, sessionSchema, {
          login_identifier: String(form.get("identifier")), password: String(form.get("password")),
        });
        router.push("/account"); router.refresh();
      } catch (error) {setError(message(error));} finally {setBusy(false);}
    }}>
      <label className="block">Username or email-like identifier<input name="identifier" required minLength={3} maxLength={120} autoComplete="username" className={inputClass}/></label>
      <label className="block">Password<input name="password" type="password" required minLength={12} maxLength={128} autoComplete={mode === "register" ? "new-password" : "current-password"} className={inputClass}/></label>
      <button disabled={busy} className={buttonClass}>{mode === "register" ? "Create account" : "Sign in"}</button>
    </form>
    {error && <p role="alert" className="mt-5">{error}</p>}
    <p className="mt-6 text-sm">Use 12–128 characters. Pilot accounts have no email verification or self-service password recovery. Keep your credentials safe.</p>
    <Link className="mt-6 inline-block underline" href={mode === "register" ? "/login" : "/register"}>{mode === "register" ? "Already have an account? Sign in" : "Create account"}</Link>
  </section>;
}

function useAccount() {
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let cancelled = false;
    accountRequest("/account", accountSchema).then(value => {
      if (!cancelled) setAccount(value);
    }).catch(error => {if (!cancelled) setError(message(error));}).finally(() => {
      if (!cancelled) setLoaded(true);
    });
    return () => {cancelled = true;};
  }, []);
  return {account, setAccount, error, loaded};
}

export function AccountPage({historyOnly = false}: {historyOnly?: boolean}) {
  const {account, error, loaded} = useAccount();
  const router = useRouter();
  const [logoutError, setLogoutError] = useState("");
  if (!loaded) return <p>Loading account…</p>;
  if (!account) return <p>{error} <Link href="/login" className="underline">Sign in</Link></p>;
  return <section className="max-w-2xl">
    <h1 className="text-3xl font-medium">{historyOnly ? "Analysis history" : "Your account"}</h1>
    {!historyOnly && <>
      <p className="mt-5">{account.user.login_identifier}{account.user.role === "owner" ? " · OWNER" : ""}</p>
      <p className="mt-6 text-2xl">{account.user.role === "owner" ? "Owner access · No Credit charge" : `Balance: ${account.wallet.balance} Credits`}</p>
      <div className="mt-5 flex gap-5"><Link href="/redeem" className="underline">Redeem Code</Link><Link href="/analyze" className="underline">Run Analysis</Link></div>
      <h2 className="mt-10 text-xl">Recent credit transactions</h2>
      <ul className="mt-4 divide-y divide-black/10">{account.wallet.transactions.map(entry => <li key={entry.id} className="py-3">
        {entry.amount > 0 ? "+" : ""}{entry.amount} · {entry.transaction_type} · Balance {entry.balance_after}
      </li>)}</ul>
      {!account.wallet.transactions.length && <p className="mt-3">No credit transactions yet.</p>}
    </>}
    <h2 className="mt-10 text-xl">Recent analyses</h2>
    <ul className="mt-4 space-y-3">{account.analyses.map(analysis => <li key={analysis.id}><Link href={`/result/${analysis.id}?funding=credits`} className="underline">Synthetic analysis · {analysis.status}</Link></li>)}</ul>
    {!account.analyses.length && <p className="mt-3">No analyses yet.</p>}
    {!historyOnly && <button className={buttonClass} onClick={async () => {
      try {await accountRequest("/auth/logout", z.object({logged_out: z.boolean()}), {}); router.push("/login"); router.refresh();}
      catch (error) {setLogoutError(message(error));}
    }}>Sign out</button>}
    {logoutError && <p role="alert" className="mt-4">{logoutError}</p>}
  </section>;
}

export function RedeemPage() {
  const {account, setAccount, error, loaded} = useAccount();
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  if (!loaded) return <p>Loading account…</p>;
  if (!account) return <p>{error} <Link href="/login" className="underline">Sign in</Link></p>;
  return <section className="max-w-md">
    <h1 className="text-3xl font-medium">Redeem Code</h1>
    <p className="mt-5">Enter the code you received after purchase.</p>
    <p className="mt-5">Balance: {account.wallet.balance} Credits</p>
    <form className="mt-6" onSubmit={async event => {
      event.preventDefault(); const formElement = event.currentTarget;
      const code = String(new FormData(formElement).get("code"));
      setBusy(true); setFeedback("");
      try {
        const result = await accountRequest("/redeem", redemptionSchema, {code});
        setAccount({...account, wallet: {...account.wallet, balance: result.balance}});
        setFeedback(`${result.credits_added} Credits added`); formElement.reset();
      } catch (error) {setFeedback(message(error));} finally {setBusy(false);}
    }}>
      <label>Redemption Code<input name="code" required maxLength={40} autoComplete="off" spellCheck={false} className={inputClass}/></label>
      <button disabled={busy} className={buttonClass}>Redeem</button>
    </form>
    {feedback && <p role="status" className="mt-5">{feedback}</p>}
    <Link href="/analyze" className="mt-6 inline-block underline">Run Analysis</Link>
  </section>;
}

export function AccountAnalyze({children}: {children: React.ReactNode}) {
  const {account, loaded} = useAccount();
  const [products, setProducts] = useState<CreditProduct[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Retain the same key after a network failure. An explicit new run gets a new key.
  const [requestKey, setRequestKey] = useState<string | null>(null);
  const router = useRouter();
  useEffect(() => {
    if (account) accountRequest("/credit-products", creditProductsSchema).then(setProducts).catch(error => setError(message(error)));
  }, [account]);
  if (!loaded) return <p>Loading…</p>;
  if (!account) return <><p className="mb-8"><Link href="/login" className="underline">Sign in</Link> to use Credits, or <Link href="/register" className="underline">create an account</Link>.</p>{children}</>;
  const product = products[0];
  return <section className="max-w-xl">
    <h1 className="text-3xl font-medium">Auvylen Analysis</h1>
    <p className="mt-6 text-xl">{account.user.role === "owner" ? "Owner · No Credit charge" : `Balance: ${account.wallet.balance} Credits`}</p>
    {product && <>
      <p className="mt-5">Cost: {product.credit_cost} Credit{product.credit_cost === 1 ? "" : "s"}</p>
      <p className="mt-5">Development / Synthetic Result. No photo or real facial model is used.</p>
      {!product.available ? <p className="mt-5">Synthetic analysis is unavailable in production.</p> : <button className={buttonClass} disabled={busy} onClick={async () => {
        setBusy(true); setError(""); const key = requestKey ?? crypto.randomUUID(); setRequestKey(key);
        try {
          const analysis = await accountRequest("/credit-analyses", analysisSchema, {product_slug: product.slug, idempotency_key: key});
          router.push(`/result/${analysis.id}?funding=credits`);
        } catch (error) {setError(message(error));} finally {setBusy(false);}
      }}>Run Analysis</button>}
    </>}
    {error && <p role="alert" className="mt-5">{error}</p>}
    <Link href="/redeem" className="mt-8 inline-block underline">Redeem Code</Link>
  </section>;
}
