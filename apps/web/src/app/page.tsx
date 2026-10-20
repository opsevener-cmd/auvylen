import {HomePage} from "@/components/home-page";
export default function Home() {return <HomePage syntheticAvailable={process.env.APP_ENV !== "production"} />;}
