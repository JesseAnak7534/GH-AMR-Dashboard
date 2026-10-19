import type { Metadata } from "next";
import { Container, Note, PageHeader } from "@/components/Chrome";
import { PooledSection } from "@/components/Pooled";
import { getUse } from "@/lib/data";
import { OKABE_ITO } from "@/lib/palette";

export const metadata: Metadata = {
  title: "AMC — veterinary antimicrobial consumption",
  description:
    "Veterinary antimicrobial consumption in Ghana, as milligrams of active " +
    "ingredient per kilogram of animal biomass.",
};

export default function AmcPage() {
  const data = getUse();
  return (
    <>
      <PageHeader
        badge="AMC"
        colour="#999999"
        title="AMC"
        lede="Veterinary consumption, as milligrams of active ingredient per kilogram of biomass."
      />
      <Container>
        <PooledSection
          title="Milligrams per kilogram of biomass"
          blocks={data.amc}
          valueKey="mg_per_kg_biomass"
          unit="mg per kg biomass"
          colour={OKABE_ITO.grey}
          note="Biomass is the denominator: the same tonnage means something different across poultry than across cattle."
        />
        <Note>
          Rates are pooled, never averaged. A record with no usable denominator
          is excluded, not counted as zero.
        </Note>
      </Container>
    </>
  );
}
