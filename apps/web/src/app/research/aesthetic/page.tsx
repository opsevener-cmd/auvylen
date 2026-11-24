import {notFound} from "next/navigation";
import {AestheticAnalysisPage} from "@/components/aesthetic-analysis";
import {features} from "@/lib/features";

export const dynamic = "force-dynamic";

export default function Page() {
  if (!features().aesthetic) notFound();
  return <AestheticAnalysisPage />;
}
