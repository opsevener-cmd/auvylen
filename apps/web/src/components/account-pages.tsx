"use client";
import {useI18n} from "@/components/i18n/provider";

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
  const {t} = useI18n();
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return <section className="max-w-md">
    <h1 className="text-3xl font-medium">{mode === "register" ? t("Create account") : t("Sign in")}</h1>
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
      <label className="block">{t("Username or email-like identifier")}<input name="identifier" required minLength={3} maxLength={120} autoComplete="username" className={inputClass}/></label>
      <label className="block">{t("Password")}<input name="password" type="password" required minLength={12} maxLength={128} autoComplete={mode === "register" ? "new-password" : "current-password"} className={inputClass}/></label>
      <button disabled={busy} className={buttonClass}>{mode === "register" ? t("Create account") : t("Sign in")}</button>
    </form>
    {error && <p role="alert" className="mt-5">{t(error)}</p>}
    <p className="mt-6 text-sm">{t("Use 12–128 characters. Pilot accounts have no email verification or self-service password recovery. Keep your credentials safe.")}</p>
    <Link className="mt-6 inline-block underline" href={mode === "register" ? "/login" : "/register"}>{mode === "register" ? t("Already have an account? Sign in") : t("Create account")}</Link>
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
  const {t} = useI18n();
  const {account, error, loaded} = useAccount();
  const router = useRouter();
  const [logoutError, setLogoutError] = useState("");
  if (!loaded) return <p>{t("Loading account…")}</p>;
  if (!account) return <p>{t(error)} <Link href="/login" className="underline">{t("Sign in")}</Link></p>;
  return <section className="max-w-2xl">
    <h1 className="text-3xl font-medium">{historyOnly ? t("Analysis history") : t("Your account")}</h1>
    {!historyOnly && <>
      <p className="mt-5">{account.user.login_identifier}{account.user.role === "owner" ? t(" · OWNER") : ""}</p>
      <p className="mt-6 text-2xl">{account.user.role === "owner" ? t("Owner access · No Credit charge") : t("Balance: {value0} Credits", {value0: account.wallet.balance})}</p>
      <div className="mt-5 flex gap-5">{account.user.role === "owner" ? <Link href="/owner" className="underline">{t("Owner dashboard")}</Link> : <Link href="/redeem" className="underline">{t("Redeem Code")}</Link>}<Link href="/analyze" className="underline">{t("Run Analysis")}</Link></div>
      <h2 className="mt-10 text-xl">{t("Recent credit transactions")}</h2>
      <ul className="mt-4 divide-y divide-black/10">{account.wallet.transactions.map(entry => <li key={entry.id} className="py-3">
        {entry.amount > 0 ? "+" : ""}{entry.amount} · {t(entry.transaction_type)} {t("· Balance")} {entry.balance_after}
      </li>)}</ul>
      {!account.wallet.transactions.length && <p className="mt-3">{t("No credit transactions yet.")}</p>}
    </>}
    <h2 className="mt-10 text-xl">{t("Recent analyses")}</h2>
    <ul className="mt-4 space-y-3">{account.analyses.map(analysis => <li key={analysis.id}><Link href={`/result/${analysis.id}?funding=credits`} className="underline">{t("Synthetic analysis ·")} {t(analysis.status)}</Link></li>)}</ul>
    {!account.analyses.length && <p className="mt-3">{t("No analyses yet.")}</p>}
    {!historyOnly && <button className={buttonClass} onClick={async () => {
      try {await accountRequest("/auth/logout", z.object({logged_out: z.boolean()}), {}); router.push("/login"); router.refresh();}
      catch (error) {setLogoutError(message(error));}
    }}>{t("Sign out")}</button>}
    {logoutError && <p role="alert" className="mt-4">{t(logoutError)}</p>}
  </section>;
}

export function RedeemPage() {
  const {t} = useI18n();
  const {account, setAccount, error, loaded} = useAccount();
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  if (!loaded) return <p>{t("Loading account…")}</p>;
  if (!account) return <p>{t(error)} <Link href="/login" className="underline">{t("Sign in")}</Link></p>;
  return <section className="max-w-md">
    <h1 className="text-3xl font-medium">{t("Redeem Code")}</h1>
    <p className="mt-5">{t("Enter the code you received after purchase.")}</p>
    <p className="mt-5">{t("Balance:")} {account.wallet.balance} {t("Credits")}</p>
    <form className="mt-6" onSubmit={async event => {
      event.preventDefault(); const formElement = event.currentTarget;
      const code = String(new FormData(formElement).get("code"));
      setBusy(true); setFeedback("");
      try {
        const result = await accountRequest("/redeem", redemptionSchema, {code});
        setAccount({...account, wallet: {...account.wallet, balance: result.balance}});
        setFeedback(String(result.credits_added)); formElement.reset();
      } catch (error) {setFeedback(message(error));} finally {setBusy(false);}
    }}>
      <label>{t("Redemption Code")}<input name="code" required maxLength={40} autoComplete="off" spellCheck={false} className={inputClass}/></label>
      <button disabled={busy} className={buttonClass}>{t("Redeem")}</button>
    </form>
    {feedback && <p role="status" className="mt-5">{/^\d+$/.test(feedback) ? t("{count} Credits added", {count: feedback}) : t(feedback)}</p>}
    <Link href="/analyze" className="mt-6 inline-block underline">{t("Run Analysis")}</Link>
  </section>;
}

export function AccountAnalyze({children}: {children: React.ReactNode}) {
  const {t} = useI18n();
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
  if (!loaded) return <p>{t("Loading…")}</p>;
  if (!account) return <><p className="mb-8"><Link href="/login" className="underline">{t("Sign in")}</Link> {t("to use Credits, or")} <Link href="/register" className="underline">{t("create an account")}</Link>.</p>{children}</>;
  const product = products[0];
  return <section className="max-w-xl">
    <h1 className="text-3xl font-medium">{t("Auvylen Analysis")}</h1>
    <p className="mt-6 text-xl">{account.user.role === "owner" ? t("Owner · No Credit charge") : t("Balance: {value0} Credits", {value0: account.wallet.balance})}</p>
    {product && <>
      <p className="mt-5">{t(product.credit_cost === 1 ? "Cost: {count} Credit" : "Cost: {count} Credits", {count: product.credit_cost})}</p>
      <p className="mt-5">{t("Development / Synthetic Result. No photo or real facial model is used.")}</p>
      {!product.available ? <p className="mt-5">{t("Synthetic analysis is unavailable in production.")}</p> : <button className={buttonClass} disabled={busy} onClick={async () => {
        setBusy(true); setError(""); const key = requestKey ?? crypto.randomUUID(); setRequestKey(key);
        try {
          const analysis = await accountRequest("/credit-analyses", analysisSchema, {product_slug: product.slug, idempotency_key: key});
          router.push(`/result/${analysis.id}?funding=credits`);
        } catch (error) {setError(message(error));} finally {setBusy(false);}
      }}>{t("Run Analysis")}</button>}
    </>}
    {error && <p role="alert" className="mt-5">{t(error)}</p>}
    {account.user.role === "owner" ? <Link href="/owner" className="mt-8 inline-block underline">{t("Owner dashboard")}</Link> : <Link href="/redeem" className="mt-8 inline-block underline">{t("Redeem Code")}</Link>}
  </section>;
}
