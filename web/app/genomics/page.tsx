import type { Metadata } from "next";
import { Container, PageHeader } from "@/components/Chrome";
import { getCustody, getGenomics } from "@/lib/data";
import { GenomicsView } from "./GenomicsView";

export const metadata: Metadata = {
  title: "Genomics",
  description:
    "Resistance determinants found by sequencing, how often they explain the " +
    "laboratory result, and which genomes are closely related.",
};

export default function GenomicsPage() {
  const data = getGenomics();
  const custody = getCustody();
  return (
    <>
      <PageHeader
        badge="WGS"
        colour="#CC79A7"
        title="Genomics"
        lede="The genes behind the resistance, and which genomes look alike."
      />
      <Container>
        <GenomicsView data={data} custody={custody} />
      </Container>
    </>
  );
}
