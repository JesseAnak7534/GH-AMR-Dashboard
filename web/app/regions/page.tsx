import type { Metadata } from "next";
import { Container, PageHeader } from "@/components/Chrome";
import { getRegions } from "@/lib/data";
import { RegionsView } from "./RegionsView";

export const metadata: Metadata = {
  title: "Regions",
  description:
    "Where surveillance isolates in Ghana were collected, region by region, " +
    "and how much each region contributes.",
};

export default function RegionsPage() {
  return (
    <>
      <PageHeader
        badge="GEO"
        colour="#1d4d43"
        title="Regions"
        lede="Where the isolates came from. Differences between regions reflect surveillance coverage as much as biology."
      />
      <Container>
        <RegionsView data={getRegions()} />
      </Container>
    </>
  );
}
