import {HomePage} from "@/components/home-page";
import {features} from "@/lib/features";
export default function Home() {return <HomePage syntheticAvailable={features().syntheticAnalysis} />;}
