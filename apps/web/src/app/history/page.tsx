import {notFound} from "next/navigation";
import {AccountPage} from "@/components/account-pages";
import {features} from "@/lib/features";

export const dynamic = "force-dynamic";

export default function History() {
  if (!features().syntheticAnalysis) notFound();
  return <AccountPage historyOnly showAnalyses/>;
}
