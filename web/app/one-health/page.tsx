import type { Metadata } from "next";
import { Container, PageHeader } from "@/components/Chrome";
import { getOneHealth } from "@/lib/data";
import { OneHealthView } from "./OneHealthView";

export const metadata: Metadata = {
  title: "One Health",
  description:
    "Human, animal, food, environmental and aquaculture surveillance compared " +
    "side by side, never pooled into a single national rate.",
};

export default function OneHealthPage() {
  const data = getOneHealth();
  return (
    <>
      <PageHeader
        badge="OH"
        colour="#009E73"
        title="One Health"
        lede="The same surveillance across human, animal, food, environmental and aquaculture sources — counted separately, because resistance means something different in each."
      />
      <Container>
        <OneHealthView data={data} />
      </Container>
    </>
  );
}
