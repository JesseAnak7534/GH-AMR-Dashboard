"""
Enhanced AI Assistant for AMR Surveillance Dashboard
Provides intelligent reasoning beyond just the dataset.

Uses the Claude API (Anthropic) when an ANTHROPIC_API_KEY is configured, and
falls back to a rich local rule-based reasoner when it is not.
"""

import os
import pandas as pd
from src import analytics


# Default Claude model. Override with the ANTHROPIC_MODEL env var / Streamlit secret.
DEFAULT_MODEL = "claude-opus-4-8"


def _resolve_secret(name: str):
    """Resolve a secret from Streamlit secrets (cloud) or the environment (.env / shell)."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and name in st.secrets:
            val = st.secrets.get(name)
            if val:
                return str(val).strip()
    except (FileNotFoundError, KeyError, AttributeError, ImportError):
        pass
    val = os.getenv(name)
    return val.strip() if val else None


class EnhancedAIAssistant:
    """AI Assistant with reasoning capabilities for AMR surveillance."""

    def __init__(self):
        """Initialize the AI Assistant."""
        # API key comes from the environment or Streamlit secrets — never hardcoded.
        self.api_key = _resolve_secret("ANTHROPIC_API_KEY")
        self.model = _resolve_secret("ANTHROPIC_MODEL") or DEFAULT_MODEL
        self.anthropic_available = False
        self.client = None

        if self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
                self.anthropic_available = True
            except Exception:
                # SDK missing or client init failed -> fall back to local reasoning.
                self.anthropic_available = False

        # Domain knowledge database
        self.common_organisms = {
            "Staphylococcus aureus": "MRSA - Healthcare and community pathogen",
            "Escherichia coli": "ESBL producers - UTIs and sepsis",
            "Klebsiella pneumoniae": "Carbapenem-resistant - Nosocomial infections",
            "Pseudomonas aeruginosa": "High intrinsic resistance - Respiratory infections",
            "Acinetobacter baumannii": "Extremely drug-resistant - ICU threat",
            "Salmonella": "Foodborne pathogen - Emerging resistance",
            "Vibrio cholerae": "Cholera - Important for Ghana",
        }

    def get_response(self, user_query: str, all_ast: pd.DataFrame, all_samples: pd.DataFrame) -> str:
        """Get AI-generated response."""

        # Try Claude if a key is configured
        if self.anthropic_available:
            try:
                return self._get_anthropic_response(user_query, all_ast, all_samples)
            except Exception:
                # Any API/network/parsing error -> graceful local fallback.
                pass

        # Fall back to advanced local reasoning
        return self._get_local_response(user_query, all_ast, all_samples)

    def _get_anthropic_response(self, user_query: str, all_ast: pd.DataFrame, all_samples: pd.DataFrame) -> str:
        """Get response from the Claude API."""

        # Prepare data context
        if all_ast.empty or all_samples.empty:
            context = "No data available"
        else:
            stats = analytics.calculate_resistance_statistics(all_ast)
            context = f"""Your surveillance dataset:
- Tests: {len(all_ast):,}
- Resistance rate: {stats.get('resistance_rate', 0):.1f}%
- Organisms: {all_ast['organism'].nunique()}
- Antibiotics: {all_ast['antibiotic'].nunique()}"""

        system_prompt = f"""You are an expert AMR epidemiologist and public health specialist.
{context}

You can:
1. Analyze the user's surveillance data
2. Reason beyond the data using expert knowledge
3. Provide evidence-based recommendations
4. Explain resistance mechanisms
5. Connect findings to global AMR trends

Be practical, actionable, and connect to Ghana/Africa context when relevant."""

        # Adaptive thinking lets Claude decide how much to reason per question —
        # good for clinical/epidemiological queries. Drop the `thinking` arg for
        # lower latency if responses feel slow.
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=system_prompt,
            messages=[{"role": "user", "content": user_query}],
        )

        # Response content is a list of blocks; keep the text, skip thinking blocks.
        text = "\n".join(
            block.text for block in response.content
            if getattr(block, "type", None) == "text"
        ).strip()

        if not text:
            # Empty (e.g. a refusal) -> trigger the local fallback in get_response.
            raise RuntimeError("Empty response from Claude")

        return text

    def _get_local_response(self, user_query: str, all_ast: pd.DataFrame, all_samples: pd.DataFrame) -> str:
        """Advanced local reasoning."""

        if all_ast.empty or all_samples.empty:
            return "No data available. Please upload data first in Upload & Data Quality."

        query_lower = user_query.lower()
        stats = analytics.calculate_resistance_statistics(all_ast)
        resistance_rate = stats.get('resistance_rate', 0)

        # Data analysis queries
        if any(word in query_lower for word in ['summary', 'overall', 'resistance rate', 'general']):
            return self._summarize_data(all_ast, all_samples, stats)

        elif any(word in query_lower for word in ['organism', 'pathogen', 'bacteria', 'species']):
            return self._analyze_organisms(all_ast, stats)

        elif any(word in query_lower for word in ['antibiotic', 'drug', 'treatment', 'susceptible']):
            return self._analyze_antibiotics(all_ast)

        elif any(word in query_lower for word in ['region', 'geographic', 'location', 'hotspot']):
            return self._analyze_geography(all_samples)

        elif any(word in query_lower for word in ['trend', 'temporal', 'time', 'change', 'pattern']):
            return self._analyze_trends(all_ast)

        # Recommendation queries
        elif any(word in query_lower for word in ['recommend', 'suggest', 'should', 'action', 'prevent']):
            return self._provide_recommendations(stats, resistance_rate, all_ast)

        # Educational queries
        elif any(word in query_lower for word in ['how', 'why', 'explain', 'mechanism', 'develop']):
            return self._explain_amr_concepts(query_lower)

        elif any(word in query_lower for word in ['risk', 'danger', 'threat', 'concern', 'critical']):
            return self._assess_risks(resistance_rate)

        # Default
        else:
            return self._intelligent_fallback(user_query, stats, resistance_rate)

    def _summarize_data(self, all_ast, all_samples, stats) -> str:
        """Summarize surveillance data with interpretation."""

        resistance_rate = stats.get('resistance_rate', 0)

        summary = f"""**Your Surveillance Data:**
