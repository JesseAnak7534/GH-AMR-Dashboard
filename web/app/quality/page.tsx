import type { Metadata } from "next";
import { Container, PageHeader } from "@/components/Chrome";
import { getQuality } from "@/lib/clinical";
import { QualityView } from "./QualityView";

export const metadata: Metadata = {
  title: "Data quality",
  description:
    "Coverage, field completeness, timeliness, chain linkage, result " +
    "provenance, implausible organism-agent combinations and missing " +
    "denominators behind the figures on this site.",
};

export default function QualityPage() {
  return (
    <>
      <PageHeader
        badge="DQ"
        colour="#4a5568"
        title="Data coverage and quality"
        lede="Whether the data can support the figures drawn from it. Every rate elsewhere on this site should be read against this page."
      />
      <Container>
        <QualityView data={getQuality()} />
      </Container>
    </>
  );
}
