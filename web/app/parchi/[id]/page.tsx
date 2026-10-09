import { redirect } from "next/navigation";

/** Parchis are opened only through the worker's single-use QR link. */
export default function LegacyParchiPage() {
  redirect("/worker");
}
