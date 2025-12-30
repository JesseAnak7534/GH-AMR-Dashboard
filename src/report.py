"""
Report generation module for AMR Surveillance Dashboard.
Generates HTML reports for download with comprehensive charts and visualizations.
"""
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
import base64
import json
import plotly
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from src import analytics
from src import plots


def generate_chart_description(chart_type: str, data_stats: Dict) -> str:
    """Generate dynamic, data-driven descriptions for charts in reported speech."""
    descriptions = {
        'overall_resistance': f"""The overall antimicrobial resistance distribution reveals that approximately {data_stats.get('resistant_pct', 0):.1f}% of tested isolates demonstrated resistance to the antimicrobials tested. Susceptible isolates comprised {data_stats.get('susceptible_pct', 0):.1f}% of the population, while intermediate resistance was observed in {data_stats.get('intermediate_pct', 0):.1f}% of cases. This distribution pattern indicates {data_stats.get('interpretation', 'a moderate level of resistance')} within the tested population.""",
        
        'organism_resistance': f"""Analysis of the top ten organisms by resistance profile demonstrates that {data_stats.get('highest_organism', 'the leading organism')} exhibited the highest resistance rate at {data_stats.get('highest_resistance', 0):.1f}%, followed by {data_stats.get('second_organism', 'other isolates')} at {data_stats.get('second_resistance', 0):.1f}%. These organisms collectively accounted for {data_stats.get('top_org_percentage', 0):.1f}% of all tested isolates. The stacked bar representation clearly delineates susceptible, intermediate, and resistant categories for each organism.""",
        
        'antibiotic_resistance': f"""The analysis of antimicrobial resistance among the top twelve antibiotics reveals that {data_stats.get('highest_antibiotic', 'one compound')} demonstrated the highest resistance rate at {data_stats.get('highest_ab_resistance', 0):.1f}%, while {data_stats.get('lowest_antibiotic', 'another agent')} showed the lowest resistance at {data_stats.get('lowest_ab_resistance', 0):.1f}%. This variation across antimicrobial classes suggests {data_stats.get('ab_interpretation', 'differential antibiotic usage patterns and resistance mechanisms')} within the surveyed population.""",
        
        'source_category_resistance': f"""Resistance patterns across different source categories indicate that {data_stats.get('highest_source', 'a particular source category')} exhibited the highest resistance rate at {data_stats.get('highest_source_resistance', 0):.1f}%, whereas {data_stats.get('lowest_source', 'another category')} demonstrated lower resistance at {data_stats.get('lowest_source_resistance', 0):.1f}%. These differences highlight {data_stats.get('source_interpretation', 'varying contamination pressures and antibiotic use patterns')} across different sample origins.""",
        
        'source_type_distribution': f"""The sample distribution by source type shows that {data_stats.get('primary_source', 'a dominant source type')} comprised {data_stats.get('primary_percentage', 0):.1f}% of all samples, representing {data_stats.get('primary_count', 0)} isolates. {data_stats.get('secondary_source', 'The secondary source')} accounted for {data_stats.get('secondary_percentage', 0):.1f}%, while remaining sources collectively represented {data_stats.get('other_percentage', 0):.1f}%. This distribution reflects {data_stats.get('source_type_interpretation', 'the sampling strategy and epidemiological importance of different compartments')}.
""",
        
        'district_hotspots': f"""Geographic analysis identified {data_stats.get('highest_district', 'a particular district')} as the resistance hotspot with {data_stats.get('highest_district_resistance', 0):.1f}% resistance rate among its {data_stats.get('highest_district_tests', 0)} samples. {data_stats.get('second_district', 'Another district')} followed closely with {data_stats.get('second_district_resistance', 0):.1f}% resistance. These geographic variations suggest {data_stats.get('geographic_interpretation', 'localized transmission hotspots or regional differences in antimicrobial selection pressure')}.""",
        
        'heatmap_matrix': f"""The organism-antibiotic resistance matrix reveals critical patterns: {data_stats.get('critical_finding', 'certain organism-antibiotic combinations exhibit notably high resistance rates')}, while other combinations show lower prevalence. The most concerning interaction is between {data_stats.get('highest_concern_organism', 'an organism')} and {data_stats.get('highest_concern_ab', 'an antimicrobial')}, which demonstrated {data_stats.get('highest_interaction_resistance', 0):.1f}% resistance. This pattern indicates {data_stats.get('heatmap_interpretation', 'specific resistance mechanisms or selective pressures favoring particular pathogen-drug combinations')}.
"""
    }
    return descriptions.get(chart_type, "")


def generate_ai_insights(samples_df: pd.DataFrame, ast_df: pd.DataFrame, top_districts: Optional[pd.DataFrame] = None) -> Dict:
    """Generate AI-powered insights and recommendations based on data analysis."""
    insights = {
        'summary': "",
        'key_findings': [],
        'risk_assessment': "",
        'recommendations': [],
        'emerging_concerns': []
    }
    
    if ast_df.empty:
        return insights
    
    # Calculate key metrics
    overall_resistance = (ast_df['result'] == 'R').sum() / len(ast_df) * 100
    susceptible_pct = (ast_df['result'] == 'S').sum() / len(ast_df) * 100
    intermediate_pct = (ast_df['result'] == 'I').sum() / len(ast_df) * 100
    
    # Identify high-resistance organisms
    organism_resistance = ast_df.groupby('organism')['result'].apply(lambda x: (x == 'R').sum() / len(x) * 100).sort_values(ascending=False)
    
    # Identify high-resistance antibiotics
    antibiotic_resistance = ast_df.groupby('antibiotic')['result'].apply(lambda x: (x == 'R').sum() / len(x) * 100).sort_values(ascending=False)
    
    # Summary
    if overall_resistance > 40:
        risk_level = "HIGH"
        insight = "This dataset demonstrates concerning levels of antimicrobial resistance, exceeding 40%. Immediate public health interventions are recommended."
    elif overall_resistance > 20:
        risk_level = "MODERATE"
        insight = "Moderate antimicrobial resistance levels (20-40%) are observed, suggesting the need for enhanced surveillance and infection control measures."
    else:
        risk_level = "LOW"
        insight = "Antimicrobial resistance levels remain below 20%, indicating relatively controlled resistance patterns, though continued surveillance is essential."
    
    insights['summary'] = f"Overall antimicrobial resistance rate: {overall_resistance:.1f}% ({risk_level} RISK). {insight}"
    
    # Key findings
    if len(organism_resistance) > 0:
        top_org = organism_resistance.index[0]
        top_org_res = organism_resistance.iloc[0]
        insights['key_findings'].append(f"'{top_org}' exhibits the highest resistance rate at {top_org_res:.1f}%")
    
    if len(antibiotic_resistance) > 0:
        top_ab = antibiotic_resistance.index[0]
        top_ab_res = antibiotic_resistance.iloc[0]
        insights['key_findings'].append(f"'{top_ab}' shows the highest resistance frequency at {top_ab_res:.1f}%")
    
    insights['key_findings'].append(f"Susceptibility rate: {susceptible_pct:.1f}% | Intermediate resistance: {intermediate_pct:.1f}%")
    
    # Risk assessment
    if overall_resistance > 30:
        insights['risk_assessment'] = f"ALERT: Resistance rate of {overall_resistance:.1f}% suggests significant public health concern. Priority should be given to epidemiological investigation and control measures."
    elif overall_resistance > 15:
        insights['risk_assessment'] = f"CAUTION: Resistance rate of {overall_resistance:.1f}% warrants enhanced monitoring and implementation of antimicrobial stewardship programs."
    else:
        insights['risk_assessment'] = f"Resistance rate of {overall_resistance:.1f}% is manageable but requires continued surveillance to prevent escalation."
    
    # Recommendations based on data
    if overall_resistance > 30:
        insights['recommendations'].append("Implement strict infection control protocols immediately")
        insights['recommendations'].append("Conduct epidemiological investigation of resistance hotspots")
        insights['recommendations'].append("Launch antimicrobial stewardship program targeting high-resistance organisms")
    
    if len(organism_resistance) > 0 and organism_resistance.iloc[0] > 50:
        top_org = organism_resistance.index[0]
        insights['recommendations'].append(f"Develop targeted interventions for {top_org} resistance")
    
    if len(antibiotic_resistance) > 0 and antibiotic_resistance.iloc[0] > 40:
        top_ab = antibiotic_resistance.index[0]
        insights['recommendations'].append(f"Consider restricting non-essential use of {top_ab}")
    
    insights['recommendations'].append("Strengthen laboratory quality assurance and standardized testing")
    insights['recommendations'].append("Enhance data collection completeness and timeliness")
    
    # Emerging concerns
    if not samples_df.empty and 'date_received' in samples_df.columns:
        try:
            # Identify recent trends
            recent_samples = samples_df.tail(int(len(samples_df) * 0.2))
            if not recent_samples.empty:
                insights['emerging_concerns'].append("Trend analysis: Monitor recent samples for emerging resistance patterns")
        except:
            pass
    
    if overall_resistance > susceptible_pct:
        insights['emerging_concerns'].append("Resistant isolates now exceed susceptible isolates - critical threshold crossed")
    
    if len(organism_resistance) > 0 and organism_resistance.iloc[0] > 60:
        insights['emerging_concerns'].append(f"Presence of high-resistance organisms ({organism_resistance.index[0]}) suggests potential outbreak risk")
    
    return insights


