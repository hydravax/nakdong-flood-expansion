import streamlit as st
import folium
from streamlit_folium import st_folium

st.write("Query Params:", st.query_params)

if "clicked_node" not in st.session_state:
    st.session_state.clicked_node = None

m = folium.Map(location=[35.5, 129.0], zoom_start=10)
html = """
<div style='white-space: nowrap;'>
    지점명: 형산강상류 
    <a href="/?node=test_node" target="_parent"><button>선택1(href)</button></a>
</div>
"""
folium.Marker(
    [35.5, 129.0], 
    popup=folium.Popup(html, max_width=300)
).add_to(m)

st_data = st_folium(m, height=400)
st.write("st_data:", st_data)
