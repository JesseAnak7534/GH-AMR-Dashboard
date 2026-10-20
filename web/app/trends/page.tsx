import type { Metadata } from "next";
import { Container, PageHeader } from "@/components/Chrome";
import { getTrends } from "@/lib/data";
import { TrendsView } from "./TrendsView";

export const metadata: Metadata = {
  title: "Trends",
  description:
    "How antimicrobial resistance has moved over time in Ghana, by quarter, " +
    "with confidence bands so a change can be read against its uncertainty.",
};

export default function TrendsPage() {
  return (
    <>
      <PageHeader
        badge="TIME"
        colour="#56B4E9"
        title="Trends"
        lede="Resistance by quarter. Where the bands overlap, the change is within the uncertainty."
      />
      <Container>
        <TrendsView data={getTrends()} />
      </Container>
    </>
  );
}
