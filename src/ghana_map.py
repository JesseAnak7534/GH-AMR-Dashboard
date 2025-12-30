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
) -> dict:
    """
    Create an interactive pydeck map of Ghana showing sample locations and resistance patterns.
    
    Args:
        samples_df: DataFrame with latitude, longitude, district, region columns
        ast_df: DataFrame with sample_id and resistance test results
        title: Title for the map
        
    Returns:
        pydeck chart specification dictionary
    """
    
    # Center of Ghana
    ghana_center = [7.3697, -5.6789]
    
    # Calculate resistance by location
    if 'latitude' in samples_df.columns and 'longitude' in samples_df.columns:
        # Merge with AST data
        sample_resistance = ast_df.groupby('sample_id')['result'].apply(
            lambda x: (x == 'R').sum() / len(x) * 100 if len(x) > 0 else 0
        ).reset_index()
        sample_resistance.columns = ['sample_id', 'resistance_rate']
        
        # Merge with samples
        samples_with_resistance = samples_df.merge(sample_resistance, left_on='sample_id', right_on='sample_id', how='left')
        samples_with_resistance['resistance_rate'] = samples_with_resistance['resistance_rate'].fillna(0)
        
        # Create color mapping based on resistance
        def get_color(resistance_rate):
            if resistance_rate > 50:
                return [255, 0, 0, 200]  # Red
            elif resistance_rate > 30:
                return [255, 165, 0, 200]  # Orange
            else:
                return [0, 255, 0, 200]  # Green
        
        samples_with_resistance['color'] = samples_with_resistance['resistance_rate'].apply(get_color)
        
        # Create pydeck layer
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=samples_with_resistance,
            get_position='[longitude, latitude]',
            get_color='color',
            get_radius=100,
            pickable=True,
        )
        
        # Create view state
        view_state = pdk.ViewState(
            latitude=ghana_center[0],
            longitude=ghana_center[1],
            zoom=7,
            bearing=0,
            pitch=0
        )
        
        # Create deck
        return pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            tooltip={"text": "{district}\n{region}\nResistance: {resistance_rate:.1f}%"}
        )
    else:
        # Return empty deck if no location data
        view_state = pdk.ViewState(
            latitude=ghana_center[0],
            longitude=ghana_center[1],
            zoom=7,
        )
        return pdk.Deck(layers=[], initial_view_state=view_state)


def create_regional_resistance_heatmap(
    ast_df: pd.DataFrame,
    samples_df: pd.DataFrame
):
    """
    Create a heatmap showing resistance concentration by region using pydeck.
    
    Args:
        ast_df: AST results DataFrame
        samples_df: Samples DataFrame with region/district information
        
    Returns:
        pydeck chart
    """
    
    ghana_center = [7.3697, -5.6789]
    
    # Calculate resistance by location
    region_resistance = ast_df.merge(
        samples_df[['sample_id', 'latitude', 'longitude', 'region']],
        on='sample_id'
    ).copy()
    
    region_resistance['is_resistant'] = (region_resistance['result'] == 'R').astype(int)
    
    # Group by location and calculate resistance
    location_stats = region_resistance.groupby(['latitude', 'longitude']).agg({
        'is_resistant': ['sum', 'count']
    }).reset_index()
    
    location_stats.columns = ['latitude', 'longitude', 'resistant_count', 'total_count']
    location_stats['resistance_rate'] = (location_stats['resistant_count'] / location_stats['total_count'] * 100)
    location_stats['color'] = location_stats['resistance_rate'].apply(
        lambda x: [255, 0, 0, 200] if x > 50 else [255, 165, 0, 200] if x > 30 else [0, 255, 0, 200]
    )
    
    # Create heatmap layer
    layer = pdk.Layer(
        "HeatmapLayer",
        data=location_stats,
        get_position='[longitude, latitude]',
        get_weight='resistance_rate',
        radius_pixels=50,
    )
    
    view_state = pdk.ViewState(
        latitude=ghana_center[0],
        longitude=ghana_center[1],
        zoom=7,
    )
    
    return pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={"text": "Resistance Rate: {resistance_rate:.1f}%"}
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

