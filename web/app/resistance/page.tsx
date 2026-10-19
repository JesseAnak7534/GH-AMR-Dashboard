import type { Metadata } from "next";
import { Container, PageHeader } from "@/components/Chrome";
import { getResistance } from "@/lib/data";
import { ResistanceView } from "./ResistanceView";

export const metadata: Metadata = {
  title: "Resistance",
  description:
    "Susceptibility by organism and antibiotic, with the number of isolates " +
    "behind every figure and a 95% confidence interval on every percentage.",
};

/**
 * The server half: read the published figures at build time and hand them to
 * the client component that lets the reader switch sector and sort the table.
 * The data arrives in the HTML, so the first paint already has the numbers.
 */
export default function ResistancePage() {
  const data = getResistance();
  return (
    <>
      <PageHeader
        badge="AST"
        colour="#0072B2"
        title="Resistance"
        lede="How often the organisms being isolated still respond to the antibiotics used against them. Each percentage is the proportion of tested isolates that remained susceptible, with the number tested and a 95% confidence interval."
      />
      <Container>
        <ResistanceView data={data} />
      </Container>
    </>
  );
}
