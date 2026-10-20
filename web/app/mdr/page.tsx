import type { Metadata } from "next";
import { Container, PageHeader } from "@/components/Chrome";
import { getMdr } from "@/lib/data";
import { MdrView } from "./MdrView";

export const metadata: Metadata = {
  title: "Multidrug resistance",
  description:
    "Multidrug-resistant and extensively drug-resistant isolates in Ghana, " +
    "classified to the Magiorakos definitions.",
};

export default function MdrPage() {
  return (
    <>
      <PageHeader
        badge="MDR"
        colour="#000000"
        title="Multidrug resistance"
        lede="Isolates resistant across three or more antimicrobial categories."
      />
      <Container>
        <MdrView data={getMdr()} />
      </Container>
    </>
  );
}