- Total tests: {len(all_ast):,}
- Resistance rate: **{resistance_rate:.1f}%**
- Susceptible: {stats.get('susceptible_rate', 0):.1f}%
- Intermediate: {stats.get('intermediate_rate', 0):.1f}%
- Organisms: {all_ast['organism'].nunique()}
- Antibiotics: {all_ast['antibiotic'].nunique()}
"""

        # Add interpretation
        if resistance_rate > 75:
            summary += "\n🔴 **CRITICAL**: Resistance >75% - Public health emergency"
        elif resistance_rate > 50:
            summary += "\n🟠 **HIGH**: Resistance 50-75% - Urgent intervention needed"
        elif resistance_rate > 30:
            summary += "\n🟡 **MODERATE**: Resistance 30-50% - Active surveillance required"
        else:
            summary += "\n🟢 **CONTROLLED**: Resistance <30% - Continue current practices"

        summary += "\n\n**What this means:**\n"
        summary += "- These rates reflect current surveillance capacity and practices\n"
        summary += "- Limited diagnostics may underestimate resistance in resource-limited areas\n"
        summary += "- Resistance continues to evolve - track trends over time\n"
        summary += "- Local patterns should guide empirical therapy and infection prevention"

        return summary

    def _analyze_organisms(self, all_ast, stats) -> str:
        """Analyze top organisms with clinical context."""

        top_orgs = all_ast['organism'].value_counts().head(5)

        response = "**Top Organisms:**\n\n"

        for organism, count in top_orgs.items():
            org_data = all_ast[all_ast['organism'] == organism]
            org_resistance = (org_data['result'] == 'R').sum() / len(org_data) * 100

            response += f"• **{organism}**: {count} tests ({org_resistance:.1f}% resistant)\n"

            if organism in self.common_organisms:
                response += f"  - {self.common_organisms[organism]}\n"

        response += """\n**Key Points:**
- Focus infection prevention on high-resistance organisms
- Use local patterns to guide empirical therapy
- Consider organism-specific control measures
- Monitor for emerging resistance in previously susceptible species"""

        return response

    def _analyze_antibiotics(self, all_ast) -> str:
        """Analyze antibiotic effectiveness."""

        top_abs = all_ast['antibiotic'].value_counts().head(5)

        response = "**Antibiotic Resistance Pattern:**\n\n"

        for antibiotic, count in top_abs.items():
            ab_data = all_ast[all_ast['antibiotic'] == antibiotic]
            ab_resistance = (ab_data['result'] == 'R').sum() / len(ab_data) * 100

            status = "Avoid" if ab_resistance > 50 else "Use"
            response += f"• **{antibiotic}**: {ab_resistance:.1f}% resistant [{status}]\n"

        response += """\n**Stewardship Actions:**
- Restrict high-resistance antibiotics to documented susceptible infections
- Use combination therapy strategically
- Implement rapid diagnostics to guide therapy
- Monitor for emerging resistance patterns"""

        return response

    def _analyze_geography(self, all_samples) -> str:
        """Analyze geographic distribution."""

        if 'region' not in all_samples.columns:
            return "Geographic data not available. Add region/district information to your data."

        top_regions = all_samples['region'].value_counts().head(5)

        response = f"**Geographic Coverage ({all_samples['region'].nunique()} regions):**\n\n"

        for region, count in top_regions.items():
            response += f"• {region}: {count} samples\n"

        response += """\n**Ghana Context:**
