import type {Metadata} from "next";
import {PhotoCheck} from "@/components/photo-check";

export const metadata: Metadata = {title: "Free photo check"};

export default function Page() {return <PhotoCheck />;}
