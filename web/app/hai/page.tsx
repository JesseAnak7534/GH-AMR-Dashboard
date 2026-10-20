import type { Metadata } from "next";
import { Container, PageHeader } from "@/components/Chrome";
import { getHai } from "@/lib/clinical";
import { HaiView } from "./HaiView";

export const metadata: Metadata = {
  title: "Hospital infection",
  description:
    "Healthcare-associated infection in Ghana: ESKAPE organisms, the hospital " +
    "resistance profile, multidrug resistance in hospital, and sentinel " +
    "laboratory comparison.",
};

export default function HaiPage() {
  return (
    <>
      <PageHeader
        badge="HAI"
        colour="#3b4e8c"
        title="Hospital infection"
        lede="Human clinical isolates: the organisms behind most healthcare-associated infection, how resistant they are, how much of it is multidrug resistant, and how that has moved."
      />
      <Container>
        <HaiView data={getHai()} />
      </Container>
    </>
  );
}