- High-burden regions need enhanced resources
- Rural areas may have diagnostic gaps
- Infrastructure differences affect resistance patterns
- Climate/water access influences pathogen transmission"""

        return response

    def _analyze_trends(self, all_ast) -> str:
        """Analyze temporal trends."""

        if 'test_date' not in all_ast.columns:
            return "Date information not available. Add test dates to track resistance trends."

        return """**Trend Analysis:**

Key questions:
- Is resistance increasing or decreasing?
- Do patterns show seasonal variation?
- Are specific organisms becoming more resistant?

**Interpretation Tips:**
- Small datasets show random fluctuation - look for 6+ month trends
- Tropical regions often have seasonal resistance changes
- Infection prevention improvements show effects after 2-3 months
- Watch for emerging resistance to newer antibiotics

Check the Trends page for detailed visualization."""

    def _provide_recommendations(self, stats, resistance_rate, all_ast) -> str:
        """Provide evidence-based public health recommendations."""

        recommendations = []

        if resistance_rate > 75:
            recommendations.append("🔴 **URGENT ACTION REQUIRED:**")
            recommendations.append("• Declare public health emergency")
            recommendations.append("• Implement strict infection prevention")
            recommendations.append("• Restrict use of affected antibiotics")
            recommendations.append("• Activate rapid response team")

        elif resistance_rate > 50:
            recommendations.append("🟠 **HIGH PRIORITY:**")
            recommendations.append("• Establish antimicrobial stewardship immediately")
            recommendations.append("• Audit infection prevention practices")
            recommendations.append("• Implement antibiotic use restrictions")
            recommendations.append("• Increase surveillance frequency")

        else:
            recommendations.append("🟡 **STANDARD ACTIONS:**")
            recommendations.append("• Continue regular surveillance")
            recommendations.append("• Maintain infection prevention practices")

        recommendations.extend([
            "",
            "✅ **Universal Recommendations:**",
            "• Use local resistance data for empirical therapy",
            "• Implement rapid diagnostics",
            "• Focus on source control and WASH",
            "• Regular staff training on antibiotic stewardship",
            "• Public education on appropriate antibiotic use",
        ])

        return "\n".join(recommendations)

    def _explain_amr_concepts(self, query_lower) -> str:
        """Explain AMR concepts."""

        if 'mechanism' in query_lower or 'how does' in query_lower:
            return """**How Antibiotic Resistance Develops:**

1. **Natural Selection**: Antibiotics kill susceptible bacteria, resistant strains multiply
2. **Mutations**: Spontaneous DNA changes create resistance
3. **Gene Transfer**: Bacteria share resistance through plasmids and other mechanisms
4. **Key Mechanisms:**
   - Beta-lactamase: Enzymes that destroy antibiotics
   - Target modification: Bacteria alter antibiotic binding sites
   - Efflux pumps: Active transport removes antibiotics
   - Metabolic bypass: Alternative pathways bypass inhibition

**In Ghana:** Limited diagnostics -> prolonged antibiotics -> increased resistance selection"""

        else:
            return """**What is Antibiotic Resistance?**

When microbes survive antibiotics that normally kill them.

**Why It Matters:**
- Treatment failures increase
- Hospital stays longer
- Mortality increases
- Costs increase
- Limited treatment options

**Main Drivers:**
- Overuse of antibiotics
- Poor infection prevention
- Weak diagnostic capacity
- Limited stewardship programs
- Contaminated water/food"""

    def _assess_risks(self, resistance_rate) -> str:
        """Assess public health risks."""

        if resistance_rate > 75:
            level = "CRITICAL RISK"
            action = "Immediate intervention required"
        elif resistance_rate > 50:
            level = "HIGH RISK"
            action = "Urgent action needed"
        elif resistance_rate > 30:
            level = "MODERATE RISK"
            action = "Active surveillance and intervention"
        else:
            level = "LOW RISK"
            action = "Continue current practices"

        return f"""**Risk Assessment:** {level}

Resistance rate: {resistance_rate:.1f}%

**Implications:**
- {action}
- Treatment failures likely
- Monitor closely
- Implement prevention measures
- Use data to guide decisions"""

    def _intelligent_fallback(self, user_query, stats, resistance_rate) -> str:
        """Intelligent response for unrecognized queries."""

        return f"""I understand you're asking: "{user_query[:50]}..."

**What I can help with:**

**Data Analysis:**
- Overall resistance patterns
- Top organisms and antibiotics
- Geographic distribution
- Temporal trends

**Expert Guidance:**
- Evidence-based recommendations
- Infection prevention strategies
- Antimicrobial stewardship
- Clinical decision support

**Education:**
- How resistance develops
- Why it matters
- What to do about it

**Your Current Data:**
- Resistance rate: {resistance_rate:.1f}%
- Tests: {stats.get('total_tests', 0):,}
- Overall status: {"CRITICAL" if resistance_rate > 75 else "HIGH" if resistance_rate > 50 else "MODERATE" if resistance_rate > 30 else "CONTROLLED"}

Try asking: "What should we do?" or "Explain how resistance develops\""""
