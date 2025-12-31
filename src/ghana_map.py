"""
Enhanced interactive mapping module for Ghana with region and district labels.
Uses pydeck for interactive maps with resistance pattern visualization.
"""
import pandas as pd
import numpy as np
import pydeck as pdk
import streamlit as st
from typing import Optional


# Ghana Regions and Districts with approximate coordinates
GHANA_REGIONS = {
    "Ahafo": (6.8, -2.2),
    "Ashanti": (6.5, -1.5),
    "Bono": (7.2, -2.5),
    "Bono East": (7.5, -0.8),
    "Central": (5.2, -1.2),
    "Eastern": (6.0, -0.5),
    "Greater Accra": (5.5, -0.2),
    "Northern": (9.3, -1.0),
    "North East": (10.2, -1.0),
    "Oti": (8.5, 0.5),
    "Savannah": (10.0, -2.0),
    "Upper East": (10.8, -1.2),
    "Upper West": (10.5, -2.5),
    "Volta": (6.5, 0.8),
    "Western": (5.0, -2.5),
    "Western North": (5.5, -3.0)
}

# Ghana Districts (sample - commonly sampled areas)
GHANA_DISTRICTS = {
    # Greater Accra
    "Accra": (5.603, -0.187),
    "Tema": (5.627, -0.012),
    "Lajja": (5.6, -0.15),
    
    # Ashanti
    "Kumasi": (6.668, -1.616),
    "Adum": (6.67, -1.62),
    "Bekwai": (6.44, -1.58),
    
    # Central
    "Cape Coast": (5.106, -1.247),
    "Sekondi-Takoradi": (4.900, -1.754),
    "Elmina": (5.088, -1.339),
    
    # Eastern
    "Koforidua": (6.0824, -0.2624),
    "Akyem": (5.98, -0.32),
    
    # Volta
    "Ho": (6.615, 0.487),
    "Keta": (5.925, 0.992),
    
    # Northern
    "Tamale": (9.281, -0.853),
    "Bolgatanga": (10.788, -0.832),
    
    # Upper East
    "Bolgatanga": (10.788, -0.832),
    "Navrongo": (10.897, -1.099),
}


def create_interactive_ghana_map(
    samples_df: pd.DataFrame, 
    ast_df: pd.DataFrame,
    title: str = "Ghana - Sample Locations & Resistance"
) -> pdk.Deck:
    """
    Create an interactive pydeck map of Ghana showing sample locations and resistance patterns.
    
    Args:
        samples_df: DataFrame with latitude, longitude, district, region columns
        ast_df: DataFrame with sample_id and resistance test results
        title: Title for the map
        
    Returns:
        pydeck Deck object
    """
    
    # Center of Ghana
    ghana_center = [7.3697, -5.6789]
    
    # Calculate resistance by location
    if 'latitude' in samples_df.columns and 'longitude' in samples_df.columns:
        # Remove rows with missing coordinates
        samples_clean = samples_df.dropna(subset=['latitude', 'longitude']).copy()
        
        if len(samples_clean) > 0:
            # Convert to numeric
            samples_clean['latitude'] = pd.to_numeric(samples_clean['latitude'], errors='coerce')
            samples_clean['longitude'] = pd.to_numeric(samples_clean['longitude'], errors='coerce')
            samples_clean = samples_clean.dropna(subset=['latitude', 'longitude'])
            
            # Merge with AST data
            sample_resistance = ast_df.groupby('sample_id').agg({
                'result': lambda x: {
                    'resistant': (x == 'R').sum(),
                    'total': len(x),
                    'rate': (x == 'R').sum() / len(x) * 100 if len(x) > 0 else 0
                }
            }).reset_index()
            
            # Extract resistance metrics
            sample_resistance[['resistant_count', 'total_count', 'resistance_rate']] = pd.DataFrame(
                sample_resistance['result'].apply(lambda x: [x['resistant'], x['total'], x['rate']]).tolist(),
                index=sample_resistance.index
            )
            sample_resistance = sample_resistance[['sample_id', 'resistant_count', 'total_count', 'resistance_rate']]
            
            # Merge with samples
            samples_with_resistance = samples_clean.merge(sample_resistance, left_on='sample_id', right_on='sample_id', how='left')
            samples_with_resistance['resistance_rate'] = samples_with_resistance['resistance_rate'].fillna(0)
            
            # Create color mapping based on resistance
            def get_color(resistance_rate):
                if resistance_rate > 50:
                    return [255, 50, 50, 255]  # Bright Red
                elif resistance_rate > 30:
                    return [255, 165, 0, 255]  # Orange
                else:
                    return [50, 200, 50, 255]  # Bright Green
            
            samples_with_resistance['color'] = samples_with_resistance['resistance_rate'].apply(get_color)
            
            # Add point size based on total tests
            samples_with_resistance['point_size'] = (samples_with_resistance['total_count'] * 3).clip(lower=100, upper=500)
            
            # Create tooltip data with proper formatting
            samples_with_resistance['tooltip_text'] = samples_with_resistance.apply(
                lambda row: f"District: {row.get('district', 'N/A')}\n"
                            f"Region: {row.get('region', 'N/A')}\n"
                            f"Tests: {int(row.get('total_count', 0))}\n"
                            f"Resistant: {int(row.get('resistant_count', 0))}\n"
                            f"Rate: {row.get('resistance_rate', 0):.1f}%",
                axis=1
            )
            
            # Create pydeck layer with improved settings
            layer = pdk.Layer(
                "ScatterplotLayer",
                data=samples_with_resistance,
                get_position=['longitude', 'latitude'],
                get_color='color',
                get_radius='point_size',
                pickable=True,
                auto_highlight=True,
                opacity=0.8,
                stroked=True,
                lineWidthScale=15,
                lineWidthMinPixels=2,
                lineWidthMaxPixels=10
            )
            
            # Create view state
            view_state = pdk.ViewState(
                latitude=ghana_center[0],
                longitude=ghana_center[1],
                zoom=6.5,
                bearing=0,
                pitch=20,
                min_zoom=5,
                max_zoom=15
            )
            
            # Create deck with proper map style
            return pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                tooltip={
                    "html": "<b style='font-size: 14px;'>{tooltip_text}</b>",
                    "style": {
                        "backgroundColor": "#ffffff",
                        "color": "#000000",
                        "padding": "10px",
                        "border-radius": "5px",
                        "border": "1px solid #ccc",
                        "font-family": "Arial"
                    }
                },
                map_style="mapbox://styles/mapbox/light-v10",
                mapbox_key="pk.eyJ1IjoibWFwYm94IiwiYSI6ImNpejY4NXVycTA2emYycW1qdm9wbXI5YW8ifQ.rJcFIG214AriISLbB6B5aw"
            )
    
    # Return empty deck if no location data
    view_state = pdk.ViewState(
        latitude=ghana_center[0],
        longitude=ghana_center[1],
        zoom=6,
    )
    return pdk.Deck(
        layers=[],
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/light-v10"
    )


