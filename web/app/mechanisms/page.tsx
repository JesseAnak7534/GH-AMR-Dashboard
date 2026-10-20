import type { Metadata } from "next";
import { Container, PageHeader } from "@/components/Chrome";
import { getMechanisms } from "@/lib/clinical";
import { MechanismsView } from "./MechanismsView";

export const metadata: Metadata = {
  title: "Resistance mechanisms",
  description:
    "ESBL, carbapenemase, MRSA and AmpC phenotypes, cross-resistance within " +
    "an antibiotic class, and how many agents each isolate resists.",
};

export default function MechanismsPage() {
  return (
    <>
      <PageHeader
        badge="MECH"
        colour="#7a1f6b"
        title="Resistance mechanisms"
        lede="The phenotypes that point to an enzyme, resistance across a whole class, and how many agents an isolate defeats."
      />
      <Container>
        <MechanismsView data={getMechanisms()} />
      </Container>
    </>
  );
}
