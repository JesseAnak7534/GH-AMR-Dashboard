import type { Metadata } from "next";
import { Container, PageHeader } from "@/components/Chrome";
import { getComparison } from "@/lib/clinical";
import { ComparisonView } from "./ComparisonView";

export const metadata: Metadata = {
  title: "Comparison",
  description:
    "Resistance compared between laboratories, regions, wards, specimen " +
    "types, age bands and periods in Ghana, on one denominator, with the 95% " +
    "confidence interval beside every figure.",
};

export default function ComparisonPage() {
  return (
    <>
      <PageHeader
        badge="CMP"
        colour="#0b6e6e"
        title="Comparative analysis"
        lede="Resistance between laboratories, regions, wards, specimens and periods."
      />
      <Container>
        <ComparisonView data={getComparison()} />
      </Container>
    </>
  );
}
