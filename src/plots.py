"""
Plotting module for AMR Surveillance Dashboard.
Creates interactive visualizations using Plotly.
"""
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from typing import Optional, List, Tuple


def calculate_resistance_percentage(ast_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate resistance percentage by organism and antibiotic."""
    if ast_df.empty:
        return pd.DataFrame()

    # Group by organism and antibiotic, count each result type
    result_counts = ast_df.groupby(['organism', 'antibiotic', 'result']).size().reset_index(name='count')
    
    if result_counts.empty:
        return pd.DataFrame()
    
    # Pivot to get R, I, S counts for each organism-antibiotic pair
    pivot_df = result_counts.pivot_table(
        index=['organism', 'antibiotic'],
        columns='result',
        values='count',
        fill_value=0
    )
    
    if pivot_df.empty:
        return pd.DataFrame()
    
    # Reset index to make organism and antibiotic regular columns
    pivot_df = pivot_df.reset_index()
    
    # Create result dataframe
    result_df = pd.DataFrame({
        'organism': pivot_df['organism'],
        'antibiotic': pivot_df['antibiotic'],
        'susceptible': pivot_df.get('S', 0),
        'intermediate': pivot_df.get('I', 0),
        'resistant': pivot_df.get('R', 0),
    })
    
    result_df['total_tests'] = result_df['susceptible'] + result_df['intermediate'] + result_df['resistant']
    result_df['percent_susceptible'] = (result_df['susceptible'] / result_df['total_tests'] * 100).round(2)
    result_df['percent_intermediate'] = (result_df['intermediate'] / result_df['total_tests'] * 100).round(2)
    result_df['percent_resistant'] = (result_df['resistant'] / result_df['total_tests'] * 100).round(2)
    
    return result_df.sort_values('percent_resistant', ascending=False)


def get_antibiotic_resistance_rates(ast_df: pd.DataFrame) -> pd.DataFrame:
    """Get resistance rates by antibiotic (aggregated across all organisms)."""
    if ast_df.empty:
        return pd.DataFrame()

    resistance_stats = calculate_resistance_percentage(ast_df)

    if resistance_stats.empty:
        return pd.DataFrame()

    # Group by antibiotic and aggregate
    antibiotic_stats = resistance_stats.groupby('antibiotic').agg({
        'resistant': 'sum',
        'total_tests': 'sum'
    }).reset_index()

    antibiotic_stats['resistance_rate'] = (antibiotic_stats['resistant'] / antibiotic_stats['total_tests'] * 100).round(2)

    return antibiotic_stats.sort_values('resistance_rate', ascending=False)


def plot_top_antibiotics(ast_df: pd.DataFrame, max_items: int = 30) -> go.Figure:
    """Plot top antibiotics by resistance percentage."""
    if ast_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        return fig

    resistance_stats = calculate_resistance_percentage(ast_df)
    
    # Group by antibiotic (across all organisms)
    antibiotic_stats = resistance_stats.groupby('antibiotic').agg({
        'resistant': 'sum',
        'total_tests': 'sum'
    }).reset_index()
    antibiotic_stats['percent_resistant'] = (antibiotic_stats['resistant'] / antibiotic_stats['total_tests'] * 100).round(2)
    antibiotic_stats = antibiotic_stats.sort_values('percent_resistant', ascending=False).head(max_items)
    
    fig = px.bar(antibiotic_stats, x='antibiotic', y='percent_resistant',
                 title='Top Antibiotics by Resistance %',
                 labels={'antibiotic': 'Antibiotic', 'percent_resistant': 'Resistance %'},
                 color='percent_resistant',
                 color_continuous_scale='RdYlGn_r',
                 height=500)
    fig.update_layout(xaxis_tickangle=-45, hovermode='x unified')
    return fig


def plot_resistance_by_category(ast_df: pd.DataFrame, samples_df: pd.DataFrame) -> go.Figure:
    """Plot resistance by source category (ENVIRONMENT, FOOD, HUMAN, ANIMAL, AQUACULTURE)."""
    if ast_df.empty or samples_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font=dict(size=14))
        fig.update_layout(height=500)
        return fig

    # Merge to get source_category
    merged = ast_df.merge(samples_df[['sample_id', 'source_category']], on='sample_id', how='left')
    merged = merged.dropna(subset=['source_category'])
    
    if merged.empty:
        fig = go.Figure()
        fig.add_annotation(text="No matching samples found", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=500)
        return fig

    # Calculate stats by category
    category_stats = merged.groupby(['source_category', 'result']).size().reset_index(name='count')
    
    if category_stats.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=500)
        return fig

    # Pivot to wide format
    pivot_data = category_stats.pivot_table(
        index='source_category',
        columns='result',
        values='count',
        fill_value=0
    )

    # Calculate percentages
    totals = pivot_data.sum(axis=1)
    percentages = pivot_data.div(totals, axis=0) * 100
    
    fig = go.Figure()
    
    colors = {'R': '#d62728', 'I': '#ff7f0e', 'S': '#2ca02c'}
    result_labels = {'R': 'Resistant', 'I': 'Intermediate', 'S': 'Susceptible'}
    
    for result in ['R', 'I', 'S']:
        if result in percentages.columns:
            fig.add_trace(go.Bar(
                x=percentages.index,
                y=percentages[result],
                name=result_labels.get(result, result),
                marker_color=colors.get(result, '#808080')
            ))
    
    fig.update_layout(
        barmode='stack',
        title='Resistance Profile by Source Category',
        xaxis_title='Source Category',
        yaxis_title='Percentage (%)',
        height=500,
        hovermode='x unified',
        showlegend=True
    )
    return fig


def plot_resistance_by_source_type(ast_df: pd.DataFrame, samples_df: pd.DataFrame) -> go.Figure:
    """Plot resistance by source type."""
    if ast_df.empty or samples_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font=dict(size=14))
        fig.update_layout(height=500)
        return fig

    merged = ast_df.merge(samples_df[['sample_id', 'source_type']], on='sample_id', how='left')
    merged = merged.dropna(subset=['source_type'])
    
    if merged.empty:
        fig = go.Figure()
        fig.add_annotation(text="No matching samples found", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=500)
        return fig
    
    source_type_stats = merged.groupby(['source_type', 'result']).size().reset_index(name='count')
    
    if source_type_stats.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=500)
        return fig

    # Pivot to wide format
    pivot_data = source_type_stats.pivot_table(
        index='source_type',
        columns='result',
        values='count',
        fill_value=0
    )

    totals = pivot_data.sum(axis=1)
    percentages = pivot_data.div(totals, axis=0) * 100
    
    fig = go.Figure()
    
    colors = {'R': '#d62728', 'I': '#ff7f0e', 'S': '#2ca02c'}
    result_labels = {'R': 'Resistant', 'I': 'Intermediate', 'S': 'Susceptible'}
    
    for result in ['R', 'I', 'S']:
        if result in percentages.columns:
            fig.add_trace(go.Bar(
                x=percentages.index,
                y=percentages[result],
                name=result_labels.get(result, result),
                marker_color=colors.get(result, '#808080')
            ))
    
    fig.update_layout(
        barmode='stack',
        title='Resistance Profile by Source Type',
        xaxis_title='Source Type',
        yaxis_title='Percentage (%)',
        height=500,
        xaxis_tickangle=-45,
        hovermode='x unified',
        showlegend=True
    )
    return fig


def plot_resistance_trends(ast_df: pd.DataFrame, time_aggregation: str = 'Monthly') -> go.Figure:
    """Plot resistance trends over time."""
    if ast_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font=dict(size=14))
        fig.update_layout(height=500)
        return fig

    # Parse dates
    ast_df = ast_df.copy()
    ast_df['test_date'] = pd.to_datetime(ast_df['test_date'], errors='coerce')
    ast_df = ast_df.dropna(subset=['test_date'])
    
    if ast_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No valid dates in data", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=500)
        return fig

    # Aggregate by time period
    if time_aggregation == 'Monthly':
        ast_df['period'] = ast_df['test_date'].dt.to_period('M')
    elif time_aggregation == 'Quarterly':
        ast_df['period'] = ast_df['test_date'].dt.to_period('Q')
    else:  # Yearly
        ast_df['period'] = ast_df['test_date'].dt.to_period('Y')

    # Calculate resistance by period
    period_stats = ast_df.groupby(['period', 'result']).size().reset_index(name='count')
    
    if period_stats.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=500)
        return fig

    # Pivot to wide format
    pivot_data = period_stats.pivot_table(
        index='period',
        columns='result',
        values='count',
        fill_value=0
    )
    
    # Sort by period
    pivot_data = pivot_data.sort_index()
    
    # Calculate percentages
    totals = pivot_data.sum(axis=1)
    percentages = pivot_data.div(totals, axis=0) * 100
    
    # Convert period to string for plotting with proper formatting
    if time_aggregation == 'Monthly':
        periods = [str(p) for p in percentages.index]  # 2025-01
    elif time_aggregation == 'Quarterly':
        periods = [f"{p.year} Q{p.quarter}" for p in percentages.index]  # 2025 Q1
    else:  # Yearly
        periods = [str(p.year) for p in percentages.index]  # 2025
    
    fig = go.Figure()
    
    colors = {'R': '#d62728', 'I': '#ff7f0e', 'S': '#2ca02c'}
    result_labels = {'R': 'Resistant', 'I': 'Intermediate', 'S': 'Susceptible'}
    
    for result in ['R', 'I', 'S']:
        if result in percentages.columns:
            fig.add_trace(go.Scatter(
                x=periods, 
                y=percentages[result],
                name=result_labels.get(result, result),
                mode='lines+markers',
                line=dict(color=colors.get(result, '#808080'), width=3),
                marker=dict(size=8),
                hovertemplate='%{x}<br>%{y:.1f}%<extra></extra>'
            ))
    
    fig.update_layout(
        title=f'Resistance Trends ({time_aggregation})',
        xaxis_title='Time Period',
        yaxis_title='Percentage (%)',
        height=500,
        hovermode='x unified',
        showlegend=True
    )
    return fig


def plot_point_map(samples_df: pd.DataFrame, ast_df: pd.DataFrame) -> go.Figure:
    """Plot sample locations on Ghana map with district boundaries."""
    if samples_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No sample data", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        return fig

    # Filter samples with coordinates
    map_data = samples_df[samples_df['latitude'].notna() & samples_df['longitude'].notna()].copy()

    if map_data.empty:
        fig = go.Figure()
        fig.add_annotation(text="No samples with geographic coordinates", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        return fig

    # Add resistance info
    resistance_by_sample = ast_df.groupby('sample_id').apply(
        lambda x: (x['result'] == 'R').sum() / len(x) * 100 if len(x) > 0 else 0,
        include_groups=False
    ).reset_index(name='resistance_percent')

    map_data = map_data.merge(resistance_by_sample, on='sample_id', how='left')
    map_data['resistance_percent'] = map_data['resistance_percent'].fillna(0)

    # Create figure with Ghana focus
    fig = go.Figure()

    # Add Ghana country boundary (simplified)
    # Ghana coordinates for country outline
    ghana_outline = [
        dict(
            type='scattergeo',
            lat=[4.5, 4.5, 11.5, 11.5, 4.5],
            lon=[-3.5, 1.5, 1.5, -3.5, -3.5],
            mode='lines',
            line=dict(width=2, color='black'),
            showlegend=False,
            hoverinfo='skip'
        )
    ]

    # Add sample points as red dots
    fig.add_trace(go.Scattergeo(
        lat=map_data['latitude'],
        lon=map_data['longitude'],
        mode='markers',
        marker=dict(
            size=8,
            color='red',
            symbol='circle',
            line=dict(width=1, color='darkred'),
            opacity=0.8
        ),
        text=map_data['sample_id'],
        hovertemplate=
            '<b>Sample ID:</b> %{text}<br>' +
            '<b>Region:</b> %{customdata[0]}<br>' +
            '<b>District:</b> %{customdata[1]}<br>' +
            '<b>Source:</b> %{customdata[2]}<br>' +
            '<b>Type:</b> %{customdata[3]}<br>' +
            '<b>Resistance Rate:</b> %{customdata[4]:.1f}%<br>' +
            '<b>Coordinates:</b> (%{lat:.4f}, %{lon:.4f})<extra></extra>',
        customdata=map_data[['region', 'district', 'source_category', 'source_type', 'resistance_percent']].values,
        name='Sample Locations'
    ))

    # Ghana major regions for reference (simplified boundaries)
    regions_data = [
        {'name': 'Greater Accra', 'lat': 5.6, 'lon': -0.2, 'color': 'rgba(255,0,0,0.1)'},
        {'name': 'Ashanti', 'lat': 6.7, 'lon': -1.6, 'color': 'rgba(0,255,0,0.1)'},
        {'name': 'Eastern', 'lat': 6.3, 'lon': -0.5, 'color': 'rgba(0,0,255,0.1)'},
        {'name': 'Central', 'lat': 5.5, 'lon': -1.2, 'color': 'rgba(255,255,0,0.1)'},
        {'name': 'Western', 'lat': 5.3, 'lon': -2.3, 'color': 'rgba(255,0,255,0.1)'},
        {'name': 'Volta', 'lat': 6.6, 'lon': 0.5, 'color': 'rgba(0,255,255,0.1)'},
        {'name': 'Northern', 'lat': 9.4, 'lon': -1.0, 'color': 'rgba(128,128,128,0.1)'},
        {'name': 'Upper East', 'lat': 10.7, 'lon': -0.3, 'color': 'rgba(128,0,128,0.1)'},
        {'name': 'Upper West', 'lat': 10.1, 'lon': -2.5, 'color': 'rgba(0,128,128,0.1)'},
        {'name': 'Brong-Ahafo', 'lat': 7.8, 'lon': -1.5, 'color': 'rgba(128,128,0,0.1)'}
    ]

    # Add region labels
    for region in regions_data:
        fig.add_trace(go.Scattergeo(
            lat=[region['lat']],
            lon=[region['lon']],
            mode='text',
            text=[region['name']],
            textposition='middle center',
            textfont=dict(size=10, color='black'),
            showlegend=False,
            hoverinfo='skip'
        ))

    fig.update_layout(
        geo=dict(
            scope='africa',
            projection_type='natural earth',
            showcountries=True,
            countrywidth=1,
            showcoastlines=True,
            coastlinewidth=1,
            showland=True,
            landcolor='lightgray',
            showocean=True,
            oceancolor='lightblue',
            # Focus tightly on Ghana
            lataxis_range=[4.5, 11.5],
            lonaxis_range=[-3.5, 1.5],
            center=dict(lat=7.5, lon=-1.0),
            resolution=50
        ),
        margin=dict(l=0, r=0, t=50, b=0),
        height=800,
        title=dict(
            text='🗺️ AMR Surveillance Sample Locations - Ghana',
            x=0.5,
            y=0.95,
            xanchor='center',
            yanchor='top',
            font=dict(size=18, color='#2c3e50', family='Arial, sans-serif')
        ),
        legend=dict(
            x=0.02,
            y=0.98,
            bgcolor='rgba(255,255,255,0.8)',
            bordercolor='black',
            borderwidth=1
        )
    )

    return fig



def get_top_districts_by_resistance(ast_df: pd.DataFrame, samples_df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Get top districts by resistance percentage."""
    if ast_df.empty or samples_df.empty:
        return pd.DataFrame()

    merged = ast_df.merge(samples_df[['sample_id', 'district']], on='sample_id', how='left')
    merged = merged.dropna(subset=['district'])
    
    if merged.empty:
        return pd.DataFrame()
    
    district_stats = merged.groupby(['district', 'result']).size().reset_index(name='count')
    
    # Pivot to wide format
    pivot_data = district_stats.pivot_table(
        index='district',
        columns='result',
        values='count',
        fill_value=0
    )
    
    if pivot_data.empty:
        return pd.DataFrame()

    total = pivot_data.sum(axis=1)
    resistant_count = pivot_data.get('R', pd.Series(0))
    
    result = pd.DataFrame({
        'district': pivot_data.index,
        'total_tests': total.values,
        'resistant': resistant_count.values,
        'percent_resistant': (resistant_count.values / total.values * 100).round(2)
    })
    
    return result.sort_values('percent_resistant', ascending=False).head(top_n)


def get_resistance_by_region(ast_df: pd.DataFrame, samples_df: pd.DataFrame) -> pd.DataFrame:
    """Get resistance statistics by region."""
    if ast_df.empty or samples_df.empty:
        return pd.DataFrame()

    merged = ast_df.merge(samples_df[['sample_id', 'region']], on='sample_id', how='left')
    merged = merged.dropna(subset=['region'])
    
    if merged.empty:
        return pd.DataFrame()
    
    region_stats = merged.groupby(['region', 'result']).size().reset_index(name='count')
    
    # Pivot to wide format
    pivot_data = region_stats.pivot_table(
        index='region',
        columns='result',
        values='count',
        fill_value=0
    )
    
    if pivot_data.empty:
        return pd.DataFrame()

    total = pivot_data.sum(axis=1)
    susceptible = pivot_data.get('S', pd.Series(0, index=pivot_data.index))
    intermediate = pivot_data.get('I', pd.Series(0, index=pivot_data.index))
    resistant = pivot_data.get('R', pd.Series(0, index=pivot_data.index))
    
    result = pd.DataFrame({
        'region': pivot_data.index,
        'total_tests': total.values,
        'susceptible': susceptible.values,
        'intermediate': intermediate.values,
        'resistant': resistant.values,
        'percent_resistant': (resistant.values / total.values * 100).round(2)
    })
    
    return result.sort_values('percent_resistant', ascending=False)


def plot_resistance_by_region(ast_df: pd.DataFrame, samples_df: pd.DataFrame) -> go.Figure:
    """Plot resistance distribution by region."""
    region_data = get_resistance_by_region(ast_df, samples_df)
    
    if region_data.empty:
        fig = go.Figure()
        fig.add_annotation(text="No regional data", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        return fig
    
    # Create a copy with additional info for hover
    plot_data = region_data.copy()
    plot_data['hover_text'] = plot_data.apply(
        lambda row: f"{row['region']}<br>Resistance Rate: {row['percent_resistant']:.2f}%<br>" +
                   f"Susceptible: {int(row['susceptible'])}<br>" +
                   f"Intermediate: {int(row['intermediate'])}<br>" +
                   f"Resistant: {int(row['resistant'])}<br>" +
                   f"Total: {int(row['total_tests'])}", 
        axis=1
    )
    
    fig = px.bar(
        plot_data,
        x='region',
        y=['susceptible', 'intermediate', 'resistant'],
        title='Antimicrobial Resistance by Region',
        labels={'value': 'Number of Tests', 'region': 'Region', 'variable': 'Result Type'},
        barmode='stack',
        color_discrete_map={'susceptible': '#2ecc71', 'intermediate': '#f39c12', 'resistant': '#e74c3c'},
        height=450,
        hover_data={'hover_text': False}
    )
    
    # Update hover text for each trace
    for trace in fig.data:
        trace.hovertemplate = '%{customdata[0]}<extra></extra>'
        trace.customdata = plot_data[['hover_text']].values
    
    fig.update_layout(
        xaxis_tickangle=-45,
        hovermode='x unified',
        legend=dict(title='Resistance Profile')
    )
    
    return fig


def plot_resistance_percentage_by_region(ast_df: pd.DataFrame, samples_df: pd.DataFrame) -> go.Figure:
    """Plot resistance percentage by region."""
    region_data = get_resistance_by_region(ast_df, samples_df)
    
    if region_data.empty:
        fig = go.Figure()
        fig.add_annotation(text="No regional data", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        return fig
    
    # Keep the same sort order as the stacked bar chart (descending by percent_resistant)
    # This ensures visual alignment between the two graphs
    # Calculate dynamic height: 30px per region + padding (more compact)
    num_regions = len(region_data)
    chart_height = max(400, num_regions * 30 + 80)
    
    fig = px.bar(
        region_data,
        y='region',
        x='percent_resistant',
        orientation='h',
        title='Resistance Rate by Region (%)',
        labels={'percent_resistant': 'Resistance %', 'region': 'Region'},
        color='percent_resistant',
        color_continuous_scale='RdYlGn_r',
        height=chart_height,
        hover_data={'total_tests': True, 'resistant': True}
    )
    
    fig.update_layout(
        margin=dict(l=150),
        hovermode='y unified'
    )
    
    return fig


def get_resistance_by_district_detailed(ast_df: pd.DataFrame, samples_df: pd.DataFrame) -> pd.DataFrame:
    """Get detailed resistance statistics by district."""
    if ast_df.empty or samples_df.empty:
        return pd.DataFrame()

    merged = ast_df.merge(samples_df[['sample_id', 'district', 'region']], on='sample_id', how='left')
    merged = merged.dropna(subset=['district'])
    
    if merged.empty:
        return pd.DataFrame()
    
    district_stats = merged.groupby(['district', 'region', 'result']).size().reset_index(name='count')
    
    # Pivot to wide format
    pivot_data = district_stats.pivot_table(
        index=['district', 'region'],
        columns='result',
        values='count',
        fill_value=0
    )
    
    if pivot_data.empty:
        return pd.DataFrame()

    total = pivot_data.sum(axis=1)
    susceptible = pivot_data.get('S', pd.Series(0))
    intermediate = pivot_data.get('I', pd.Series(0))
    resistant = pivot_data.get('R', pd.Series(0))
    
    result = pd.DataFrame({
        'district': [idx[0] for idx in pivot_data.index],
        'region': [idx[1] for idx in pivot_data.index],
        'total_tests': total.values,
        'susceptible': susceptible.values,
        'intermediate': intermediate.values,
        'resistant': resistant.values,
        'percent_resistant': (resistant.values / total.values * 100).round(2)
    })
    
    return result.sort_values('percent_resistant', ascending=False)


def plot_resistance_by_district_detailed(ast_df: pd.DataFrame, samples_df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    """Plot resistance by district with region information."""
    district_data = get_resistance_by_district_detailed(ast_df, samples_df).head(top_n)
    
    if district_data.empty:
        fig = go.Figure()
        fig.add_annotation(text="No district data", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        return fig
    
    fig = px.bar(
        district_data.sort_values('percent_resistant', ascending=True),
        y='district',
        x='percent_resistant',
        orientation='h',
        title=f'Top {top_n} Districts by Resistance Rate (%)',
        labels={'percent_resistant': 'Resistance %', 'district': 'District'},
        color='percent_resistant',
        color_continuous_scale='RdYlGn_r',
        height=500,
        hover_data={'region': True, 'total_tests': True, 'resistant': True}
    )
    
    fig.update_layout(
        margin=dict(l=180),
        hovermode='y unified'
    )
    
    return fig

# ============================================================================
# ADVANCED AMR FEATURES
# ============================================================================

def detect_mdr_isolates(ast_df: pd.DataFrame, resistance_threshold: int = 3) -> pd.DataFrame:
    """
    Detect multi-drug resistant (MDR) isolates.
    MDR: resistant to 3 or more drug classes
    """
    if ast_df.empty:
        return pd.DataFrame()
    
    # Map antibiotics to drug classes (simplified)
    drug_classes = {
        'Ampicillin': 'Beta-lactams',
        'Cephalosporin': 'Beta-lactams',
        'Ceftriaxone': 'Beta-lactams',
        'Amoxicillin': 'Beta-lactams',
        'Penicillin': 'Beta-lactams',
        'Ciprofloxacin': 'Quinolones',
        'Norfloxacin': 'Quinolones',
        'Ofloxacin': 'Quinolones',
        'Gentamicin': 'Aminoglycosides',
        'Streptomycin': 'Aminoglycosides',
        'Tetracycline': 'Tetracyclines',
        'Doxycycline': 'Tetracyclines',
        'Sulfamethoxazole': 'Sulfonamides',
        'Chloramphenicol': 'Phenicols',
        'Trimethoprim': 'Folate antagonists',
        'Clindamycin': 'Macrolides',
        'Erythromycin': 'Macrolides',
        'Azithromycin': 'Macrolides',
    }
    
    # Add drug class
    ast_df = ast_df.copy()
    ast_df['drug_class'] = ast_df['antibiotic'].map(drug_classes).fillna('Other')
    
    # Find resistant isolates
    resistant = ast_df[ast_df['result'] == 'R'].copy()
    
    # Count resistant drug classes per isolate
    mdr_data = resistant.groupby('isolate_id').agg({
        'drug_class': 'nunique',
        'organism': 'first',
        'sample_id': 'first'
    }).reset_index()
    mdr_data.columns = ['isolate_id', 'resistant_drug_classes', 'organism', 'sample_id']
    
    # Filter MDR isolates
    mdr_isolates = mdr_data[mdr_data['resistant_drug_classes'] >= resistance_threshold]
    
    return mdr_isolates.sort_values('resistant_drug_classes', ascending=False)


def plot_organism_antibiotic_heatmap(ast_df: pd.DataFrame) -> go.Figure:
    """Plot organism-antibiotic resistance heatmap."""
    if ast_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=500)
        return fig
    
    # Calculate resistance percentage
    resistance_stats = calculate_resistance_percentage(ast_df)
    
    if resistance_stats.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=500)
        return fig
    
    # Pivot for heatmap
    heatmap_data = resistance_stats.pivot_table(
        index='organism',
        columns='antibiotic',
        values='percent_resistant',
        fill_value=0
    )
    
    # Limit to top organisms and antibiotics for readability
    top_organisms = heatmap_data.index[:8] if len(heatmap_data) > 8 else heatmap_data.index
    top_antibiotics = heatmap_data.columns[:10] if len(heatmap_data.columns) > 10 else heatmap_data.columns
    heatmap_data = heatmap_data.loc[top_organisms, top_antibiotics]
    
    fig = go.Figure(data=go.Heatmap(
        z=heatmap_data.values,
        x=heatmap_data.columns,
        y=heatmap_data.index,
        colorscale='RdYlGn_r',
        hovertemplate='<b>%{y}</b><br>%{x}<br>Resistance: %{z:.1f}%<extra></extra>',
        colorbar=dict(title='Resistance %')
    ))
    
    fig.update_layout(
        title='Resistance Heatmap: Organisms vs Antibiotics',
        xaxis_title='Antibiotic',
        yaxis_title='Organism',
        height=600,
        xaxis_tickangle=-45
    )
    
    return fig


def get_co_resistance_patterns(ast_df: pd.DataFrame, min_samples: int = 5) -> pd.DataFrame:
    """Identify co-resistance patterns (common antibiotic combinations)."""
    if ast_df.empty:
        return pd.DataFrame()
    
    # Get resistant isolates
    resistant = ast_df[ast_df['result'] == 'R'].copy()
    
    if resistant.empty:
        return pd.DataFrame()
    
    # Find antibiotic combinations within same isolate
    co_resistance = resistant.groupby('isolate_id')['antibiotic'].apply(
        lambda x: ', '.join(sorted(x))
    ).reset_index()
    co_resistance.columns = ['isolate_id', 'antibiotic_combination']
    
    # Count occurrences
    pattern_counts = co_resistance['antibiotic_combination'].value_counts().reset_index()
    pattern_counts.columns = ['antibiotic_combination', 'count']
    
    # Filter by minimum samples
    pattern_counts = pattern_counts[pattern_counts['count'] >= min_samples]
    
    return pattern_counts.sort_values('count', ascending=False)


def plot_resistance_distribution(ast_df: pd.DataFrame) -> go.Figure:
    """Plot overall resistance distribution using bar chart for better readability."""
    if ast_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=400)
        return fig

    # Count results
    result_counts = ast_df['result'].value_counts().reset_index()
    result_counts.columns = ['result', 'count']

    # Map to labels
    result_labels = {'R': 'Resistant', 'I': 'Intermediate', 'S': 'Susceptible'}
    result_counts['label'] = result_counts['result'].map(result_labels)

    # Calculate percentages
    result_counts['percentage'] = (result_counts['count'] / result_counts['count'].sum() * 100).round(1)

    # Sort by resistance level (S, I, R)
    result_counts['sort_order'] = result_counts['result'].map({'S': 0, 'I': 1, 'R': 2})
    result_counts = result_counts.sort_values('sort_order')

    colors = {'R': '#d62728', 'I': '#ff7f0e', 'S': '#2ca02c'}

    # Use horizontal bar chart for better readability
    fig = px.bar(
        result_counts,
        y='label',
        x='percentage',
        title='Resistance Distribution',
        color='result',
        color_discrete_map={'R': colors['R'], 'I': colors['I'], 'S': colors['S']},
        orientation='h',
        text='percentage'
    )

    fig.update_traces(texttemplate='%{text}%', textposition='outside')
    fig.update_layout(
        height=400,
        xaxis_title='Percentage (%)',
        yaxis_title='',
        showlegend=False
    )

    return fig


def get_surveillance_alerts(ast_df: pd.DataFrame, samples_df: pd.DataFrame) -> List[Dict]:
    """Generate AMR surveillance alerts based on thresholds."""
    alerts = []
    
    if ast_df.empty or samples_df.empty:
        return alerts
    
    # Check overall resistance
    total_tests = len(ast_df)
    if total_tests > 0:
        overall_resistance = (ast_df['result'] == 'R').sum() / total_tests * 100
        if overall_resistance > 30:
            alerts.append({
                'severity': 'HIGH',
                'message': f'Overall resistance exceeds 30%: {overall_resistance:.1f}%',
                'type': 'resistance_threshold'
            })
    
    # Check for MDR isolates
    mdr = detect_mdr_isolates(ast_df)
    if len(mdr) > 0:
        alerts.append({
            'severity': 'HIGH',
            'message': f'{len(mdr)} multi-drug resistant isolates detected',
            'type': 'mdr_detection'
        })
    
    # Check for high-risk organism-antibiotic combinations
    resistance_stats = calculate_resistance_percentage(ast_df)
    if not resistance_stats.empty:
        high_risk = resistance_stats[
            (resistance_stats['percent_resistant'] > 50) & 
            (resistance_stats['total_tests'] >= 10)
        ]
        if len(high_risk) > 0:
            top_combo = high_risk.iloc[0]
            alerts.append({
                'severity': 'MEDIUM',
                'message': f'{top_combo["organism"]} shows {top_combo["percent_resistant"]:.1f}% resistance to {top_combo["antibiotic"]}',
                'type': 'high_resistance_combo'
            })
    
    return alerts


def plot_resistance_mechanisms(ast_df: pd.DataFrame) -> go.Figure:
    """Plot detected resistance mechanisms."""
    from src.analytics import detect_resistance_mechanisms
    
    mechanisms_df = detect_resistance_mechanisms(ast_df)
    
    if mechanisms_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No resistance mechanisms detected", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=400)
        return fig
    
    # Count mechanisms by type
    mechanism_counts = mechanisms_df['resistance_mechanism'].value_counts().reset_index()
    mechanism_counts.columns = ['mechanism', 'count']
    
    colors = {
        'ESBL': '#e74c3c',
        'Carbapenemase': '#9b59b6',
        'MRSA': '#f39c12',
        'AmpC': '#27ae60',
        'VRSA': '#e67e22',
        'VISA': '#d35400'
    }
    
    fig = px.bar(
        mechanism_counts,
        x='mechanism',
        y='count',
        title='Detected Resistance Mechanisms',
        color='mechanism',
        color_discrete_map=colors,
        labels={'count': 'Number of Isolates', 'mechanism': 'Resistance Mechanism'}
    )
    
    fig.update_layout(height=400, showlegend=False)
    return fig


def plot_cross_resistance_patterns(ast_df: pd.DataFrame) -> go.Figure:
    """Plot cross-resistance patterns by antibiotic class."""
    from src.analytics import detect_cross_resistance
    
    cross_resistance_df = detect_cross_resistance(ast_df)
    
    if cross_resistance_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No cross-resistance patterns detected", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=400)
        return fig
    
    # Count cross-resistance by antibiotic class
    class_counts = cross_resistance_df['antibiotic_class'].value_counts().reset_index()
    class_counts.columns = ['antibiotic_class', 'count']
    
    fig = px.bar(
        class_counts,
        x='antibiotic_class',
        y='count',
        title='Cross-Resistance Patterns by Antibiotic Class',
        color='count',
        color_continuous_scale='Reds',
        labels={'count': 'Number of Isolates', 'antibiotic_class': 'Antibiotic Class'}
    )
    
    fig.update_layout(height=400)
    return fig


def plot_multiple_resistance_distribution(ast_df: pd.DataFrame) -> go.Figure:
    """Plot distribution of multiple antibiotic resistance."""
    from src.analytics import get_multiple_resistance_patterns
    
    mdr_df = get_multiple_resistance_patterns(ast_df)
    
    if mdr_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No multiple resistance patterns detected", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=400)
        return fig
    
    # Count by resistance level
    level_counts = mdr_df['resistance_level'].value_counts().reset_index()
    level_counts.columns = ['resistance_level', 'count']
    
    colors = {'MDR': '#e74c3c', 'Multi-drug resistant': '#f39c12'}
    
    fig = px.pie(
        level_counts,
        values='count',
        names='resistance_level',
        title='Multiple Antibiotic Resistance Distribution',
        color='resistance_level',
        color_discrete_map=colors
    )
    
    fig.update_layout(height=400)
    return fig
