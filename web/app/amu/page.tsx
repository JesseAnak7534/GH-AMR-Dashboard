import type { Metadata } from "next";
import { Container, Note, PageHeader } from "@/components/Chrome";
import { ConsumptionView } from "@/components/ConsumptionView";
import { getUse } from "@/lib/data";
import { OKABE_ITO } from "@/lib/palette";

export const metadata: Metadata = {
  title: "AMU — human antimicrobial use",
  description:
    "Human antimicrobial consumption in Ghana, as defined daily doses per " +
    "1,000 patient-days, pooled across facilities.",
};

export default function AmuPage() {
  const data = getUse();
  return (
    <>
      <PageHeader
        badge="AMU"
        colour="#E69F00"
        title="AMU"
        lede="Human antimicrobial use: defined daily doses per 1,000 patient-days, with the volume dispensed behind it."
      />
      <Container>
        <ConsumptionView
          blocks={data.amu}
          valueKey="ddd_per_1000_patient_days"
          unit="DDD per 1,000 patient-days"
          colour={OKABE_ITO.orange}
          volumeKey="quantity_dispensed"
          volumeUnit="Quantity dispensed"
          note="A defined daily dose is an assumed average adult dose, not one anyone was given. It makes volumes comparable; it does not describe any patient."
        />
        <Note>
          Rates are pooled, never averaged across facilities. A record with no
          usable denominator is excluded, not counted as zero.
        </Note>
      </Container>
    </>
  );
}
