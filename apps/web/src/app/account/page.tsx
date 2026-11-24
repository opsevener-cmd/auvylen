import {AccountPage} from "@/components/account-pages";
import {features} from "@/lib/features";

export const dynamic = "force-dynamic";

export default function Account() {return <AccountPage showAnalyses={features().syntheticAnalysis}/>;}
