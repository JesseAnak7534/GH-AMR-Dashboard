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
        lede="The organisms behind healthcare-associated infection, and how resistant they are."
      />
      <Container>
        <HaiView data={getHai()} />
      </Container>
    </>
  );
}