def generate_html_report(
    dataset_name: str,
    samples_df: pd.DataFrame,
    ast_df: pd.DataFrame
) -> str:
    """Generate comprehensive HTML report with embedded charts and visualizations covering all dashboard parameters."""

    if ast_df.empty or samples_df.empty:
        return "<html><body><h1>No data available for report generation.</h1></body></html>"

    # Import required modules
    from src import analytics

    # Calculate comprehensive statistics
    total_samples = len(samples_df)
    total_tests = len(ast_df)
    total_organisms = ast_df['organism'].nunique()
    total_antibiotics = ast_df['antibiotic'].nunique()

    # Overall resistance statistics
    overall_resistance = (ast_df['result'] == 'R').sum() / len(ast_df) * 100
    susceptible_rate = (ast_df['result'] == 'S').sum() / len(ast_df) * 100
    intermediate_rate = (ast_df['result'] == 'I').sum() / len(ast_df) * 100

    # Advanced analytics data
    resistance_stats = analytics.calculate_resistance_statistics(ast_df)
    trend_analysis = analytics.calculate_trend_direction(ast_df)
    emerging_patterns = analytics.identify_emerging_resistance(ast_df, samples_df)
    data_quality = analytics.assess_data_quality(samples_df, ast_df)
    resistance_burden = analytics.calculate_resistance_burden(samples_df, ast_df)
    kpis = analytics.calculate_kpis(samples_df, ast_df)

    # Risk assessment data
    high_risk_organisms = analytics.get_high_risk_organisms(ast_df, 50)  # Resistance rate threshold 50%

    # Resistance by various categories
    organism_resistance = ast_df.groupby('organism').agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    organism_resistance.columns = ['organism', 'total_tests', 'resistant_count']
    organism_resistance['resistance_rate'] = (organism_resistance['resistant_count'] / organism_resistance['total_tests'] * 100).round(1)
    organism_resistance = organism_resistance.sort_values('resistance_rate', ascending=False)

    antibiotic_resistance = ast_df.groupby('antibiotic').agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    antibiotic_resistance.columns = ['antibiotic', 'total_tests', 'resistant_count']
    antibiotic_resistance['resistance_rate'] = (antibiotic_resistance['resistant_count'] / antibiotic_resistance['total_tests'] * 100).round(1)
    antibiotic_resistance = antibiotic_resistance.sort_values('resistance_rate', ascending=False)

    # Regional analysis
    region_resistance = ast_df.merge(samples_df[['sample_id', 'region']], on='sample_id', how='left')
    region_resistance = region_resistance.groupby('region').agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    region_resistance.columns = ['region', 'total_tests', 'resistant_count']
    region_resistance['resistance_rate'] = (region_resistance['resistant_count'] / region_resistance['total_tests'] * 100).round(1)
    region_resistance = region_resistance.sort_values('resistance_rate', ascending=False)

    # Source category analysis
    source_resistance = ast_df.merge(samples_df[['sample_id', 'source_category']], on='sample_id', how='left')
    source_resistance = source_resistance.groupby('source_category').agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    source_resistance.columns = ['source_category', 'total_tests', 'resistant_count']
    source_resistance['resistance_rate'] = (source_resistance['resistant_count'] / source_resistance['total_tests'] * 100).round(1)
    source_resistance = source_resistance.sort_values('resistance_rate', ascending=False)

    # MDR Analysis
    mdr_data = plots.detect_mdr_isolates(ast_df)
    mdr_count = len(mdr_data) if not mdr_data.empty else 0

    # Resistance mechanisms and patterns
    mechanisms_df = analytics.detect_resistance_mechanisms(ast_df)
    cross_resistance_df = analytics.detect_cross_resistance(ast_df)
    mdr_patterns_df = analytics.get_multiple_resistance_patterns(ast_df)

    # Create comprehensive charts
    # 1. Overall resistance pie chart
    overall_fig = go.Figure(data=[go.Pie(
        labels=['Resistant', 'Susceptible', 'Intermediate'],
        values=[overall_resistance, susceptible_rate, intermediate_rate],
        marker_colors=['#e74c3c', '#27ae60', '#f39c12']
    )])
    overall_fig.update_layout(title='Overall Resistance Distribution')
    overall_chart = overall_fig.to_html(full_html=False, include_plotlyjs='cdn')

    # 2. Organism resistance bar chart (top 10)
    top_organisms = organism_resistance.head(10)
    organism_fig = go.Figure()
    organism_fig.add_trace(go.Bar(
        x=top_organisms['organism'],
        y=top_organisms['resistance_rate'],
        marker_color='#3498db'
    ))
    organism_fig.update_layout(
        title='Resistance by Organism (Top 10)',
        xaxis_title='Organism',
        yaxis_title='Resistance Rate (%)'
    )
    organism_chart = organism_fig.to_html(full_html=False, include_plotlyjs=False)

    # 3. Antibiotic resistance bar chart (top 10)
    top_antibiotics = antibiotic_resistance.head(10)
    antibiotic_fig = go.Figure()
    antibiotic_fig.add_trace(go.Bar(
        x=top_antibiotics['antibiotic'],
        y=top_antibiotics['resistance_rate'],
        marker_color='#e67e22'
    ))
    antibiotic_fig.update_layout(
        title='Resistance by Antibiotic (Top 10)',
        xaxis_title='Antibiotic',
        yaxis_title='Resistance Rate (%)'
    )
    antibiotic_chart = antibiotic_fig.to_html(full_html=False, include_plotlyjs=False)

    # 4. Regional resistance chart
    region_fig = go.Figure()
    region_fig.add_trace(go.Bar(
        x=region_resistance['region'].head(10),
        y=region_resistance['resistance_rate'].head(10),
        marker_color='#9b59b6'
    ))
    region_fig.update_layout(
        title='Resistance by Region (Top 10)',
        xaxis_title='Region',
        yaxis_title='Resistance Rate (%)'
    )
    region_chart = region_fig.to_html(full_html=False, include_plotlyjs=False)

    # 5. Source category resistance chart
    source_fig = go.Figure()
    source_fig.add_trace(go.Bar(
        x=source_resistance['source_category'],
        y=source_resistance['resistance_rate'],
        marker_color='#1abc9c'
    ))
    source_fig.update_layout(
        title='Resistance by Source Category',
        xaxis_title='Source Category',
        yaxis_title='Resistance Rate (%)'
    )
    source_chart = source_fig.to_html(full_html=False, include_plotlyjs=False)

    # 6. MDR distribution chart
    if not mdr_data.empty:
        mdr_counts = mdr_data['resistant_drug_classes'].value_counts().sort_index()
        mdr_fig = go.Figure()
        mdr_fig.add_trace(go.Bar(
            x=mdr_counts.index,
            y=mdr_counts.values,
            marker_color='#e74c3c',
            name='MDR Isolates'
        ))
        mdr_fig.update_layout(
            title='Multi-Drug Resistant Isolates by Drug Class Count',
            xaxis_title='Number of Resistant Drug Classes',
            yaxis_title='Number of Isolates'
        )
        mdr_chart = mdr_fig.to_html(full_html=False, include_plotlyjs=False)
    else:
        mdr_chart = "<p>No multi-drug resistant isolates detected</p>"

    # Generate comprehensive HTML report
    html_report = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Comprehensive AMR Surveillance Report - {dataset_name}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f8f9fa;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
            font-weight: 300;
        }}
        .section {{
            background: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }}
        .section h2 {{
            margin-top: 0;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            border-left: 4px solid #667eea;
        }}
        .stat-number {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }}
        .stat-label {{
            color: #666;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .chart-container {{
            margin: 20px 0;
        }}
        .data-table {{
            margin: 20px 0;
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #f8f9fa;
            font-weight: 600;
            color: #333;
        }}
        tr:hover {{
            background-color: #f8f9fa;
        }}
        .risk-high {{ color: #e74c3c; font-weight: bold; }}
        .risk-medium {{ color: #f39c12; font-weight: bold; }}
        .risk-low {{ color: #27ae60; font-weight: bold; }}
        .alert-box {{
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
        }}
        .alert-critical {{ background: #ffeaea; border-left: 4px solid #e74c3c; }}
        .alert-warning {{ background: #fff5e6; border-left: 4px solid #f39c12; }}
        .alert-info {{ background: #e6f7ff; border-left: 4px solid #3498db; }}
        .footer {{
            text-align: center;
            color: #666;
            font-size: 0.9em;
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
        }}
        @media print {{
            body {{
                background: white;
                max-width: none;
                margin: 0;
                padding: 15px;
            }}
            .section {{
                box-shadow: none;
                border: 1px solid #ddd;
                margin-bottom: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🦠 Comprehensive Antimicrobial Resistance Surveillance Report</h1>
        <p><strong>Dataset:</strong> {dataset_name}</p>
        <p><strong>Analysis Date:</strong> {datetime.now().strftime('%B %d, %Y')}</p>
        <p><strong>Report Coverage:</strong> Resistance Overview, Trends, Advanced Analytics & Risk Assessment</p>
    </div>

    <!-- EXECUTIVE SUMMARY -->
    <div class="section">
        <h2>📊 Executive Summary</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{total_samples}</div>
                <div class="stat-label">Total Samples</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{total_tests}</div>
                <div class="stat-label">AST Tests</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{total_organisms}</div>
                <div class="stat-label">Organisms Identified</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{total_antibiotics}</div>
                <div class="stat-label">Antibiotics Tested</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{overall_resistance:.1f}%</div>
                <div class="stat-label">Overall Resistance</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{mdr_count}</div>
                <div class="stat-label">MDR Isolates</div>
            </div>
        </div>
    </div>

    <!-- RESISTANCE OVERVIEW -->
    <div class="section">
        <h2>🔬 Resistance Overview</h2>

        <h3>Overall Resistance Distribution</h3>
        <p><strong>Overview:</strong> The antimicrobial susceptibility testing revealed an overall resistance rate of <strong>{overall_resistance:.1f}%</strong> (n = {total_tests}). This represents the proportion of all tested isolates that demonstrated resistance to the antimicrobials tested. Susceptible isolates accounted for <strong>{susceptible_rate:.1f}%</strong> of all tests, while intermediate resistance was observed in <strong>{intermediate_rate:.1f}%</strong> of cases. The distribution pattern indicates the prevalence of resistance within the tested population and guides the need for targeted interventions.</p>
        <div class="chart-container">{overall_chart}</div>

        <h3>Resistance by Organism (Top 10)</h3>
        <p><strong>Interpretation:</strong> This chart identifies the 10 organisms with the highest resistance rates in your surveillance data. Each organism's resistance rate reflects the proportion of its isolates that demonstrated resistance across all tested antibiotics. Organisms appearing at the top of this list represent high-priority targets for infection prevention and antibiotic stewardship interventions. Clinical attention should focus on implementing appropriate treatment protocols and infection control measures for these problematic pathogens.</p>
        <div class="chart-container">{organism_chart}</div>

        <h3>Resistance by Antibiotic (Top 10)</h3>
        <p><strong>Interpretation:</strong> This visualization displays the 10 antibiotics against which the highest resistance rates were observed. Antibiotics with elevated resistance rates may have reduced clinical utility and should be used judiciously. The variation in resistance across different antimicrobials reflects differences in resistance mechanisms, selective pressure from antimicrobial usage, and intrinsic properties of the drugs themselves. Clinical guidelines should be adjusted based on these resistance patterns to optimize therapeutic outcomes.</p>
        <div class="chart-container">{antibiotic_chart}</div>

        <h3>Multi-Drug Resistance Analysis</h3>
        <p><strong>Context:</strong> <strong>{mdr_count}</strong> multi-drug resistant isolates were detected (defined as resistance to 3 or more drug classes). Multi-drug resistance severely limits therapeutic options and poses a significant public health threat. The distribution across different numbers of resistant drug classes helps identify patterns of co-resistance and guides selection of empiric therapy when susceptibility testing is not yet available.</p>
        <div class="chart-container">{mdr_chart}</div>

        <h3>Resistance Mechanisms Detected</h3>
        <p><strong>Significance:</strong> <strong>{len(mechanisms_df) if not mechanisms_df.empty else 0}</strong> distinct resistance mechanisms were identified across your isolates. Understanding the underlying resistance mechanisms provides insight into how resistance evolved and guides development of targeted interventions. Different mechanisms may require different control strategies—for example, plasmid-mediated resistance may be interrupted by horizontal gene transfer prevention measures, while chromosomal mutations may require different approaches.</p>
        {f'<div class="data-table"><table><thead><tr><th>Isolate ID</th><th>Organism</th><th>Mechanism</th><th>Confidence</th></tr></thead><tbody>' + ''.join([f"<tr><td>{row['isolate_id']}</td><td>{row['organism']}</td><td>{row['resistance_mechanism']}</td><td>{row['confidence']}</td></tr>" for _, row in mechanisms_df.head(10).iterrows()]) + '</tbody></table></div>' if not mechanisms_df.empty else '<p>No resistance mechanisms detected</p>'}
    </div>

    <!-- GEOGRAPHIC ANALYSIS -->
    <div class="section">
        <h2>🗺️ Geographic & Regional Analysis</h2>

        <h3>Resistance by Region</h3>
        <p><strong>Geographic Insight:</strong> Regional variation in resistance rates reflects differences in antimicrobial stewardship practices, infection control infrastructure, disease burden, and farming/clinical practices across geographic areas. Regions with elevated resistance rates may benefit from enhanced surveillance, targeted stewardship programs, and infection control reinforcement.</p>
        <div class="chart-container">{region_chart}</div>

        <h3>Resistance by Source Category</h3>
        <p><strong>One Health Perspective:</strong> Resistance patterns vary substantially across different source categories (environmental, food, human, animal), highlighting the interconnected nature of antimicrobial resistance across sectors. Each category may have distinct resistance profiles based on antimicrobial usage patterns and transmission routes within that sector. Understanding these patterns supports targeted, source-specific interventions aligned with One Health principles.</p>
        <div class="chart-container">{source_chart}</div>

        <div class="data-table">
            <h3>Regional Resistance Summary</h3>
            <table>
                <thead>
                    <tr><th>Region</th><th>Resistance Rate (%)</th><th>Total Tests</th><th>Resistant Isolates</th></tr>
                </thead>
                <tbody>
"""

    # Add regional data
    for _, row in region_resistance.head(10).iterrows():
        html_report += f"""
                    <tr>
                        <td>{row['region']}</td>
                        <td>{row['resistance_rate']}%</td>
                        <td>{int(row['total_tests'])}</td>
                        <td>{int(row['resistant_count'])}</td>
                    </tr>"""

    html_report += """
                </tbody>
            </table>
        </div>
    </div>

    <!-- TRENDS ANALYSIS -->
    <div class="section">
        <h2>📈 Trends Analysis</h2>

        <h3>Resistance Trend Direction</h3>
        <p><strong>Epidemiological Significance:</strong> Monitoring trends in antimicrobial resistance over time provides critical insights into whether resistance is increasing, decreasing, or remaining stable. An increasing trend suggests rising selective pressure from antimicrobial use or spread of resistant strains, warranting urgent intervention. Decreasing trends indicate successful stewardship or control measures.</p>
"""

    if trend_analysis:
        trend_direction = trend_analysis.get('trend', 'insufficient_data')
        risk_level = trend_analysis.get('risk_level', 'UNKNOWN')
        change_pct = trend_analysis.get('change_percentage', 0)

        if trend_direction == 'increasing':
            html_report += f'<div class="alert-box alert-critical">📈 <strong>INCREASING TREND DETECTED</strong> - Resistance increased by {change_pct:.2f}% (Risk: {risk_level}). Urgent intervention recommended.</div>'
        elif trend_direction == 'decreasing':
            html_report += f'<div class="alert-box alert-info">📉 <strong>DECREASING TREND DETECTED</strong> - Resistance decreased by {abs(change_pct):.2f}% (Risk: {risk_level}). Continue current interventions.</div>'
        else:
            html_report += f'<div class="alert-box alert-info">➡️ <strong>STABLE TREND</strong> - Resistance change: {change_pct:.2f}% (Risk: {risk_level}). Continued monitoring recommended.</div>'

    html_report += f"""
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{trend_analysis.get('first_half_resistance', 0):.1f}%</div>
                <div class="stat-label">Early Period</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{trend_analysis.get('second_half_resistance', 0):.1f}%</div>
                <div class="stat-label">Recent Period</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{change_pct:.2f}%</div>
                <div class="stat-label">Change</div>
            </div>
        </div>
    </div>

    <!-- ADVANCED ANALYTICS -->
    <div class="section">
        <h2>🔬 Advanced Analytics</h2>

        <h3>Comprehensive Statistics</h3>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{resistance_stats.get('resistance_rate', 0):.1f}%</div>
                <div class="stat-label">Resistance Rate</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{resistance_stats.get('total_tests', 0)}</div>
                <div class="stat-label">Total Tests</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{kpis.get('tests_per_sample', 0):.1f}</div>
                <div class="stat-label">Tests per Sample</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{kpis.get('organisms_identified', 0)}</div>
                <div class="stat-label">Organisms Identified</div>
            </div>
        </div>

        <h3>Data Quality Assessment</h3>
"""

    if data_quality:
        completeness = data_quality.get('completeness_score', 0)
        if completeness >= 90:
            html_report += f'<div class="alert-box alert-info">✅ <strong>High Quality Data</strong> - Completeness Score: {completeness:.1f}%</div>'
        elif completeness >= 70:
            html_report += f'<div class="alert-box alert-warning">⚠️ <strong>Moderate Quality Data</strong> - Completeness Score: {completeness:.1f}%</div>'
        else:
            html_report += f'<div class="alert-box alert-critical">🔴 <strong>Low Quality Data</strong> - Completeness Score: {completeness:.1f}%</div>'

        if data_quality.get('data_quality_issues'):
            html_report += '<h4>Data Quality Issues:</h4><ul>'
            for issue in data_quality['data_quality_issues']:
                html_report += f'<li>{issue}</li>'
            html_report += '</ul>'

    html_report += """
        <h3>Emerging Resistance Patterns</h3>
"""

    if emerging_patterns:
        html_report += f'<div class="alert-box alert-warning">🚨 <strong>{len(emerging_patterns)} emerging resistance patterns</strong> detected in recent data</div>'
        html_report += '<div class="data-table"><table><thead><tr><th>Pattern</th><th>Description</th><th>Risk Level</th></tr></thead><tbody>'
        for pattern in emerging_patterns[:10]:  # Show top 10
            html_report += f'<tr><td>{pattern.get("pattern", "Unknown")}</td><td>{pattern.get("description", "N/A")}</td><td class="risk-high">{pattern.get("risk_level", "Unknown")}</td></tr>'
        html_report += '</tbody></table></div>'
    else:
        html_report += '<div class="alert-box alert-info">✅ No concerning emerging resistance patterns detected</div>'

    html_report += """
    </div>

    <!-- RISK ASSESSMENT -->
    <div class="section">
        <h2>⚠️ Risk Assessment</h2>

        <h3>Resistance Burden</h3>
"""

    if resistance_burden:
        burden_rate = resistance_burden.get('overall_resistance_rate', 0)
        impact = resistance_burden.get('public_health_impact', '')

        if 'CRITICAL' in impact:
            html_report += f'<div class="alert-box alert-critical">🔴 <strong>CRITICAL BURDEN</strong> - {impact}</div>'
        elif 'HIGH' in impact:
            html_report += f'<div class="alert-box alert-warning">🟠 <strong>HIGH BURDEN</strong> - {impact}</div>'
        else:
            html_report += f'<div class="alert-box alert-info">🔵 <strong>MODERATE BURDEN</strong> - {impact}</div>'

        html_report += f"""
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{resistance_burden.get('total_resistant_tests', 0)}</div>
                <div class="stat-label">Resistant Tests</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{burden_rate:.1f}%</div>
                <div class="stat-label">Overall Rate</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{resistance_burden.get('total_tests', 0)}</div>
                <div class="stat-label">Total Tests</div>
            </div>
        </div>
"""

    html_report += """
        <h3>Risk Identification & Antibiotic Resistance Patterns</h3>
"""

    if high_risk_organisms:
        html_report += f'<div class="alert-box alert-critical">🚨 <strong>{len(high_risk_organisms)} high-risk organisms identified (≥50% resistance)</strong></div>'
        html_report += '<div class="data-table"><table><thead><tr><th>Risk Level</th><th>Organism</th><th>At-Risk Antibiotic(s)</th><th>Resistance Rate</th><th>Alternative Antibiotics</th><th>Recommendation</th></tr></thead><tbody>'

        # Antibiotic resistance mapping for alternatives
        antibiotic_alternatives = {
            'Fluoroquinolone': ['Cephalosporin', 'Macrolide', 'Beta-lactam'],
            'Azithromycin': ['Fluoroquinolone', 'Cephalosporin', 'Tetracycline'],
            'Tetracycline': ['Fluoroquinolone', 'Macrolide', 'Cephalosporin'],
            'Ampicillin': ['Cephalosporin', 'Fluoroquinolone', 'Macrolide'],
            'Cephalosporin': ['Fluoroquinolone', 'Macrolide', 'Carbapenems'],
            'Macrolide': ['Fluoroquinolone', 'Cephalosporin', 'Tetracycline'],
            'Trimethoprim-sulfamethoxazole': ['Fluoroquinolone', 'Cephalosporin', 'Macrolide']
        }

        for organism in high_risk_organisms[:15]:  # Show top 15
            risk_class = 'risk-high' if organism['risk_level'] == 'CRITICAL' else 'risk-medium' if organism['risk_level'] == 'HIGH' else 'risk-low'
            
            # Get the most resistant antibiotics for this organism
            org_ast = ast_df[ast_df['organism'] == organism['organism']]
            most_resistant_abs = org_ast.groupby('antibiotic')['result'].apply(lambda x: (x == 'R').sum() / len(x) * 100).sort_values(ascending=False).head(3)
            resistant_abs_str = ', '.join([f"{ab} ({rate:.0f}%)" for ab, rate in most_resistant_abs.items()])
            
            # Get alternatives
            alternatives_list = []
            for ab in most_resistant_abs.index:
                alternatives_list.extend(antibiotic_alternatives.get(ab, ['Consult specialist']))
            alternatives_str = ', '.join(list(set(alternatives_list))[:3]) if alternatives_list else 'Consult antimicrobial specialist'
            
            html_report += f'<tr><td class="{risk_class}">{organism["risk_level"]}</td><td><strong>{organism["organism"]}</strong></td><td>{resistant_abs_str}</td><td>{organism["resistance_rate"]:.1f}%</td><td>{alternatives_str}</td><td>Implement stewardship</td></tr>'

        html_report += '</tbody></table></div>'
        html_report += '<p style="color: #666; margin-top: 15px;"><em><strong>Recommendation Basis:</strong> Based on resistance patterns detected in this surveillance data, alternative antibiotics are suggested to manage infections caused by these high-risk organisms. Clinical decision-making should always incorporate local epidemiology, patient factors, and current treatment guidelines.</em></p>'
    else:
        html_report += '<div class="alert-box alert-info">✅ No high-risk organisms detected at critical resistance thresholds</div>'

    html_report += """
    </div>

    <!-- COMPARATIVE ANALYSIS SUMMARY -->
    <div class="section">
        <h2>🔀 Comparative Analysis Summary</h2>
        
        <h3>Multi-Parameter Resistance Patterns</h3>
        <p>Your surveillance dataset includes resistance data that can be analyzed across multiple dimensions. The following comparative insights highlight important geographic, categorical, and organism-specific patterns:</p>
        
        <h4>Geographic Variation in Resistance</h4>
"""
    
    if not region_resistance.empty:
        html_report += f'<p>Antimicrobial resistance varies significantly across geographic regions, ranging from <strong>{region_resistance["resistance_rate"].min():.1f}%</strong> to <strong>{region_resistance["resistance_rate"].max():.1f}%</strong>. The region with the highest resistance is <strong>{region_resistance.iloc[0]["region"]}</strong> at <strong>{region_resistance.iloc[0]["resistance_rate"]:.1f}%</strong>, while <strong>{region_resistance.iloc[-1]["region"]}</strong> shows the lowest at <strong>{region_resistance.iloc[-1]["resistance_rate"]:.1f}%</strong>. These variations indicate localized differences in antibiotic usage patterns, infection control practices, or endemic resistant strain distribution. Geographic hotspots should be prioritized for enhanced interventions and targeted stewardship programs.</p>'
    
    html_report += """
        <h4>Source Category Resistance Profile</h4>
"""
    
    if not source_resistance.empty:
        html_report += f'<p>Resistance patterns differ across source categories, with rates ranging from <strong>{source_resistance["resistance_rate"].min():.1f}%</strong> to <strong>{source_resistance["resistance_rate"].max():.1f}%</strong>. The highest resistance is observed in <strong>{source_resistance.iloc[0]["source_category"]}</strong> sources (<strong>{source_resistance.iloc[0]["resistance_rate"]:.1f}%</strong>), emphasizing the need for source-specific interventions in the One Health approach to AMR control. This framework allows epidemiologists to track organism-antibiotic combinations across different source types and identify critical intervention points.</p>'
    
    html_report += """
        <h4>Key Recommendations for Comparative Analysis</h4>
        <ul>
            <li><strong>Cross-variable comparisons:</strong> Use the dashboard's "Cross-Variable Comparison" tool to examine how specific organism-antibiotic combinations vary across regions, districts, or source types</li>
            <li><strong>Multi-parameter tracking:</strong> Monitor resistance trends for the same organism-antibiotic pair across multiple geographic areas to detect emerging patterns</li>
            <li><strong>Targeted interventions:</strong> Identify high-resistance hotspots and implement localized stewardship and infection control measures</li>
            <li><strong>Source-specific strategies:</strong> Develop tailored prevention programs based on resistance patterns in environmental, food, human, and animal compartments</li>
        </ul>
    </div>

    <!-- DETAILED DATA TABLES -->
    <div class="section">
        <h2>📋 Detailed Data Tables</h2>

        <div class="data-table">
            <h3>Top 10 Organisms by Resistance Rate</h3>
            <table>
                <thead>
                    <tr>
                        <th>Organism</th>
                        <th>Resistance Rate (%)</th>
                        <th>Total Tests</th>
                        <th>Resistant Isolates</th>
                    </tr>
                </thead>
                <tbody>
"""

    # Add organism data
    for _, row in top_organisms.iterrows():
        html_report += f"""
                    <tr>
                        <td>{row['organism']}</td>
                        <td>{row['resistance_rate']}%</td>
                        <td>{int(row['total_tests'])}</td>
                        <td>{int(row['resistant_count'])}</td>
                    </tr>"""

    html_report += """
                </tbody>
            </table>

            <h3>Top 10 Antibiotics by Resistance Rate</h3>
            <table>
                <thead>
                    <tr>
                        <th>Antibiotic</th>
                        <th>Resistance Rate (%)</th>
                        <th>Total Tests</th>
                        <th>Resistant Isolates</th>
                    </tr>
                </thead>
                <tbody>
"""

    # Add antibiotic data
    for _, row in top_antibiotics.iterrows():
        html_report += f"""
                    <tr>
                        <td>{row['antibiotic']}</td>
                        <td>{row['resistance_rate']}%</td>
                        <td>{int(row['total_tests'])}</td>
                        <td>{int(row['resistant_count'])}</td>
                    </tr>"""

    html_report += f"""
                </tbody>
            </table>
        </div>
    </div>

    <div class="footer">
        <p><strong>Comprehensive AMR Surveillance Report</strong> | Generated by AMR Surveillance Dashboard</p>
        <p>Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Dataset: {dataset_name}</p>
        <p>Report includes: Resistance Overview, Geographic Analysis, Trends, Advanced Analytics & Risk Assessment</p>
        <p>For questions or support, please contact the surveillance team.</p>
    </div>
</body>
</html>"""

    return html_report


def generate_apa_style_report(
    dataset_name: str,
    samples_df: pd.DataFrame,
    ast_df: pd.DataFrame
) -> str:
    """Generate APA-style report focusing only on results."""
    
    if ast_df.empty or samples_df.empty:
        return "No data available for report generation."
    
    # Calculate key statistics
    total_samples = len(samples_df)
    total_tests = len(ast_df)
    total_organisms = ast_df['organism'].nunique()
    total_antibiotics = ast_df['antibiotic'].nunique()
    
    # Overall resistance
    overall_resistance = (ast_df['result'] == 'R').sum() / len(ast_df) * 100
    susceptible_rate = (ast_df['result'] == 'S').sum() / len(ast_df) * 100
    intermediate_rate = (ast_df['result'] == 'I').sum() / len(ast_df) * 100
    
    # Resistance by organism
    organism_resistance = ast_df.groupby('organism').agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    organism_resistance.columns = ['organism', 'total_tests', 'resistant_count']
    organism_resistance['resistance_rate'] = (organism_resistance['resistant_count'] / organism_resistance['total_tests'] * 100).round(1)
    organism_resistance = organism_resistance.sort_values('resistance_rate', ascending=False)
    
    # Resistance by antibiotic
    antibiotic_resistance = ast_df.groupby('antibiotic').agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    antibiotic_resistance.columns = ['antibiotic', 'total_tests', 'resistant_count']
    antibiotic_resistance['resistance_rate'] = (antibiotic_resistance['resistant_count'] / antibiotic_resistance['total_tests'] * 100).round(1)
    antibiotic_resistance = antibiotic_resistance.sort_values('resistance_rate', ascending=False)
    
    # Resistance by source category
    source_resistance = ast_df.merge(samples_df[['sample_id', 'source_category']], on='sample_id', how='left')
    source_resistance = source_resistance.groupby('source_category').agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    source_resistance.columns = ['source_category', 'total_tests', 'resistant_count']
    source_resistance['resistance_rate'] = (source_resistance['resistant_count'] / source_resistance['total_tests'] * 100).round(1)
    # Resistance by region
    region_resistance = ast_df.merge(samples_df[['sample_id', 'region']], on='sample_id', how='left')
    region_resistance = region_resistance.groupby('region').agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    region_resistance.columns = ['region', 'total_tests', 'resistant_count']
    region_resistance['resistance_rate'] = (region_resistance['resistant_count'] / region_resistance['total_tests'] * 100).round(1)
    region_resistance = region_resistance.sort_values('resistance_rate', ascending=False)
    
    # Resistance by district
    district_resistance = ast_df.merge(samples_df[['sample_id', 'district']], on='sample_id', how='left')
    district_resistance = district_resistance.groupby('district').agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    district_resistance.columns = ['district', 'total_tests', 'resistant_count']
    district_resistance['resistance_rate'] = (district_resistance['resistant_count'] / district_resistance['total_tests'] * 100).round(1)
    district_resistance = district_resistance.sort_values('resistance_rate', ascending=False)
    
    # Resistance by site type
    site_type_resistance = ast_df.merge(samples_df[['sample_id', 'site_type']], on='sample_id', how='left')
    site_type_resistance = site_type_resistance.groupby('site_type').agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    site_type_resistance.columns = ['site_type', 'total_tests', 'resistant_count']
    site_type_resistance['resistance_rate'] = (site_type_resistance['resistant_count'] / site_type_resistance['total_tests'] * 100).round(1)
    site_type_resistance = site_type_resistance.sort_values('resistance_rate', ascending=False)
    
    # Resistance by source type
    source_type_resistance = ast_df.merge(samples_df[['sample_id', 'source_type']], on='sample_id', how='left')
    source_type_resistance = source_type_resistance.groupby('source_type').agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    source_type_resistance.columns = ['source_type', 'total_tests', 'resistant_count']
    source_type_resistance['resistance_rate'] = (source_type_resistance['resistant_count'] / source_type_resistance['total_tests'] * 100).round(1)
    source_type_resistance = source_type_resistance.sort_values('resistance_rate', ascending=False)
    
    # Advanced analysis
    from src.analytics import (
        detect_resistance_mechanisms, detect_cross_resistance, get_multiple_resistance_patterns,
        calculate_resistance_statistics, calculate_trend_direction, identify_emerging_resistance,
        assess_data_quality, calculate_resistance_burden, compare_organisms, compare_antibiotics
    )
    
    mechanisms_df = detect_resistance_mechanisms(ast_df)
    cross_resistance_df = detect_cross_resistance(ast_df)
    mdr_df = get_multiple_resistance_patterns(ast_df)
    
    # Additional statistics
    resistance_stats = calculate_resistance_statistics(ast_df)
    trend_analysis = calculate_trend_direction(ast_df)
    emerging_patterns = identify_emerging_resistance(ast_df, samples_df)
    data_quality = assess_data_quality(samples_df, ast_df)
    resistance_burden = calculate_resistance_burden(samples_df, ast_df)
    
    # Generate APA-style report
    report = f"""
# Antimicrobial Resistance Surveillance Results

**Dataset:** {dataset_name}  
**Analysis Date:** {datetime.now().strftime('%B %d, %Y')}  
**Total Samples:** {total_samples}  
**Total AST Tests:** {total_tests}  
**Organisms Identified:** {total_organisms}  
**Antibiotics Tested:** {total_antibiotics}

## Overall Resistance Distribution

The antimicrobial susceptibility testing revealed an overall resistance rate of {overall_resistance:.1f}% (n = {total_tests}). Susceptible isolates accounted for {susceptible_rate:.1f}% of all tests, while intermediate resistance was observed in {intermediate_rate:.1f}% of cases.

## Resistance by Organism

Organism-specific resistance rates are presented below (top 10 organisms by resistance rate):

"""
    
    # Add top 10 organisms
    for i, (_, row) in enumerate(organism_resistance.head(10).iterrows()):
        report += f"{i+1}. {row['organism']}: {row['resistance_rate']}% (n = {int(row['total_tests'])})\n"
    
    report += "\n## Resistance by Antibiotic\n\nAntibiotic-specific resistance rates are presented below (top 10 antibiotics by resistance rate):\n\n"
    
    # Add top 10 antibiotics
    for i, (_, row) in enumerate(antibiotic_resistance.head(10).iterrows()):
        report += f"{i+1}. {row['antibiotic']}: {row['resistance_rate']}% (n = {int(row['total_tests'])})\n"
    
    report += "\n## Resistance by Source Category\n\nResistance rates by source category:\n\n"
    
    for i, (_, row) in enumerate(source_resistance.iterrows()):
        report += f"{i+1}. {row['source_category']}: {row['resistance_rate']}% (n = {int(row['total_tests'])})\n"
    
    report += "\n## Resistance by Region\n\nRegional resistance rates:\n\n"
    
    for i, (_, row) in enumerate(region_resistance.iterrows()):
        report += f"{i+1}. {row['region']}: {row['resistance_rate']}% (n = {int(row['total_tests'])})\n"
    
    report += "\n## Resistance by District\n\nDistrict-level resistance rates:\n\n"
    
    for i, (_, row) in enumerate(district_resistance.iterrows()):
        report += f"{i+1}. {row['district']}: {row['resistance_rate']}% (n = {int(row['total_tests'])})\n"
    
    report += "\n## Resistance by Site Type\n\nResistance rates by site type:\n\n"
    
    for i, (_, row) in enumerate(site_type_resistance.iterrows()):
        report += f"{i+1}. {row['site_type']}: {row['resistance_rate']}% (n = {int(row['total_tests'])})\n"
    
    report += "\n## Resistance by Source Type\n\nResistance rates by source type:\n\n"
    
    for i, (_, row) in enumerate(source_type_resistance.iterrows()):
        report += f"{i+1}. {row['source_type']}: {row['resistance_rate']}% (n = {int(row['total_tests'])})\n"
    
    # Add resistance mechanisms if detected
    if not mechanisms_df.empty:
        report += "\n## Resistance Mechanisms Detected\n\n"
        mechanism_counts = mechanisms_df['resistance_mechanism'].value_counts()
        for mechanism, count in mechanism_counts.items():
            report += f"- {mechanism}: {count} isolates\n"
        
        report += "\nDetailed mechanism detections:\n\n"
        for i, (_, row) in enumerate(mechanisms_df.iterrows()):
            report += f"{i+1}. {row['organism']} (isolate {row['isolate_id']}): {row['resistance_mechanism']} ({row['confidence']} confidence)\n"
    
    # Add cross-resistance if detected
    if not cross_resistance_df.empty:
        report += "\n## Cross-Resistance Patterns\n\n"
        class_counts = cross_resistance_df['antibiotic_class'].value_counts()
        for class_name, count in class_counts.items():
            report += f"- {class_name}: {count} isolates\n"
        
        report += "\nDetailed cross-resistance patterns:\n\n"
        for i, (_, row) in enumerate(cross_resistance_df.iterrows()):
            report += f"{i+1}. {row['organism']} (isolate {row['isolate_id']}): {row['antibiotic_class']} ({row['cross_resistance_level']} level, {row['resistant_antibiotics']}/{row['total_antibiotics']} antibiotics)\n"
    
    # Add multi-drug resistance if detected
    if not mdr_df.empty:
        report += "\n## Multi-Drug Resistance Analysis\n\n"
        mdr_counts = mdr_df['resistance_level'].value_counts()
        for level, count in mdr_counts.items():
            report += f"- {level}: {count} isolates\n"
        
        report += "\nDetailed MDR isolates:\n\n"
        for i, (_, row) in enumerate(mdr_df.iterrows()):
            report += f"{i+1}. {row['organism']} (isolate {row['isolate_id']}): {row['resistance_level']} ({row['resistant_antibiotics']}/{row['total_antibiotics']} antibiotics, {row['resistance_percentage']}%)\n"
    
    # Add trend analysis
    if trend_analysis and trend_analysis.get('trend') != 'insufficient_data':
        report += f"\n## Resistance Trend Analysis\n\n"
        report += f"- Trend Direction: {trend_analysis.get('trend', 'N/A')}\n"
        report += f"- First Half Resistance Rate: {trend_analysis.get('first_half_resistance', 0):.1f}%\n"
        report += f"- Second Half Resistance Rate: {trend_analysis.get('second_half_resistance', 0):.1f}%\n"
        report += f"- Change Percentage: {trend_analysis.get('change_percentage', 0):.1f}%\n"
        report += f"- Risk Level: {trend_analysis.get('risk_level', 'N/A')}\n"
    
    # Add emerging resistance patterns
    if emerging_patterns:
        report += "\n## Emerging Resistance Patterns\n\n"
        for pattern in emerging_patterns:
            report += f"- {pattern['organism']} - {pattern['antibiotic']}: {pattern['resistance_rate']}% resistance (n = {pattern['tests']}, severity: {pattern['severity']})\n"
    
    # Add data quality assessment
    if data_quality:
        report += "\n## Data Quality Assessment\n\n"
        report += f"- Total Samples: {data_quality.get('total_samples', 0)}\n"
        report += f"- Total Tests: {data_quality.get('total_tests', 0)}\n"
        report += f"- Samples with Coordinates: {data_quality.get('samples_with_coordinates', 0)}\n"
        report += f"- Tests with Dates: {data_quality.get('tests_with_dates', 0)}\n"
        report += f"- Completeness Score: {data_quality.get('completeness_score', 0):.1f}%\n"
        if data_quality.get('data_quality_issues'):
            report += "- Issues Identified:\n"
            for issue in data_quality.get('data_quality_issues', []):
                report += f"  - {issue}\n"
    
    # Add resistance burden
    if resistance_burden:
        report += "\n## Resistance Burden Assessment\n\n"
        report += f"- Overall Resistance Rate: {resistance_burden.get('overall_resistance_rate', 0):.1f}%\n"
        report += f"- Total Resistant Tests: {resistance_burden.get('total_resistant_tests', 0)}\n"
        report += f"- Public Health Impact: {resistance_burden.get('public_health_impact', 'N/A')}\n"
        report += "- Resistance by Category:\n"
        for category, rate in resistance_burden.get('resistance_by_category', {}).items():
            report += f"  - {category}: {rate:.1f}%\n"
    
    return report


def generate_filtered_html_report(
    report_title: str,
    samples_df: pd.DataFrame,
    ast_df: pd.DataFrame,
    selected_categories: List[str],
    selected_regions: List[str],
    selected_organisms: List[str],
    selected_antibiotics: List[str]
) -> str:
    """Generate professional HTML report with filtered data and enhanced formatting."""

    if ast_df.empty or samples_df.empty:
        return "<html><body><h1>No data available for report generation.</h1></body></html>"

    # Import required modules
    from src import analytics

    # Calculate comprehensive statistics
    total_samples = len(samples_df)
    total_tests = len(ast_df)
    total_organisms = ast_df['organism'].nunique()
    total_antibiotics = ast_df['antibiotic'].nunique()

    # Overall resistance statistics
    overall_resistance = (ast_df['result'] == 'R').sum() / len(ast_df) * 100
    susceptible_rate = (ast_df['result'] == 'S').sum() / len(ast_df) * 100
    intermediate_rate = (ast_df['result'] == 'I').sum() / len(ast_df) * 100

    # Resistance by various categories
    organism_resistance = ast_df.groupby('organism').agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    organism_resistance.columns = ['organism', 'total_tests', 'resistant_count']
    organism_resistance['resistance_rate'] = (organism_resistance['resistant_count'] / organism_resistance['total_tests'] * 100).round(1)
    organism_resistance = organism_resistance.sort_values('resistance_rate', ascending=False)

    antibiotic_resistance = ast_df.groupby('antibiotic').agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    antibiotic_resistance.columns = ['antibiotic', 'total_tests', 'resistant_count']
    antibiotic_resistance['resistance_rate'] = (antibiotic_resistance['resistant_count'] / antibiotic_resistance['total_tests'] * 100).round(1)
    antibiotic_resistance = antibiotic_resistance.sort_values('resistance_rate', ascending=False)

    # Regional analysis
    region_resistance = ast_df.merge(samples_df[['sample_id', 'region']], on='sample_id', how='left')
    region_resistance = region_resistance.groupby('region').agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    region_resistance.columns = ['region', 'total_tests', 'resistant_count']
    region_resistance['resistance_rate'] = (region_resistance['resistant_count'] / region_resistance['total_tests'] * 100).round(1)
    region_resistance = region_resistance.sort_values('resistance_rate', ascending=False)

    # MDR Analysis
    mdr_data = plots.detect_mdr_isolates(ast_df)
    mdr_count = len(mdr_data) if not mdr_data.empty else 0

    # Get advanced analytics data
    resistance_mechanisms = analytics.detect_resistance_mechanisms(ast_df)
    cross_resistance = analytics.detect_cross_resistance(ast_df)
    multiple_resistance = analytics.get_multiple_resistance_patterns(ast_df)
    trend_analysis = analytics.calculate_trend_direction(ast_df)
    emerging_patterns = analytics.identify_emerging_resistance(ast_df, samples_df)
    data_quality = analytics.assess_data_quality(samples_df, ast_df)
    high_risk_organisms = analytics.get_high_risk_organisms(ast_df)
    antibiotic_recommendations = analytics.generate_antibiotic_recommendations(ast_df)
    resistance_burden = analytics.calculate_resistance_burden(samples_df, ast_df)
    resistance_forecast = analytics.forecast_resistance_trend(ast_df)

    # Create professional charts with better formatting
    # 1. Overall resistance pie chart - enhanced
    overall_fig = go.Figure(data=[go.Pie(
        labels=['Resistant', 'Susceptible', 'Intermediate'],
        values=[overall_resistance, susceptible_rate, intermediate_rate],
        marker_colors=['#e74c3c', '#27ae60', '#f39c12'],
        textinfo='label+percent',
        textposition='outside',
        showlegend=False
    )])
    overall_fig.update_layout(
        title={
            'text': 'Overall Resistance Distribution',
            'y': 0.95,
            'x': 0.5,
            'xanchor': 'center',
            'yanchor': 'top',
            'font': {'size': 20, 'color': '#2c3e50', 'family': 'Arial, sans-serif'}
        },
        font={'family': 'Arial, sans-serif', 'size': 12},
        margin=dict(t=100, b=50, l=50, r=50)
    )
    overall_chart = overall_fig.to_html(full_html=False, include_plotlyjs='cdn', config={'displayModeBar': False})

    # 2. Organism resistance bar chart (top 10) - enhanced
    top_organisms = organism_resistance.head(10)
    organism_fig = go.Figure()
    organism_fig.add_trace(go.Bar(
        x=top_organisms['organism'],
        y=top_organisms['resistance_rate'],
        marker_color='#3498db',
        text=top_organisms['resistance_rate'].round(1).astype(str) + '%',
        textposition='outside',
        hovertemplate='<b>%{x}</b><br>Resistance Rate: %{y:.1f}%<br>Tests: %{customdata}<extra></extra>',
        customdata=top_organisms['total_tests']
    ))
    organism_fig.update_layout(
        title={
            'text': 'Resistance by Organism (Top 10)',
            'y': 0.95,
            'x': 0.5,
            'xanchor': 'center',
            'yanchor': 'top',
            'font': {'size': 18, 'color': '#2c3e50', 'family': 'Arial, sans-serif'}
        },
        xaxis_title='Organism',
        yaxis_title='Resistance Rate (%)',
        font={'family': 'Arial, sans-serif', 'size': 11},
        margin=dict(t=80, b=100, l=60, r=40),
        xaxis_tickangle=-45,
        height=500
    )
    organism_fig.update_traces(textfont_size=10)
    organism_chart = organism_fig.to_html(full_html=False, include_plotlyjs=False, config={'displayModeBar': False})

    # 3. Antibiotic resistance bar chart (top 10) - enhanced
    top_antibiotics = antibiotic_resistance.head(10)
    antibiotic_fig = go.Figure()
    antibiotic_fig.add_trace(go.Bar(
        x=top_antibiotics['antibiotic'],
        y=top_antibiotics['resistance_rate'],
        marker_color='#e67e22',
        text=top_antibiotics['resistance_rate'].round(1).astype(str) + '%',
        textposition='outside',
        hovertemplate='<b>%{x}</b><br>Resistance Rate: %{y:.1f}%<br>Tests: %{customdata}<extra></extra>',
        customdata=top_antibiotics['total_tests']
    ))
    antibiotic_fig.update_layout(
        title={
            'text': 'Resistance by Antibiotic (Top 10)',
            'y': 0.95,
            'x': 0.5,
            'xanchor': 'center',
            'yanchor': 'top',
            'font': {'size': 18, 'color': '#2c3e50', 'family': 'Arial, sans-serif'}
        },
        xaxis_title='Antibiotic',
        yaxis_title='Resistance Rate (%)',
        font={'family': 'Arial, sans-serif', 'size': 11},
        margin=dict(t=80, b=120, l=60, r=40),
        xaxis_tickangle=-45,
        height=500
    )
    antibiotic_fig.update_traces(textfont_size=10)
    antibiotic_chart = antibiotic_fig.to_html(full_html=False, include_plotlyjs=False, config={'displayModeBar': False})

    # 4. Regional resistance chart - enhanced
    region_fig = go.Figure()
    region_fig.add_trace(go.Bar(
        x=region_resistance['region'].head(10),
        y=region_resistance['resistance_rate'].head(10),
        marker_color='#9b59b6',
        text=region_resistance['resistance_rate'].head(10).round(1).astype(str) + '%',
        textposition='outside',
        hovertemplate='<b>%{x}</b><br>Resistance Rate: %{y:.1f}%<br>Tests: %{customdata}<extra></extra>',
        customdata=region_resistance['total_tests'].head(10)
    ))
    region_fig.update_layout(
        title={
            'text': 'Resistance by Region (Top 10)',
            'y': 0.95,
            'x': 0.5,
            'xanchor': 'center',
            'yanchor': 'top',
            'font': {'size': 18, 'color': '#2c3e50', 'family': 'Arial, sans-serif'}
        },
        xaxis_title='Region',
        yaxis_title='Resistance Rate (%)',
        font={'family': 'Arial, sans-serif', 'size': 11},
        margin=dict(t=80, b=100, l=60, r=40),
        xaxis_tickangle=-45,
        height=500
    )
    region_fig.update_traces(textfont_size=10)
    region_chart = region_fig.to_html(full_html=False, include_plotlyjs=False, config={'displayModeBar': False})

    # Generate professional HTML report with enhanced styling
    html_report = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{report_title}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {{
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #1a202c;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: linear-gradient(135deg, #f7fafc 0%, #edf2f7 100%);
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }}

        .report-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            border-radius: 16px;
            margin-bottom: 40px;
            text-align: center;
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);
            position: relative;
            overflow: hidden;
        }}

        .report-header::before {{
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
            animation: pulse 4s ease-in-out infinite;
        }}

        @keyframes pulse {{
            0%, 100% {{ transform: scale(1); }}
            50% {{ transform: scale(1.05); }}
        }}

        .report-header h1 {{
            margin: 0 0 10px 0;
            font-size: 2.8em;
            font-weight: 700;
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
            position: relative;
            z-index: 2;
        }}

        .report-header .subtitle {{
            font-size: 1.2em;
            opacity: 0.95;
            margin-bottom: 20px;
            position: relative;
            z-index: 2;
        }}

        .report-meta {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
            position: relative;
            z-index: 2;
        }}

        .meta-item {{
            background: rgba(255,255,255,0.15);
            padding: 15px;
            border-radius: 10px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
        }}

        .meta-item .label {{
            font-size: 0.85em;
            opacity: 0.8;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 5px;
        }}

        .meta-item .value {{
            font-size: 1.4em;
            font-weight: 600;
        }}

        .section {{
            background: white;
            padding: 35px;
            border-radius: 16px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            margin-bottom: 30px;
            border: 1px solid #e2e8f0;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}

        .section:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.12);
        }}

        .section h2 {{
            margin-top: 0;
            margin-bottom: 25px;
            color: #2d3748;
            border-bottom: 3px solid #667eea;
            padding-bottom: 15px;
            font-size: 1.8em;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .section h2::before {{
            content: '';
            width: 6px;
            height: 24px;
            background: #667eea;
            border-radius: 3px;
        }}

        .section h3 {{
            color: #4a5568;
            margin-top: 30px;
            margin-bottom: 15px;
            font-size: 1.3em;
            font-weight: 500;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .stat-card {{
            background: linear-gradient(135deg, #f7fafc 0%, #edf2f7 100%);
            padding: 25px;
            border-radius: 12px;
            text-align: center;
            border: 1px solid #e2e8f0;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}

        .stat-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.1);
        }}

        .stat-number {{
            font-size: 2.4em;
            font-weight: 700;
            color: #667eea;
            margin-bottom: 8px;
            display: block;
        }}

        .stat-label {{
            color: #718096;
            font-size: 0.95em;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 500;
        }}

        .chart-container {{
            margin: 25px 0;
            padding: 20px;
            background: #f8fafc;
            border-radius: 12px;
            border: 1px solid #e2e8f0;
        }}

        .chart-container h3 {{
            margin-top: 0;
            margin-bottom: 20px;
            color: #2d3748;
            font-size: 1.2em;
            text-align: center;
        }}

        .data-table {{
            margin: 25px 0;
            overflow-x: auto;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }}

        table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }}

        th {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 16px 12px;
            text-align: left;
            font-weight: 600;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border: none;
        }}

        td {{
            padding: 14px 12px;
            border-bottom: 1px solid #e2e8f0;
            font-size: 0.9em;
        }}

        tbody tr {{
            transition: background-color 0.2s ease;
        }}

        tbody tr:hover {{
            background-color: #f7fafc;
        }}

        tbody tr:nth-child(even) {{
            background-color: #f8fafc;
        }}

        tbody tr:nth-child(even):hover {{
            background-color: #edf2f7;
        }}

        .alert-box {{
            padding: 20px;
            border-radius: 12px;
            margin: 15px 0;
            border-left: 4px solid;
            font-weight: 500;
        }}

        .alert-critical {{
            background: linear-gradient(135deg, #fed7d7 0%, #feb2b2 100%);
            border-left-color: #e53e3e;
            color: #742a2a;
        }}

        .alert-warning {{
            background: linear-gradient(135deg, #fef5e7 0%, #fed7aa 100%);
            border-left-color: #dd6b20;
            color: #7c2d12;
        }}

        .alert-info {{
            background: linear-gradient(135deg, #ebf8ff 0%, #bee3f8 100%);
            border-left-color: #3182ce;
            color: #2a4365;
        }}

        .alert-success {{
            background: linear-gradient(135deg, #f0fff4 0%, #c6f6d5 100%);
            border-left-color: #38a169;
            color: #22543d;
        }}

        .filters-summary {{
            background: #f7fafc;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 25px;
            border: 1px solid #e2e8f0;
        }}

        .filters-summary h4 {{
            margin-top: 0;
            color: #4a5568;
            font-size: 1.1em;
        }}

        .filter-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }}

        .filter-tag {{
            background: #edf2f7;
            color: #4a5568;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: 500;
        }}

        .footer {{
            text-align: center;
            color: #a0aec0;
            font-size: 0.9em;
            margin-top: 60px;
            padding-top: 30px;
            border-top: 2px solid #e2e8f0;
        }}

        .footer p {{
            margin: 5px 0;
        }}

        @media print {{
            body {{
                background: white !important;
                max-width: none;
                margin: 0;
                padding: 15px;
                -webkit-print-color-adjust: exact;
            }}
            .section {{
                box-shadow: none !important;
                border: 1px solid #ccc !important;
                margin-bottom: 20px;
                page-break-inside: avoid;
            }}
            .chart-container {{
                page-break-inside: avoid;
            }}
        }}

        @media (max-width: 768px) {{
            .report-header {{
                padding: 25px 20px;
            }}

            .report-header h1 {{
                font-size: 2.2em;
            }}

            .section {{
                padding: 20px;
                margin-bottom: 20px;
            }}

            .stats-grid {{
                grid-template-columns: 1fr;
                gap: 15px;
            }}

            .report-meta {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="report-header">
        <h1>🦠 {report_title}</h1>
        <div class="subtitle">Comprehensive Antimicrobial Resistance Surveillance Report</div>
        <div class="report-meta">
            <div class="meta-item">
                <div class="label">Generated</div>
                <div class="value">{datetime.now().strftime('%B %d, %Y')}</div>
            </div>
            <div class="meta-item">
                <div class="label">Data Period</div>
                <div class="value">Filtered Dataset</div>
            </div>
            <div class="meta-item">
                <div class="label">Total Samples</div>
                <div class="value">{total_samples:,}</div>
            </div>
            <div class="meta-item">
                <div class="label">AST Tests</div>
                <div class="value">{total_tests:,}</div>
            </div>
        </div>
    </div>

    <!-- EXECUTIVE SUMMARY -->
    <div class="section">
        <h2>📊 Executive Summary</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <span class="stat-number">{total_samples:,}</span>
                <span class="stat-label">Total Samples</span>
            </div>
            <div class="stat-card">
                <span class="stat-number">{total_tests:,}</span>
                <span class="stat-label">AST Tests</span>
            </div>
            <div class="stat-card">
                <span class="stat-number">{total_organisms}</span>
                <span class="stat-label">Organisms Identified</span>
            </div>
            <div class="stat-card">
                <span class="stat-number">{total_antibiotics}</span>
                <span class="stat-label">Antibiotics Tested</span>
            </div>
            <div class="stat-card">
                <span class="stat-number">{overall_resistance:.1f}%</span>
                <span class="stat-label">Overall Resistance</span>
            </div>
            <div class="stat-card">
                <span class="stat-number">{mdr_count}</span>
                <span class="stat-label">MDR Isolates</span>
            </div>
        </div>

        <div style="background: #f8fafc; padding: 20px; border-radius: 12px; margin-top: 20px;">
            <h3 style="margin-top: 0; color: #2d3748;">Key Findings</h3>
            <ul style="color: #4a5568; line-height: 1.8;">
                <li><strong>Resistance Rate:</strong> {overall_resistance:.1f}% of all antimicrobial susceptibility tests showed resistance</li>
                <li><strong>Multi-Drug Resistance:</strong> {mdr_count} isolates demonstrated resistance to 3 or more drug classes</li>
                <li><strong>Geographic Coverage:</strong> Data from {len(selected_regions)} regions analyzed</li>
                <li><strong>Organism Diversity:</strong> {total_organisms} different organisms tested</li>
                <li><strong>Antibiotic Coverage:</strong> {total_antibiotics} antibiotics evaluated</li>
            </ul>
        </div>
    </div>

    <!-- RESISTANCE OVERVIEW -->
    <div class="section">
        <h2>🔬 Resistance Overview</h2>

        <div class="chart-container">
            <h3>Overall Resistance Distribution</h3>
            <p style="text-align: center; margin-bottom: 20px; color: #4a5568;">
                Analysis of {total_tests:,} antimicrobial susceptibility tests showing resistance patterns across all filtered data.
            </p>
            {overall_chart}
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 30px;">
            <div class="chart-container">
                <h3>Resistance by Organism (Top 10)</h3>
                {organism_chart}
            </div>

            <div class="chart-container">
                <h3>Resistance by Antibiotic (Top 10)</h3>
                {antibiotic_chart}
            </div>
        </div>

        <h3>Multi-Drug Resistance Analysis</h3>
        <div class="alert-box alert-warning">
            <strong>{mdr_count} Multi-Drug Resistant Isolates Detected</strong><br>
            These isolates show resistance to 3 or more antimicrobial drug classes, indicating concerning resistance patterns.
        </div>
    </div>

    <!-- GEOGRAPHIC ANALYSIS -->
    <div class="section">
        <h2>🗺️ Geographic Analysis</h2>

        <div class="chart-container">
            <h3>Resistance by Region</h3>
            {region_chart}
        </div>

        <div class="data-table">
            <h3>Regional Resistance Summary</h3>
            <table>
                <thead>
                    <tr>
                        <th>Region</th>
                        <th>Resistance Rate (%)</th>
                        <th>Total Tests</th>
                        <th>Resistant Isolates</th>
                    </tr>
                </thead>
                <tbody>
"""

    # Add regional data
    for _, row in region_resistance.head(10).iterrows():
        html_report += f"""
                    <tr>
                        <td>{row['region']}</td>
                        <td>{row['resistance_rate']}%</td>
                        <td>{int(row['total_tests']):,}</td>
                        <td>{int(row['resistant_count']):,}</td>
                    </tr>"""

    html_report += """
                </tbody>
            </table>
        </div>
    </div>

    <!-- DETAILED DATA TABLES -->
    <div class="section">
        <h2>📋 Detailed Resistance Data</h2>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 30px;">
            <div class="data-table">
                <h3>Top 10 Organisms by Resistance Rate</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Organism</th>
                            <th>Resistance Rate (%)</th>
                            <th>Total Tests</th>
                            <th>Resistant Isolates</th>
                        </tr>
                    </thead>
                    <tbody>
"""

    # Add organism data
    for _, row in top_organisms.iterrows():
        html_report += f"""
                        <tr>
                            <td>{row['organism']}</td>
                            <td>{row['resistance_rate']}%</td>
                            <td>{int(row['total_tests']):,}</td>
                            <td>{int(row['resistant_count']):,}</td>
                        </tr>"""

    html_report += """
                    </tbody>
                </table>
            </div>

            <div class="data-table">
                <h3>Top 10 Antibiotics by Resistance Rate</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Antibiotic</th>
                            <th>Resistance Rate (%)</th>
                            <th>Total Tests</th>
                            <th>Resistant Isolates</th>
                        </tr>
                    </thead>
                    <tbody>
"""

    # Add antibiotic data
    for _, row in top_antibiotics.iterrows():
        html_report += f"""
                        <tr>
                            <td>{row['antibiotic']}</td>
                            <td>{row['resistance_rate']}%</td>
                            <td>{int(row['total_tests']):,}</td>
                            <td>{int(row['resistant_count']):,}</td>
                        </tr>"""

    html_report += f"""
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- TRENDS ANALYSIS -->
    <div class="section">
        <h2>📈 Trends Analysis</h2>

        <div class="chart-container">
            <h3>Resistance Trend Analysis</h3>
            <p style="text-align: center; margin-bottom: 20px; color: #4a5568;">
                Analysis of resistance trends over time based on filtered data, showing resistance patterns and temporal distribution.
            </p>
"""

    # Add trend analysis with enhanced details including seasonal analysis
    if trend_analysis and trend_analysis.get('trend') != 'insufficient_data':
        # Calculate date range information and seasonal breakdown
        if 'test_date' in ast_df.columns:
            ast_df['test_date_parsed'] = pd.to_datetime(ast_df['test_date'], errors='coerce')
            valid_dates = ast_df[ast_df['test_date_parsed'].notna()]['test_date_parsed']

            if not valid_dates.empty:
                earliest_date = valid_dates.min()
                latest_date = valid_dates.max()
                earliest_str = earliest_date.strftime('%Y-%m-%d')
                latest_str = latest_date.strftime('%Y-%m-%d')
                total_tests = len(valid_dates)
                date_range_info = f"Data spans from {earliest_str} to {latest_str} ({total_tests} tests)"
                
                # Calculate seasonal resistance rates (Ghana climate: Dry Nov-Mar, Wet Apr-Oct)
                ast_df['month'] = ast_df['test_date_parsed'].dt.month
                dry_season_data = ast_df[ast_df['month'].isin([11, 12, 1, 2, 3])]  # Nov-Mar
                wet_season_data = ast_df[ast_df['month'].isin([4, 5, 6, 7, 8, 9, 10])]  # Apr-Oct
                
                dry_season_resistance = (dry_season_data['result'] == 'R').sum() / len(dry_season_data) * 100 if len(dry_season_data) > 0 else 0
                wet_season_resistance = (wet_season_data['result'] == 'R').sum() / len(wet_season_data) * 100 if len(wet_season_data) > 0 else 0
            else:
                date_range_info = "Date information not available"
                dry_season_resistance = 0
                wet_season_resistance = 0
        else:
            date_range_info = "Date information not available"
            dry_season_resistance = 0
            wet_season_resistance = 0

        # Calculate specific date ranges for first and second half
        if 'test_date' in ast_df.columns:
            ast_df['test_date_parsed'] = pd.to_datetime(ast_df['test_date'], errors='coerce')
            valid_dates = ast_df[ast_df['test_date_parsed'].notna()]['test_date_parsed'].sort_values()
            if not valid_dates.empty:
                midpoint = valid_dates.iloc[len(valid_dates) // 2]
                first_half_dates = valid_dates[valid_dates <= midpoint]
                second_half_dates = valid_dates[valid_dates > midpoint]
                
                first_half_start = first_half_dates.min().strftime('%Y-%m-%d')
                first_half_end = first_half_dates.max().strftime('%Y-%m-%d')
                second_half_start = second_half_dates.min().strftime('%Y-%m-%d')
                second_half_end = second_half_dates.max().strftime('%Y-%m-%d')
            else:
                first_half_start = first_half_end = second_half_start = second_half_end = "N/A"
        else:
            first_half_start = first_half_end = second_half_start = second_half_end = "N/A"

        html_report += f"""
            <div style="background: #f8fafc; padding: 20px; border-radius: 12px; margin-bottom: 20px;">
                <h4 style="margin-top: 0; color: #2d3748;">📈 Trend Analysis Summary</h4>
                <p style="margin-bottom: 15px; color: #4a5568;"><strong>Overall Time Period:</strong> {date_range_info}</p>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    <div style="text-align: center;">
                        <div style="font-size: 1.5em; font-weight: bold; color: #667eea;">{trend_analysis.get('trend', 'N/A')}</div>
                        <div style="color: #4a5568; font-size: 0.9em;">Overall Trend Direction</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 1.5em; font-weight: bold; color: #27ae60;">{trend_analysis.get('first_half_resistance', 0):.1f}%</div>
                        <div style="color: #4a5568; font-size: 0.85em;">First Half ({first_half_start} to {first_half_end})</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 1.5em; font-weight: bold; color: #e74c3c;">{trend_analysis.get('second_half_resistance', 0):.1f}%</div>
                        <div style="color: #4a5568; font-size: 0.85em;">Second Half ({second_half_start} to {second_half_end})</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 1.5em; font-weight: bold; color: #f39c12;">{trend_analysis.get('change_percentage', 0):+.1f}%</div>
                        <div style="color: #4a5568; font-size: 0.9em;">Resistance Change</div>
                    </div>
                </div>
            </div>
"""

        # Add seasonal analysis
        html_report += f"""
            <div style="background: #f0f9ff; padding: 20px; border-radius: 12px; margin-bottom: 20px; border-left: 4px solid #3182ce;">
                <h4 style="margin-top: 0; color: #2d3748;">🌍 Seasonal Resistance Patterns</h4>
                <p style="margin-bottom: 15px; color: #4a5568;">Resistance rates by Ghana's climate seasons:</p>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    <div style="text-align: center;">
                        <div style="font-size: 1.5em; font-weight: bold; color: #c05621;">🏜️ {dry_season_resistance:.1f}%</div>
                        <div style="color: #4a5568; font-size: 0.9em;">Dry Season (Nov-Mar)</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 1.5em; font-weight: bold; color: #22863a;">🌧️ {wet_season_resistance:.1f}%</div>
                        <div style="color: #4a5568; font-size: 0.9em;">Wet Season (Apr-Oct)</div>
                    </div>
                </div>
            </div>
"""

        # Add interpretation of trend
        change_pct = trend_analysis.get('change_percentage', 0)
        trend_direction = trend_analysis.get('trend', 'stable')

        if abs(change_pct) < 5:
            trend_interpretation = "Resistance levels are relatively stable with minimal change over time."
        elif change_pct > 0:
            trend_interpretation = f"Resistance is increasing by {abs(change_pct):.1f}% from the first half to the second half, indicating a concerning upward trend."
        else:
            trend_interpretation = f"Resistance is decreasing by {abs(change_pct):.1f}% from the first half to the second half, showing positive improvement."

        html_report += f"""
            <div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #ffc107;">
                <h5 style="margin-top: 0; color: #856404;">📊 Trend Interpretation</h5>
                <p style="margin: 0; color: #856404;">{trend_interpretation}</p>
            </div>
"""

        # Add resistance forecast if available
        if resistance_forecast and resistance_forecast.get('forecast_available', False):
            html_report += f"""
            <div style="background: #f0f9ff; padding: 20px; border-radius: 12px; margin-bottom: 20px; border-left: 4px solid #3182ce;">
                <h4 style="margin-top: 0; color: #2d3748;">🔮 Resistance Forecast</h4>
                <p style="margin-bottom: 10px;"><strong>Projected Resistance Rate:</strong> {resistance_forecast.get('forecasted_rate', 0):.1f}% in {resistance_forecast.get('periods', 3)} months</p>
                <p style="margin-bottom: 10px;"><strong>Confidence Interval:</strong> {resistance_forecast.get('confidence_lower', 0):.1f}% - {resistance_forecast.get('confidence_upper', 0):.1f}%</p>
                <p style="margin: 0;"><strong>Risk Assessment:</strong> <span style="color: {'#e74c3c' if resistance_forecast.get('risk_level') == 'High' else '#f39c12' if resistance_forecast.get('risk_level') == 'Medium' else '#27ae60'};">{resistance_forecast.get('risk_level', 'Unknown')} Risk</span></p>
            </div>
"""

    # Add recent test data summary
    html_report += """
            <div style="background: #f8f9fa; padding: 20px; border-radius: 12px; margin-bottom: 20px;">
                <h4 style="margin-top: 0; color: #2d3748;">📊 Recent Testing Activity</h4>
                <p style="margin-bottom: 15px; color: #4a5568;">Summary of most recent antimicrobial susceptibility tests:</p>
"""

    # Get recent tests (last 10)
    if 'test_date' in ast_df.columns:
        recent_tests = ast_df.sort_values('test_date', ascending=False).head(10)
        if not recent_tests.empty:
            html_report += '<div class="data-table"><table><thead><tr><th>Test Date</th><th>Organism</th><th>Antibiotic</th><th>Result</th></tr></thead><tbody>'

            for _, test in recent_tests.iterrows():
                result_color = '#e74c3c' if test['result'] == 'R' else '#f39c12' if test['result'] == 'I' else '#27ae60'
                html_report += f'<tr><td>{test["test_date"]}</td><td>{test["organism"]}</td><td>{test["antibiotic"]}</td><td style="color: {result_color}; font-weight: bold;">{test["result"]}</td></tr>'

            html_report += '</tbody></table></div>'

    html_report += """
            </div>
"""

    # Add emerging resistance patterns
    if emerging_patterns:
        html_report += """
            <h3>Emerging Resistance Patterns</h3>
            <div class="data-table">
                <table>
                    <thead>
                        <tr>
                            <th>Organism</th>
                            <th>Antibiotic</th>
                            <th>Resistance Rate (%)</th>
                            <th>Tests</th>
                            <th>Severity</th>
                        </tr>
                    </thead>
                    <tbody>
"""

        for pattern in emerging_patterns[:10]:  # Show top 10
            severity_color = {'Critical': '#e74c3c', 'High': '#f39c12', 'Medium': '#f1c40f', 'Low': '#27ae60'}.get(pattern.get('severity', 'Low'), '#27ae60')
            html_report += f"""
                        <tr>
                            <td>{pattern.get('organism', 'N/A')}</td>
                            <td>{pattern.get('antibiotic', 'N/A')}</td>
                            <td>{pattern.get('resistance_rate', 0):.1f}%</td>
                            <td>{pattern.get('tests', 0)}</td>
                            <td><span style="color: {severity_color}; font-weight: bold;">{pattern.get('severity', 'Low')}</span></td>
                        </tr>"""

        html_report += """
                    </tbody>
                </table>
            </div>
"""

    html_report += """
        </div>
    </div>

    <!-- ADVANCED ANALYTICS -->
    <div class="section">
        <h2>🔬 Advanced Analytics</h2>
"""

    # Resistance Mechanisms
    if not resistance_mechanisms.empty:
        html_report += """
        <div class="chart-container">
            <h3>Resistance Mechanisms Detected</h3>
            <div class="data-table">
                <table>
                    <thead>
                        <tr>
                            <th>Organism</th>
                            <th>Resistance Mechanism</th>
                            <th>Confidence</th>
                            <th>Isolates</th>
                        </tr>
                    </thead>
                    <tbody>
"""

        mechanism_summary = resistance_mechanisms.groupby(['organism', 'resistance_mechanism', 'confidence']).size().reset_index(name='count')
        for _, row in mechanism_summary.iterrows():
            confidence_color = {'High': '#27ae60', 'Moderate': '#f39c12', 'Low': '#e74c3c'}.get(row['confidence'], '#95a5a6')
            html_report += f"""
                        <tr>
                            <td>{row['organism']}</td>
                            <td>{row['resistance_mechanism']}</td>
                            <td><span style="color: {confidence_color}; font-weight: bold;">{row['confidence']}</span></td>
                            <td>{int(row['count'])}</td>
                        </tr>"""

        html_report += """
                    </tbody>
                </table>
            </div>
        </div>
"""

    # Cross-Resistance Patterns
    if not cross_resistance.empty:
        html_report += """
        <div class="chart-container">
            <h3>Cross-Resistance Patterns</h3>
            <div class="data-table">
                <table>
                    <thead>
                        <tr>
                            <th>Organism</th>
                            <th>Antibiotic Class</th>
                            <th>Cross-Resistance Level</th>
                            <th>Resistant Antibiotics</th>
                            <th>Total Antibiotics</th>
                        </tr>
                    </thead>
                    <tbody>
"""

        for _, row in cross_resistance.iterrows():
            level_color = {'High': '#e74c3c', 'Medium': '#f39c12', 'Low': '#27ae60'}.get(row.get('cross_resistance_level', 'Low'), '#27ae60')
            html_report += f"""
                        <tr>
                            <td>{row['organism']}</td>
                            <td>{row['antibiotic_class']}</td>
                            <td><span style="color: {level_color}; font-weight: bold;">{row.get('cross_resistance_level', 'Low')}</span></td>
                            <td>{row.get('resistant_antibiotics', 0)}</td>
                            <td>{row.get('total_antibiotics', 0)}</td>
                        </tr>"""

        html_report += """
                    </tbody>
                </table>
            </div>
        </div>
"""

    # Multiple Resistance Patterns
    if not multiple_resistance.empty:
        html_report += """
        <div class="chart-container">
            <h3>Multiple Drug Resistance Patterns</h3>
            <div class="data-table">
                <table>
                    <thead>
                        <tr>
                            <th>Organism</th>
                            <th>Resistance Level</th>
                            <th>Resistant Antibiotics</th>
                            <th>Total Antibiotics</th>
                            <th>Resistance Percentage</th>
                        </tr>
                    </thead>
                    <tbody>
"""

        for _, row in multiple_resistance.iterrows():
            html_report += f"""
                        <tr>
                            <td>{row['organism']}</td>
                            <td>{row['resistance_level']}</td>
                            <td>{row['resistant_antibiotics']}</td>
                            <td>{row['total_antibiotics']}</td>
                            <td>{row['resistance_percentage']:.1f}%</td>
                        </tr>"""

        html_report += """
                    </tbody>
                </table>
            </div>
        </div>
"""

    html_report += """
    </div>

    <!-- RISK ASSESSMENT -->
    <div class="section">
        <h2>⚠️ Risk Assessment</h2>
"""

    # High Risk Organisms
    if high_risk_organisms:
        html_report += """
        <div class="chart-container">
            <h3>High-Risk Organisms</h3>
            <p style="text-align: center; margin-bottom: 20px; color: #4a5568;">
                Organisms with resistance rates above 50% requiring immediate attention.
            </p>
            <div class="data-table">
                <table>
                    <thead>
                        <tr>
                            <th>Organism</th>
                            <th>Resistance Rate (%)</th>
                            <th>Risk Level</th>
                            <th>Recommendation</th>
                        </tr>
                    </thead>
                    <tbody>
"""

        for organism in high_risk_organisms:
            risk_color = {'Critical': '#e74c3c', 'High': '#f39c12', 'Medium': '#f1c40f'}.get(organism.get('risk_level', 'Low'), '#27ae60')
            html_report += f"""
                        <tr>
                            <td>{organism.get('organism', 'N/A')}</td>
                            <td>{organism.get('resistance_rate', 0):.1f}%</td>
                            <td><span style="color: {risk_color}; font-weight: bold;">{organism.get('risk_level', 'Low')}</span></td>
                            <td>{organism.get('recommendation', 'Monitor closely')}</td>
                        </tr>"""

        html_report += """
                    </tbody>
                </table>
            </div>
        </div>
"""

    # Antibiotic Recommendations
    if antibiotic_recommendations:
        html_report += """
        <div class="chart-container">
            <h3>Antibiotic Treatment Recommendations</h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px;">
"""

        for rec in antibiotic_recommendations[:6]:  # Show top 6 recommendations
            status_color = {'Preferred': '#27ae60', 'Alternative': '#f39c12', 'Not Recommended': '#e74c3c'}.get(rec.get('status', 'Alternative'), '#95a5a6')
            html_report += f"""
                <div style="background: #f8fafc; padding: 15px; border-radius: 8px; border-left: 4px solid {status_color};">
                    <div style="font-weight: bold; color: #2d3748; margin-bottom: 5px;">{rec.get('antibiotic', 'N/A')}</div>
                    <div style="color: {status_color}; font-weight: 500; margin-bottom: 5px;">{rec.get('status', 'Alternative')}</div>
                    <div style="color: #4a5568; font-size: 0.9em;">{rec.get('reason', 'Based on resistance patterns')}</div>
                </div>"""

        html_report += """
            </div>
        </div>
"""

    # Resistance Burden
    if resistance_burden:
        html_report += f"""
        <div class="chart-container">
            <h3>Resistance Burden Assessment</h3>
            <div style="background: #f8fafc; padding: 20px; border-radius: 12px;">
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 20px;">
                    <div style="text-align: center;">
                        <div style="font-size: 2em; font-weight: bold; color: #667eea;">{resistance_burden.get('overall_resistance_rate', 0):.1f}%</div>
                        <div style="color: #4a5568;">Overall Resistance Rate</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 2em; font-weight: bold; color: #e74c3c;">{resistance_burden.get('total_resistant_tests', 0):,}</div>
                        <div style="color: #4a5568;">Total Resistant Tests</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 1.5em; font-weight: bold; color: #f39c12;">{resistance_burden.get('public_health_impact', 'Unknown')}</div>
                        <div style="color: #4a5568;">Public Health Impact</div>
                    </div>
                </div>
"""

        if resistance_burden.get('resistance_by_category'):
            html_report += """
                <h4>Resistance by Category</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px;">
"""
            for category, rate in resistance_burden.get('resistance_by_category', {}).items():
                html_report += f"""
                    <div style="background: white; padding: 10px; border-radius: 6px; text-align: center; border: 1px solid #e2e8f0;">
                        <div style="font-weight: bold; color: #2d3748;">{rate:.1f}%</div>
                        <div style="color: #4a5568; font-size: 0.9em;">{category}</div>
                    </div>"""

            html_report += """
                </div>
"""

        html_report += """
            </div>
        </div>
"""

    # Data Quality Assessment
    if data_quality:
        html_report += f"""
        <div class="chart-container">
            <h3>Data Quality Assessment</h3>
            <div style="background: #f8fafc; padding: 20px; border-radius: 12px;">
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px;">
                    <div style="text-align: center;">
                        <div style="font-size: 1.8em; font-weight: bold; color: #667eea;">{data_quality.get('completeness_score', 0):.1f}%</div>
                        <div style="color: #4a5568;">Completeness Score</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 1.8em; font-weight: bold; color: #27ae60;">{data_quality.get('samples_with_coordinates', 0):,}</div>
                        <div style="color: #4a5568;">Samples with Coordinates</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 1.8em; font-weight: bold; color: #f39c12;">{data_quality.get('tests_with_dates', 0):,}</div>
                        <div style="color: #4a5568;">Tests with Dates</div>
                    </div>
                </div>
"""

        if data_quality.get('data_quality_issues'):
            html_report += """
                <h4>Data Quality Issues Identified</h4>
                <ul style="color: #4a5568;">
"""
            for issue in data_quality.get('data_quality_issues', []):
                html_report += f"                    <li>{issue}</li>"

            html_report += """
                </ul>
"""

        html_report += """
            </div>
        </div>
"""

    # Format the current date/time
    current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    html_report += f"""
    </div>

    <div class="footer">
        <p><strong>AMR Surveillance Dashboard - Comprehensive Filtered Report</strong></p>
        <p>Generated on {current_datetime} | AMR Surveillance Dashboard</p>
        <p>Includes Resistance Overview, Geographic Analysis, Trends, Advanced Analytics, and Risk Assessment</p>
        <p>For questions or support, please contact the surveillance team.</p>
    </div>
</body>
</html>"""

    return html_report
    