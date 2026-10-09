import { redirect } from "next/navigation";

/** Keep the legacy site URL stable while routing it to the data-backed console. */
export default function SitePage() {
  redirect("/supervisor");
}
