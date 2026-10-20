import type { Metadata } from "next";
import { Container, Note, PageHeader } from "@/components/Chrome";
import { ConsumptionView } from "@/components/ConsumptionView";
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
        lede="Veterinary antimicrobial consumption: milligrams of active ingredient per kilogram of biomass."
      />
      <Container>
        <ConsumptionView
          blocks={data.amc}
          valueKey="mg_per_kg_biomass"
          unit="mg per kg biomass"
          colour={OKABE_ITO.vermillion}
          volumeKey="active_ingredient_kg"
          volumeShort="kg"
          volumeUnit="Active ingredient (kg)"
          compositionKeys={["sector", "purpose", "route"]}
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
