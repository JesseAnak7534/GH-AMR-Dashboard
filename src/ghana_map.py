"""
Enhanced interactive mapping module for Ghana with region and district labels.
Uses folium for interactive Leaflet maps with resistance pattern visualization.
"""
import pandas as pd
import numpy as np
import folium
from folium import plugins
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
) -> folium.Map:
    """
    Create an interactive Folium map of Ghana showing sample locations and resistance patterns.
    
    Args:
        samples_df: DataFrame with latitude, longitude, district, region columns
        ast_df: DataFrame with sample_id and resistance test results
        title: Title for the map
        
    Returns:
        folium.Map object that can be displayed in Streamlit
    """
    
    # Center of Ghana
    ghana_center = [7.3697, -5.6789]
    
    # Create base map
    m = folium.Map(
        location=ghana_center,
        zoom_start=7,
        tiles="OpenStreetMap",
        name="Base Layer"
    )
    
    # Add title via HTML
    title_html = '''
                 <div style="position: fixed; 
                     top: 10px; left: 50px; width: 300px; height: 60px; 
                     background-color: white; border:2px solid grey; z-index:9999; 
                     font-size: 16px; font-weight: bold; padding: 10px;
                     border-radius: 5px;">
                 📍 {} 
                 </div>
                 '''.format(title)
    m.get_root().html.add_child(folium.Element(title_html))
    
    # Calculate resistance by location
    if 'latitude' in samples_df.columns and 'longitude' in samples_df.columns:
        # Merge with AST data
        sample_resistance = ast_df.groupby('sample_id')['result'].apply(
            lambda x: (x == 'R').sum() / len(x) * 100 if len(x) > 0 else 0
        ).reset_index()
        sample_resistance.columns = ['sample_id', 'resistance_rate']
        
        # Merge with samples
        samples_with_resistance = samples_df.merge(sample_resistance, left_on='sample_id', right_on='sample_id', how='left')
        
        # Add markers for each location with district/region labels
        for idx, row in samples_with_resistance.iterrows():
            if pd.notna(row['latitude']) and pd.notna(row['longitude']):
                resistance_rate = row.get('resistance_rate', 0)
                
                # Color based on resistance
                if resistance_rate > 50:
                    color = 'red'
                    resistance_level = 'High'
                elif resistance_rate > 30:
                    color = 'orange'
                    resistance_level = 'Medium'
                else:
                    color = 'green'
                    resistance_level = 'Low'
                
                district = row.get('district', 'Unknown')
                region = row.get('region', 'Unknown')
                sample_id = row.get('sample_id', 'Unknown')
                
                popup_text = f"""
                <b>Sample ID:</b> {sample_id}<br>
                <b>District:</b> {district}<br>
                <b>Region:</b> {region}<br>
                <b>Resistance Rate:</b> {resistance_rate:.1f}%<br>
                <b>Level:</b> {resistance_level}
                """
                
                folium.CircleMarker(
                    location=[row['latitude'], row['longitude']],
                    radius=8 if resistance_rate > 50 else 6 if resistance_rate > 30 else 5,
                    popup=folium.Popup(popup_text, max_width=250),
                    color=color,
                    fill=True,
                    fillColor=color,
                    fillOpacity=0.7,
                    weight=2
                ).add_to(m)
    
    # Add region labels to map
    for region, (lat, lon) in GHANA_REGIONS.items():
        folium.Marker(
            location=[lat, lon],
            popup=f"<b>{region}</b> (Region)",
            icon=folium.Icon(color='blue', icon='info-sign', prefix='glyphicon'),
            tooltip=f"{region}",
        ).add_to(m)
    
    # Add district markers
    for district, (lat, lon) in GHANA_DISTRICTS.items():
        folium.Marker(
            location=[lat, lon],
            popup=f"<b>{district}</b> (District)",
            icon=folium.Icon(color='purple', icon='map-marker', prefix='glyphicon'),
            tooltip=f"{district}",
        ).add_to(m)
    
    # Add a legend
    legend_html = '''
                  <div style="position: fixed; 
                      bottom: 50px; right: 50px; width: 220px; 
                      background-color: white; border:2px solid grey; z-index:9999; 
                      font-size: 14px; padding: 10px; border-radius: 5px;">
                  <p style="margin: 0; font-weight: bold; text-decoration: underline;">
                  Resistance Levels
                  </p>
                  <p style="margin: 5px 0;">
                  <i class="fa fa-circle" style="color:red"></i> High (&gt;50%)
                  </p>
                  <p style="margin: 5px 0;">
                  <i class="fa fa-circle" style="color:orange"></i> Medium (30-50%)
                  </p>
                  <p style="margin: 5px 0;">
                  <i class="fa fa-circle" style="color:green"></i> Low (&lt;30%)
                  </p>
                  <p style="margin: 10px 0 0 0; font-weight: bold; font-size: 12px;">
                  🔵 Blue: Regions | 🟣 Purple: Districts
                  </p>
                  </div>
                  '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    return m


def create_regional_resistance_heatmap(
    ast_df: pd.DataFrame,
    samples_df: pd.DataFrame
) -> folium.Map:
    """
    Create a heatmap showing resistance concentration by region.
    
    Args:
        ast_df: AST results DataFrame
        samples_df: Samples DataFrame with region/district information
        
    Returns:
        folium.Map with heatmap layer
    """
    
    ghana_center = [7.3697, -5.6789]
    m = folium.Map(location=ghana_center, zoom_start=7)
    
    # Calculate resistance by region
    region_resistance = ast_df.merge(
        samples_df[['sample_id', 'latitude', 'longitude', 'region']],
        on='sample_id'
    ).copy()
    
    region_resistance['is_resistant'] = (region_resistance['result'] == 'R').astype(int)
    
    # Create heatmap data
    heat_data = []
    for idx, row in region_resistance.iterrows():
        if pd.notna(row['latitude']) and pd.notna(row['longitude']):
            # Intensity: 1 if resistant, 0.5 if susceptible
            intensity = 1 if row['is_resistant'] else 0.3
            heat_data.append([row['latitude'], row['longitude'], intensity])
    
    if heat_data:
        plugins.HeatMap(heat_data, radius=50, blur=15, max_zoom=1).add_to(m)
    
    return m


def display_interactive_map_streamlit(samples_df: pd.DataFrame, ast_df: pd.DataFrame):
    """
    Display the interactive Folium map in Streamlit using streamlit-folium.
    
    Args:
        samples_df: DataFrame with location data
        ast_df: AST results DataFrame
    """
    try:
        import streamlit_folium
        
        # Create the map
        ghana_map = create_interactive_ghana_map(samples_df, ast_df)
        
        # Display in Streamlit
        streamlit_folium.folium_static(ghana_map, width=1400, height=600)
        
    except ImportError:
        st.warning("⚠️ streamlit-folium not installed. Install with: pip install streamlit-folium")
        st.info("As an alternative, here's a summary of locations:")
        
        # Show as table
        if 'latitude' in samples_df.columns and 'longitude' in samples_df.columns:
            display_df = samples_df[['sample_id', 'district', 'region', 'latitude', 'longitude']].copy()
            st.dataframe(display_df, use_container_width=True)
