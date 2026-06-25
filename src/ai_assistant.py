"""
Enhanced AI Assistant for AMR Surveillance Dashboard
Provides intelligent reasoning beyond just the dataset.

Uses the Claude API (Anthropic) when an ANTHROPIC_API_KEY is configured, and
falls back to a rich local rule-based reasoner when it is not.
"""

import os
import json
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

    def get_response(self, user_query: str, all_ast: pd.DataFrame, all_samples: pd.DataFrame, history=None) -> str:
        """Get an AI-generated response.

        history: optional list of {"role": "user"|"assistant", "content": str}
        prior turns, enabling a real multi-turn conversation.
        """

        # Try Claude if a key is configured
        if self.anthropic_available:
            try:
                return self._get_anthropic_response(user_query, all_ast, all_samples, history)
            except Exception:
                # Any API/network/parsing error -> graceful local fallback.
                pass

        # Fall back to advanced local reasoning (single-turn)
        return self._get_local_response(user_query, all_ast, all_samples)

    def _build_data_context(self, all_ast: pd.DataFrame, all_samples: pd.DataFrame) -> str:
        """Build a rich text summary of the dataset for the model to reason over."""

        if all_ast is None or all_ast.empty:
            return ("No dataset is currently loaded. Answer from general AMR "
                    "expertise and invite the user to select a dataset in the "
                    "Data Management page for data-specific analysis.")

        ast = all_ast
        samples = all_samples if all_samples is not None else pd.DataFrame()
        lines = []

        def pct_r(df):
            return (df['result'] == 'R').mean() * 100 if len(df) and 'result' in df.columns else 0.0

        # Overview
        lines.append(
            f"OVERVIEW: {len(samples):,} samples, "
            f"{ast['isolate_id'].nunique() if 'isolate_id' in ast.columns else 0:,} isolates, "
            f"{len(ast):,} AST results, "
            f"{ast['organism'].nunique() if 'organism' in ast.columns else 0} organism types, "
            f"{ast['antibiotic'].nunique() if 'antibiotic' in ast.columns else 0} antibiotics."
        )

        # Date range
        for cand, df in (('collection_date', samples), ('test_date', ast)):
            if cand in getattr(df, 'columns', []):
                dts = pd.to_datetime(df[cand], errors='coerce').dropna()
                if len(dts):
                    lines.append(f"DATE RANGE: {dts.min():%Y-%m-%d} to {dts.max():%Y-%m-%d}.")
                    break

        # Overall S/I/R
        if 'result' in ast.columns:
            vc = ast['result'].value_counts()
            tot = len(ast)
            lines.append(
                f"OVERALL SUSCEPTIBILITY: R {vc.get('R', 0) / tot * 100:.1f}%, "
                f"I {vc.get('I', 0) / tot * 100:.1f}%, "
                f"S {vc.get('S', 0) / tot * 100:.1f}% (n={tot:,})."
            )

        # Top organisms with %R
        if 'organism' in ast.columns:
            lines.append("TOP ORGANISMS (tests, %R):")
            for org, cnt in ast['organism'].value_counts().head(8).items():
                lines.append(f"  - {org}: {cnt} tests, {pct_r(ast[ast['organism'] == org]):.0f}% R")

        # Antibiotics ranked by resistance
        if 'antibiotic' in ast.columns:
            rows = []
            for abx, cnt in ast['antibiotic'].value_counts().items():
                if cnt >= 3:
                    rows.append((abx, cnt, pct_r(ast[ast['antibiotic'] == abx])))
            if rows:
                worst = sorted(rows, key=lambda r: r[2], reverse=True)[:8]
                best = sorted(rows, key=lambda r: r[2])[:5]
                lines.append("HIGHEST-RESISTANCE ANTIBIOTICS (avoid empirically):")
                lines += [f"  - {abx}: {r:.0f}% R (n={cnt})" for abx, cnt, r in worst]
                lines.append("LOWEST-RESISTANCE ANTIBIOTICS (likely still effective):")
                lines += [f"  - {abx}: {r:.0f}% R (n={cnt})" for abx, cnt, r in best]

        # Resistance by source category and region (need a sample_id join)
        if not samples.empty and 'sample_id' in samples.columns and 'sample_id' in ast.columns:
            for col, label in (('source_category', 'SOURCE CATEGORY'), ('region', 'REGION')):
                if col in samples.columns:
                    merged = ast.merge(
                        samples[['sample_id', col]].drop_duplicates('sample_id'),
                        on='sample_id', how='left',
                    )
                    groups = merged[col].value_counts().head(6)
                    if len(groups):
                        lines.append(f"RESISTANCE BY {label}:")
                        for val, cnt in groups.items():
                            lines.append(f"  - {val}: {pct_r(merged[merged[col] == val]):.0f}% R (n={cnt})")

        # Multi-drug resistance (isolate resistant to >=3 antibiotics)
        if 'isolate_id' in ast.columns and 'result' in ast.columns:
            r_counts = ast[ast['result'] == 'R'].groupby('isolate_id').size()
            total_iso = ast['isolate_id'].nunique()
            if total_iso:
                mdr = int((r_counts >= 3).sum())
                lines.append(
                    f"MULTI-DRUG RESISTANCE: {mdr} of {total_iso} isolates resistant "
                    f"to >=3 antibiotics ({mdr / total_iso * 100:.0f}%)."
                )

        return "\n".join(lines)

    # Fields that can be filtered / grouped (sample attributes are merged onto AST rows).
    _FILTER_FIELDS = [
        "organism", "antibiotic", "region", "district",
        "source_category", "source_type", "site_type", "lab_name",
    ]

    def _tool_definitions(self):
        """Curated, typed tools the model can call to query the live dataset."""
        return [
            {
                "name": "list_dataset_values",
                "description": "List the distinct values present in the dataset for a field "
                               "(e.g. every organism name, antibiotic, or region). Call this "
                               "first to get the exact spelling/casing before filtering.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string", "enum": self._FILTER_FIELDS},
                    },
                    "required": ["field"],
                },
            },
            {
                "name": "query_resistance",
                "description": "Compute susceptibility (n and %R/%I/%S) over the dataset with optional "
                               "filters and an optional group-by. Use for 'ciprofloxacin resistance in "
                               "E. coli', 'resistance by region', 'food vs environment for ceftriaxone'. "
                               "Filters are optional and combine with AND. group_by also covers "
                               "comparisons (by organism, antibiotic, lab_name, region, etc.).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "organism": {"type": "string"},
                        "antibiotic": {"type": "string"},
                        "region": {"type": "string"},
                        "district": {"type": "string"},
                        "source_category": {"type": "string", "description": "e.g. FOOD or ENVIRONMENT"},
                        "source_type": {"type": "string"},
                        "lab_name": {"type": "string"},
                        "date_from": {"type": "string", "description": "YYYY-MM-DD lower bound on test_date"},
                        "date_to": {"type": "string", "description": "YYYY-MM-DD upper bound on test_date"},
                        "group_by": {"type": "string", "enum": self._FILTER_FIELDS,
                                     "description": "Optional: break results down by this field."},
                    },
                },
            },
            {
                "name": "get_antibiogram",
                "description": "Cumulative antibiogram: for an organism, the %susceptible and tested "
                               "count (n) per antibiotic. Use for 'antibiogram for Klebsiella' or "
                               "'which drugs work against E. coli'.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "organism": {"type": "string",
                                     "description": "Organism name. Omit for an overview across organisms."},
                    },
                },
            },
            {
                "name": "detect_resistance_phenotypes",
                "description": "Run special phenotype detection across the dataset: ESBL, CRE "
                               "(carbapenemase), MRSA, AmpC, or MDR (resistant to >=3 antibiotics). "
                               "Returns counts and example isolates.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "phenotype": {"type": "string", "enum": ["ESBL", "CRE", "MRSA", "AmpC", "MDR"]},
                    },
                    "required": ["phenotype"],
                },
            },
            {
                "name": "get_resistance_trend",
                "description": "Resistance (%R) over time, aggregated by month/quarter/year, optionally "
                               "filtered to an organism and/or antibiotic. Returns the series plus a "
                               "trend direction.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "organism": {"type": "string"},
                        "antibiotic": {"type": "string"},
                        "aggregation": {"type": "string", "enum": ["monthly", "quarterly", "yearly"]},
                    },
                },
            },
        ]

    def _merge_frames(self, all_ast, all_samples):
        """AST rows with sample attributes merged on, plus a normalised _date column."""
        if all_ast is None or all_ast.empty:
            return pd.DataFrame()
        ast = all_ast
        samples = all_samples if all_samples is not None else pd.DataFrame()
        sample_cols = [c for c in ["sample_id", "region", "district", "source_category",
                                   "source_type", "site_type", "lab_name", "collection_date"]
                       if c in getattr(samples, "columns", [])]
        if not samples.empty and "sample_id" in ast.columns and "sample_id" in sample_cols:
            merged = ast.merge(samples[sample_cols].drop_duplicates("sample_id"),
                               on="sample_id", how="left")
        else:
            merged = ast.copy()
        for cand in ("test_date", "collection_date"):
            if cand in merged.columns:
                merged["_date"] = pd.to_datetime(merged[cand], errors="coerce")
                break
        return merged

    @staticmethod
    def _sir(df):
        n = len(df)
        if n == 0 or "result" not in df.columns:
            return {"n": 0}
        r = int((df["result"] == "R").sum())
        i = int((df["result"] == "I").sum())
        s = int((df["result"] == "S").sum())
        return {"n": n, "R": r, "I": i, "S": s,
                "pct_R": round(r / n * 100, 1), "pct_I": round(i / n * 100, 1),
                "pct_S": round(s / n * 100, 1)}

    def _apply_filters(self, df, ti):
        out = df
        for f in self._FILTER_FIELDS:
            v = ti.get(f)
            if v and f in out.columns:
                out = out[out[f].astype(str).str.lower() == str(v).strip().lower()]
        for bound, op in (("date_from", "ge"), ("date_to", "le")):
            raw = ti.get(bound)
            if raw and "_date" in out.columns:
                dt = pd.to_datetime(raw, errors="coerce")
                if pd.notna(dt):
                    out = out[out["_date"] >= dt] if op == "ge" else out[out["_date"] <= dt]
        return out

    def _run_tool(self, name, ti, merged):
        """Execute one tool call against the dataset and return a string result."""
        try:
            if merged is None or merged.empty:
                return "No data is loaded for the selected dataset."

            if name == "list_dataset_values":
                field = ti.get("field")
                if field not in merged.columns:
                    return f"Field '{field}' is not available in this dataset."
                vals = sorted(merged[field].dropna().astype(str).unique().tolist())
                return json.dumps({"field": field, "count": len(vals), "values": vals[:200]})

            if name == "query_resistance":
                df = self._apply_filters(merged, ti)
                result = {"filters": {k: v for k, v in ti.items() if v and k != "group_by"},
                          "overall": self._sir(df)}
                gb = ti.get("group_by")
                if gb and gb in df.columns and len(df):
                    groups = []
                    for val, sub in df.groupby(df[gb].astype(str)):
                        st = self._sir(sub)
                        st["value"] = val
                        groups.append(st)
                    result["group_by"] = gb
                    result["groups"] = sorted(groups, key=lambda g: g["n"], reverse=True)[:25]
                return json.dumps(result, default=str)

            if name == "get_antibiogram":
                org = ti.get("organism")
                df = merged
                if org and "organism" in df.columns:
                    df = df[df["organism"].astype(str).str.lower() == str(org).strip().lower()]
                if df.empty or "antibiotic" not in df.columns:
                    return json.dumps({"organism": org, "note": "No matching records."})
                rows = []
                for abx, sub in df.groupby("antibiotic"):
                    st = self._sir(sub)
                    rows.append({"antibiotic": abx, "n": st["n"],
                                 "pct_S": st.get("pct_S"), "pct_R": st.get("pct_R")})
                rows = sorted(rows, key=lambda r: r["n"], reverse=True)[:40]
                return json.dumps({"organism": org or "all", "antibiogram": rows,
                                   "note": "Interpret %S cautiously where n<30 (CLSI M39 minimum)."},
                                  default=str)

            if name == "detect_resistance_phenotypes":
                ph = ti.get("phenotype")
                fnmap = {
                    "ESBL": analytics.detect_esbl_patterns,
                    "CRE": analytics.detect_carbapenemase_patterns,
                    "MRSA": analytics.detect_mrsa_patterns,
                    "AmpC": analytics.detect_ampc_patterns,
                }
                if ph == "MDR":
                    df = analytics.get_multiple_resistance_patterns(merged, min_resistances=3)
                elif ph in fnmap:
                    df = fnmap[ph](merged)
                else:
                    return f"Unknown phenotype: {ph}"
                if df is None or len(df) == 0:
                    return json.dumps({"phenotype": ph, "count": 0, "examples": []})
                return json.dumps({"phenotype": ph, "count": int(len(df)),
                                   "examples": df.head(10).to_dict("records")}, default=str)

            if name == "get_resistance_trend":
                df = merged
                if ti.get("organism") and "organism" in df.columns:
                    df = df[df["organism"].astype(str).str.lower() == str(ti["organism"]).strip().lower()]
                if ti.get("antibiotic") and "antibiotic" in df.columns:
                    df = df[df["antibiotic"].astype(str).str.lower() == str(ti["antibiotic"]).strip().lower()]
                if df.empty or "_date" not in df.columns:
                    return json.dumps({"note": "No dated records for this filter."})
                d = df.dropna(subset=["_date"])
                if d.empty:
                    return json.dumps({"note": "No valid test dates for this filter."})
                freq = {"monthly": "M", "quarterly": "Q", "yearly": "Y"}.get(ti.get("aggregation"), "M")
                d = d.assign(period=d["_date"].dt.to_period(freq).astype(str))
                series = []
                for per, sub in d.groupby("period"):
                    st = self._sir(sub)
                    series.append({"period": per, "pct_R": st.get("pct_R"), "n": st["n"]})
                series = sorted(series, key=lambda x: x["period"])
                return json.dumps({"aggregation": ti.get("aggregation", "monthly"), "series": series,
                                   "direction": analytics.calculate_trend_direction(df)}, default=str)

            return f"Unknown tool: {name}"
        except Exception as e:
            return f"Tool error while running {name}: {e}"

    def _get_anthropic_response(self, user_query: str, all_ast: pd.DataFrame, all_samples: pd.DataFrame, history=None) -> str:
        """Get response from Claude, grounded in the dataset summary and live data tools."""

        context = self._build_data_context(all_ast, all_samples)
        merged = self._merge_frames(all_ast, all_samples)
        has_data = not merged.empty
        tools = self._tool_definitions() if has_data else []

        system_prompt = f"""You are an expert antimicrobial resistance (AMR) epidemiologist and public-health adviser embedded in a Ghana One Health surveillance dashboard covering environmental, food, and clinical samples.

You are given a summary of the user's CURRENTLY SELECTED dataset. Cite the actual organisms, %R figures, antibiotics and regions rather than speaking generically.

=== DATASET SUMMARY ===
{context}
=== END SUMMARY ===

You also have TOOLS to query the live dataset directly: susceptibility by any filter (query_resistance), antibiograms (get_antibiogram), resistance phenotypes — ESBL/CRE/MRSA/AmpC/MDR (detect_resistance_phenotypes), and time trends (get_resistance_trend), plus list_dataset_values to discover exact value spellings.

How to respond:
- If the summary already answers the question, answer directly. If it does NOT, CALL A TOOL to compute the answer — do not guess and do not say "the data doesn't cover that" without checking with a tool first.
- Use list_dataset_values when unsure of the exact organism/antibiotic/region spelling before filtering.
- Base every quantitative claim on the summary or a tool result; never invent numbers. Flag when a sample size is too small (n<30) to be reliable.
- Lead with a direct, scannable answer (short paragraphs, bullets, **bold** key numbers). Bring in Ghana / WHO GLASS / One Health context where useful, and offer 1-2 specific follow-up questions.
- You are a decision-support aid, not a substitute for clinical judgement or confirmatory testing."""

        messages = []
        for turn in (history or []):
            role = turn.get("role")
            content = turn.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_query})

        # Agentic loop: let Claude call tools until it has what it needs to answer.
        response = None
        for _ in range(8):
            kwargs = dict(
                model=self.model,
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=system_prompt,
                messages=messages,
            )
            if tools:
                kwargs["tools"] = tools
            response = self.client.messages.create(**kwargs)

            if response.stop_reason == "tool_use":
                # Preserve the full assistant turn (thinking + tool_use blocks) verbatim.
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if getattr(block, "type", None) == "tool_use":
                        out = self._run_tool(block.name, block.input or {}, merged)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": out,
                        })
                messages.append({"role": "user", "content": tool_results})
                continue

            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue

            break  # end_turn or terminal stop reason

        # If we exhausted the loop still wanting tools, force a final no-tools answer.
        if response is not None and response.stop_reason == "tool_use":
            response = self.client.messages.create(
                model=self.model, max_tokens=4096, thinking={"type": "adaptive"},
                system=system_prompt, messages=messages,
            )

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
