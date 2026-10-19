import type { Metadata } from "next";
import { Container, PageHeader } from "@/components/Chrome";
import { getUse } from "@/lib/data";
import { PpsView } from "./PpsView";

export const metadata: Metadata = {
  title: "PPS — point prevalence of antibiotic use",
  description:
    "Point prevalence surveys of antibiotic prescribing in Ghanaian " +
    "hospitals: how many patients were on an antibiotic, and what was given.",
};

export default function PpsPage() {
  const data = getUse();
  return (
    <>
      <PageHeader
        badge="PPS"
        colour="#8a6a22"
        title="PPS"
        lede="How many of the patients present on the survey day were on an antibiotic, and what was prescribed."
      />
      <Container>
        <PpsView data={data} />
      </Container>
    </>
  );
}
