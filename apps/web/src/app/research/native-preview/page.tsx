import {notFound} from "next/navigation";
import {NativePreviewPage} from "@/components/native-preview";
import {features} from "@/lib/features";

export const dynamic = "force-dynamic";

export default function Page() {
  if (!features().nativePreview) notFound();
  return <NativePreviewPage />;
}
