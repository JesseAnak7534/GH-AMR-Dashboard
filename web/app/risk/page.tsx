import type { Metadata } from "next";
import { Container, PageHeader } from "@/components/Chrome";
import { getRisk } from "@/lib/clinical";
import { RiskView } from "./RiskView";

export const metadata: Metadata = {
  title: "Risk",
  description:
    "Composite organism risk scores, the burden of resistance by specimen, " +
    "emerging organism-agent patterns, the direction of travel and an " +
    "exploratory susceptibility summary.",
};

export default function RiskPage() {
  return (
    <>
      <PageHeader
        badge="RISK"
        colour="#8c1d18"
        title="Risk and signals"
        lede="Which organisms carry the most resistance, where the burden sits, what is emerging, and where the trend is heading."
      />
      <Container>
        <RiskView data={getRisk()} />
      </Container>
    </>
  );
}
