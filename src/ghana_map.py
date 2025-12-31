"""
Enhanced interactive mapping module for Ghana using Folium.
Displays sample locations and resistance patterns with region names and clear, visible data points.
"""
import pandas as pd
import numpy as np
import folium
from folium.plugins import HeatMap, MarkerCluster
import streamlit as st
from typing import Optional


# Ghana Regions with approximate center coordinates
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


def create_interactive_ghana_map(
    samples_df: pd.DataFrame, 
    ast_df: pd.DataFrame,
    title: str = "Ghana - Sample Locations & Resistance"
) -> folium.Map:
    """
    Create an interactive Folium map of Ghana showing sample locations, region names, and resistance patterns.
    
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
    
    # Add region labels with markers
    for region_name, (lat, lon) in GHANA_REGIONS.items():
        folium.Marker(
            location=[lat, lon],
            popup=region_name,
            tooltip=region_name,
            icon=folium.Icon(
                icon='info-sign',
                color='blue',
                icon_color='white',
                prefix='glyphicon'
            )
        ).add_to(m)
        
        # Add region name label
        folium.Marker(
            location=[lat, lon],
            popup=None,
            icon=folium.DivIcon(
                html=f'''
                <div style="font-size: 11px; color: #0033cc; font-weight: bold; 
                            background-color: rgba(255, 255, 255, 0.8); 
                            padding: 2px 4px; border-radius: 3px; 
                            text-align: center; white-space: nowrap;">
                    {region_name}
                </div>
                '''
            )
        ).add_to(m)
    
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
            
            # Add marker cluster group for sample locations
            marker_cluster = MarkerCluster(name='Sample Locations').add_to(m)
            
            # Add individual markers with color coding
            for idx, row in samples_with_resistance.iterrows():
                lat = row['latitude']
                lon = row['longitude']
                district = row.get('district', 'Unknown')
                region = row.get('region', 'Unknown')
                resist_rate = row.get('resistance_rate', 0)
                total_tests = int(row.get('total_count', 0))
                resistant_count = int(row.get('resistant_count', 0))
                sample_id = row.get('sample_id', 'Unknown')
                
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
                <b>Sample ID:</b> {sample_id}<br>
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
                    tooltip=f"{district}, {region} - {resist_rate:.1f}% resistance ({total_tests} tests)"
                ).add_to(m)
            
            # Add a legend
            legend_html = '''
            <div style="position: fixed; 
                     bottom: 50px; right: 10px; width: 280px; height: auto; 
                     background-color: white; border:2px solid grey; z-index:9999; 
                     font-size:13px; padding: 12px; border-radius: 5px; box-shadow: 2px 2px 6px rgba(0,0,0,0.3);">
                <p style="margin: 0 0 12px 0; font-weight: bold; text-align: center; font-size: 14px;">Resistance Legend</p>
                <hr style="margin: 8px 0; border: none; border-top: 1px solid #ccc;">
                <p style="margin: 8px 0;"><span style="color: red; font-size: 16px;">●</span> <b>High</b> - >50% resistance</p>
                <p style="margin: 8px 0;"><span style="color: orange; font-size: 16px;">●</span> <b>Medium</b> - 30-50% resistance</p>
                <p style="margin: 8px 0;"><span style="color: green; font-size: 16px;">●</span> <b>Low</b> - <30% resistance</p>
                <hr style="margin: 8px 0; border: none; border-top: 1px solid #ccc;">
                <p style="margin: 8px 0 2px 0; font-size: 12px; color: #666;">
                  📍 <b>Blue markers</b> = Region centers<br>
                  ⭕ <b>Circle size</b> = Number of tests
                </p>
            </div>
            '''
            m.get_root().html.add_child(folium.Element(legend_html))
    
    return m

