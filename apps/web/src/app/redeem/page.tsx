import {redirect} from "next/navigation";

// Redemption lives in the Account page's Credits section.
export default function Redeem() {redirect("/account#credits");}
