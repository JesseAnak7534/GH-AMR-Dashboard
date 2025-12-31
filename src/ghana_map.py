"""
Enhanced interactive mapping module for Ghana using Folium.
Displays sample locations and resistance patterns with clear, visible data points.
"""
import pandas as pd
import numpy as np
import folium
from folium.plugins import HeatMap, MarkerCluster
import streamlit as st
from typing import Optional


def create_interactive_ghana_map(
    samples_df: pd.DataFrame, 
    ast_df: pd.DataFrame,
    title: str = "Ghana - Sample Locations & Resistance"
) -> folium.Map:
    """
    Create an interactive Folium map of Ghana showing sample locations and resistance patterns.
    
    Args:
        samples_df: DataFrame with latitude, longitude, district, region columns
        ast_df: DataFrame with sample_id and resistance test results
        title: Title for the map
        
    Returns:
        folium.Map object
    """
    
    # Center of Ghana
    ghana_center = [7.3697, -5.6789]
    
    # Create base map
    m = folium.Map(
        location=ghana_center,
        zoom_start=6.5,
        tiles="OpenStreetMap",
        prefer_canvas=True
    )
    
    # Calculate resistance by location
    if 'latitude' in samples_df.columns and 'longitude' in samples_df.columns:
        # Remove rows with missing coordinates
        samples_clean = samples_df.dropna(subset=['latitude', 'longitude']).copy()
        
        if len(samples_clean) > 0:
            # Convert to numeric
            samples_clean['latitude'] = pd.to_numeric(samples_clean['latitude'], errors='coerce')
            samples_clean['longitude'] = pd.to_numeric(samples_clean['longitude'], errors='coerce')
            samples_clean = samples_clean.dropna(subset=['latitude', 'longitude'])
            
            # Merge with AST data to calculate resistance per sample
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
            
            # Add marker cluster group
            marker_cluster = MarkerCluster().add_to(m)
            
            # Add individual markers with color coding
            for idx, row in samples_with_resistance.iterrows():
                lat = row['latitude']
                lon = row['longitude']
                district = row.get('district', 'Unknown')
                region = row.get('region', 'Unknown')
                resist_rate = row.get('resistance_rate', 0)
                total_tests = int(row.get('total_count', 0))
                resistant_count = int(row.get('resistant_count', 0))
                
                # Determine color based on resistance rate
                if resist_rate > 50:
                    color = 'red'
                    icon_color = 'red'
                elif resist_rate > 30:
                    color = 'orange'
                    icon_color = 'orange'
                else:
                    color = 'green'
                    icon_color = 'green'
                
                # Create popup with detailed information
                popup_text = f"""
                <b>Sample Location</b><br>
                <b>District:</b> {district}<br>
                <b>Region:</b> {region}<br>
                <b>Tests:</b> {total_tests}<br>
                <b>Resistant:</b> {resistant_count}<br>
                <b>Resistance Rate:</b> {resist_rate:.1f}%
                """
                
                # Add circle marker with size based on test count
                radius = max(5, min(20, total_tests / 2))
                
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=radius,
                    popup=folium.Popup(popup_text, max_width=300),
                    color=color,
                    fill=True,
                    fillColor=color,
                    fillOpacity=0.7,
                    weight=2,
                    opacity=1.0,
                    tooltip=f"{district} - {resist_rate:.1f}% resistance"
                ).add_to(m)
            
            # Add a legend
            legend_html = '''
            <div style="position: fixed; 
                     top: 10px; right: 10px; width: 250px; height: auto; 
                     background-color: white; border:2px solid grey; z-index:9999; 
                     font-size:14px; padding: 10px; border-radius: 5px;">
                <p style="margin: 0 0 10px 0; font-weight: bold;">Resistance Legend</p>
                <p style="margin: 5px 0;"><span style="color: red; font-size: 18px;">●</span> High (>50%)</p>
                <p style="margin: 5px 0;"><span style="color: orange; font-size: 18px;">●</span> Medium (30-50%)</p>
                <p style="margin: 5px 0;"><span style="color: green; font-size: 18px;">●</span> Low (<30%)</p>
                <p style="margin: 10px 0 5px 0; font-size: 12px; color: #666;">
                  Circle size = number of tests
                </p>
            </div>
            '''
            m.get_root().html.add_child(folium.Element(legend_html))
    
    return m


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

