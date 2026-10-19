import type { Metadata } from "next";
import { Container, PageHeader } from "@/components/Chrome";
import { getOrganisms } from "@/lib/data";
import { OrganismsView } from "./OrganismsView";

export const metadata: Metadata = {
  title: "Organisms",
  description:
    "What is being isolated across human, animal, food, environmental and " +
    "aquaculture surveillance, counted as isolates rather than test results.",
};

export default function OrganismsPage() {
  const data = getOrganisms();
  return (
    <>
      <PageHeader
        badge="ORG"
        colour="#D55E00"
        title="Organisms"
        lede="What is actually being isolated, counted as isolates rather than as test results, and the specimens they were grown from."
      />
      <Container>
        <OrganismsView data={data} />
      </Container>
    </>
  );
}
