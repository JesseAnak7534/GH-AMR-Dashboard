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
        lede="Resistance between groups, on one denominator, with the uncertainty shown. Comparing is where surveillance data misleads most easily, so small groups keep their counts and lose their percentages, and two groups whose intervals overlap are described as not distinguishable rather than ranked."
      />
      <Container>
        <ComparisonView data={getComparison()} />
      </Container>
    </>
  );
}
