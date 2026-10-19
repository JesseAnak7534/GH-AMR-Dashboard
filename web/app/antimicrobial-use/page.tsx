import type { Metadata } from "next";
import { Container, PageHeader } from "@/components/Chrome";
import { getUse } from "@/lib/data";
import { UseView } from "./UseView";

export const metadata: Metadata = {
  title: "Antimicrobial use",
  description:
    "Human and veterinary antimicrobial consumption and hospital prescribing, " +
    "reported as pooled rates with their denominators.",
};

export default function UsePage() {
  const data = getUse();
  return (
    <>
      <PageHeader
        badge="AMU"
        colour="#E69F00"
        title="Antimicrobial use"
        lede="How much antimicrobial is being used, in people and in animals, and how it is prescribed. Resistance and use are the two halves of the same question."
      />
      <Container>
        <UseView data={data} />
      </Container>
    </>
  );
}