def create_regional_resistance_heatmap(
    ast_df: pd.DataFrame,
    samples_df: pd.DataFrame
) -> pdk.Deck:
    """
    Create a heatmap showing resistance concentration by region using pydeck.
    
    Args:
        ast_df: AST results DataFrame
        samples_df: Samples DataFrame with region/district information
        
    Returns:
        pydeck Deck object
    """
    
    ghana_center = [7.3697, -5.6789]
    
    # Remove rows with missing coordinates
    samples_clean = samples_df.dropna(subset=['latitude', 'longitude']).copy()
    
    if len(samples_clean) > 0:
        # Calculate resistance by location
        region_resistance = ast_df.merge(
            samples_clean[['sample_id', 'latitude', 'longitude', 'region']],
            on='sample_id'
        ).copy()
        
        if len(region_resistance) > 0:
            region_resistance['is_resistant'] = (region_resistance['result'] == 'R').astype(int)
            
            # Ensure coordinates are numeric
            region_resistance['latitude'] = pd.to_numeric(region_resistance['latitude'], errors='coerce')
            region_resistance['longitude'] = pd.to_numeric(region_resistance['longitude'], errors='coerce')
            region_resistance = region_resistance.dropna(subset=['latitude', 'longitude'])
            
            # Group by location and calculate resistance
            location_stats = region_resistance.groupby(['latitude', 'longitude']).agg({
                'is_resistant': ['sum', 'count']
            }).reset_index()
            
            location_stats.columns = ['latitude', 'longitude', 'resistant_count', 'total_count']
            location_stats['resistance_rate'] = (location_stats['resistant_count'] / location_stats['total_count'] * 100)
            
            # Create ScatterplotLayer instead of HeatmapLayer for better visibility
            layer = pdk.Layer(
                "ScatterplotLayer",
                data=location_stats,
                get_position=['longitude', 'latitude'],
                get_color=[
                    'case',
                    ['>', ['get', 'resistance_rate'], 50], [255, 0, 0, 200],  # Red
                    ['>', ['get', 'resistance_rate'], 30], [255, 165, 0, 200],  # Orange
                    [0, 255, 0, 200]  # Green
                ],
                get_radius=200,
                pickable=True,
                auto_highlight=True,
            )
            
            view_state = pdk.ViewState(
                latitude=ghana_center[0],
                longitude=ghana_center[1],
                zoom=6,
            )
            
            return pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                tooltip={
                    "html": "<b>Location</b><br/>Region: {region}<br/>Resistance Rate: {resistance_rate:.1f}%<br/>Resistant: {resistant_count} / {total_count}",
                    "style": {"backgroundColor": "#f1f1f2", "color": "black"}
                },
                map_style="mapbox://styles/mapbox/light-v9"
            )
    
    # Return empty deck if no data
    view_state = pdk.ViewState(
        latitude=ghana_center[0],
        longitude=ghana_center[1],
        zoom=6,
    )
    return pdk.Deck(
        layers=[],
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/light-v9"
    )


def display_interactive_map_streamlit(samples_df: pd.DataFrame, ast_df: pd.DataFrame):
    """
    Display the interactive pydeck map in Streamlit.
    
    Args:
        samples_df: DataFrame with location data
        ast_df: AST results DataFrame
    """
    
    # Create the map
    ghana_map = create_interactive_ghana_map(samples_df, ast_df)
    
    # Display in Streamlit
    st.pydeck_chart(ghana_map, use_container_width=True)

