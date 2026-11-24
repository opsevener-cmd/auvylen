import {ResearchPage} from "@/components/research-page";
import {features} from "@/lib/features";

export const dynamic = "force-dynamic";

export default function Page() {
  const {aesthetic, syntheticAnalysis} = features();
  return <ResearchPage showAesthetic={aesthetic} showSynthetic={syntheticAnalysis} />;
}
