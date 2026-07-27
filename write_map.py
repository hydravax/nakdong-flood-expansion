
# write_map.py — interactive_map.py 재생성 스크립트
import os

CSS = """<style>
.main .block-container{padding-top:1rem;}
h1{color:#1E3A8A;font-size:28px;}
h2{font-size:20px;}
</style>"""

NET_OPTIONS = """{
  "interaction": {"dragNodes": true, "zoomView": true, "dragView": true},
  "layout": {"hierarchical": {"enabled": true, "direction": "UD",
             "sortMethod": "directed", "nodeSpacing": 160, "levelSeparation": 120}},
  "physics": {"enabled": false}
}"""

code = f'''import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import glob, os
import pandas as pd
from pyvis.network import Network
import streamlit.components.v1 as components

st.set_page_config(layout="wide", page_title="상류유역 시각화 시스템", page_icon="🌊")
st.markdown({repr(CSS)}, unsafe_allow_html=True)
st.title("🌊 낙동강유역 홍수특보 확대 대상 하천 검토")
st.markdown("수계 특성을 고려한 홍수예보 체계 마련 및 홍수특보 확대 대상 하천 검토")

DATA_DIR = "D:/RESEARCH/Nakdong"
WS_COLORS = {
    "낙동강": "#93c5fd", "낙동강동해": "#6ee7b7", "태화강": "#fde047",
    "형산강": "#c4b5fd", "회야수영강": "#f9a8d4", "기타": "#d1d5db"
}

@st.cache_data
def load_all_data():
    inf_files = glob.glob(os.path.join(DATA_DIR, "30_subbasin_*.inf"))
    watersheds_names = [os.path.basename(f).replace("30_subbasin_", "").replace(".inf", "") for f in inf_files]
    global_upstream_map = {}
    global_node_meta = {}
    special_nodes = set()
    gdf_basins_list, gdf_pts_list = [], []
    for ws in watersheds_names:
        inf_file = os.path.join(DATA_DIR, f"30_subbasin_{ws}.inf")
        try:
            with open(inf_file, encoding="euc-kr", errors="ignore") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 6 and parts[0].isdigit() and "#" in parts[2]:
                        code = parts[2]
                        name = parts[3].strip('"')
                        next_code = parts[4]
                        global_upstream_map.setdefault(next_code, []).append(code)
                        global_node_meta[code] = name
        except:
            pass
        basin_files = glob.glob(os.path.join(DATA_DIR, f"*유역도_{ws}.geojson")) or \
                      glob.glob(os.path.join(DATA_DIR, f"유역도_{ws}.geojson"))
        if basin_files:
            b = gpd.read_file(basin_files[0])
            if b.crs is None: b = b.set_crs(epsg=5186)
            b = b.to_crs(epsg=4326)
            b.geometry = b.geometry.simplify(0.001)
            b["watershed"] = ws
            gdf_basins_list.append(b)
        for tag, ptype in [("특보지점", "특보"), ("유역출구", "유역출구")]:
            flist = glob.glob(os.path.join(DATA_DIR, f"*_{ws}_{tag}.geojson"))
            if flist:
                p = gpd.read_file(flist[0])
                if p.crs is None: p = p.set_crs(epsg=5186)
                p = p.to_crs(epsg=4326)
                p["pt_type"] = ptype
                p["watershed"] = ws
                if ptype == "특보":
                    for _, row in p.iterrows():
                        special_nodes.add(row["desc"])
                gdf_pts_list.append(p)
    gdf_all_basins = gpd.GeoDataFrame(pd.concat(gdf_basins_list, ignore_index=True)) if gdf_basins_list else None
    gdf_all_pts = gpd.GeoDataFrame(pd.concat(gdf_pts_list, ignore_index=True)) if gdf_pts_list else None
    return global_upstream_map, global_node_meta, gdf_all_basins, gdf_all_pts, special_nodes

@st.cache_data
def load_rivers():
    rivers = []
    for rfile in ["낙동강_국가하천.geojson", "낙동강_지방하천.geojson"]:
        paths = glob.glob(os.path.join(DATA_DIR, rfile))
        if paths:
            gdf = gpd.read_file(paths[0])
            if gdf.crs is None: gdf = gdf.set_crs(epsg=5186)
            gdf = gdf.to_crs(epsg=4326)
            gdf.geometry = gdf.geometry.simplify(0.001)
            rivers.append(gdf)
    return rivers

def get_all_upstream(target_node, upstream_map):
    visited = set()
    def dfs(curr):
        visited.add(curr)
        for p in upstream_map.get(curr, []):
            if p not in visited:
                dfs(p)
    dfs(target_node)
    return visited

def draw_network_flowchart(target_node, upstream_set, upstream_map, node_metadata, special_nodes):
    if not upstream_set:
        return None
    net = Network(height="700px", width="100%", directed=True,
                  bgcolor="#ffffff", font_color="black", cdn_resources="remote")
    net.set_options("""{
      "interaction": {"dragNodes": true, "zoomView": true, "dragView": true},
      "layout": {"hierarchical": {"enabled": true, "direction": "UD",
                 "sortMethod": "directed", "nodeSpacing": 160, "levelSeparation": 120}},
      "physics": {"enabled": false}
    }""")
    added = set()
    def add_n(n):
        if n in added: return
        lbl = node_metadata.get(n, n)
        is_tgt = (n == target_node)
        is_sp = (n in special_nodes)
        red = is_tgt or is_sp
        net.add_node(n, label=lbl, shape="box",
            borderWidth=3 if is_tgt else (2 if red else 1),
            color={"background": "#fecaca" if red else "#f8fafc",
                   "border": "#b91c1c" if red else "#64748b",
                   "highlight": {"background": "#fca5a5", "border": "#991b1b"}},
            font={"color": "#b91c1c" if red else "black", "face": "Malgun Gothic"})
        added.add(n)
    queue = [target_node]
    add_n(target_node)
    seen_edges = set()
    while queue:
        curr = queue.pop(0)
        for p in upstream_map.get(curr, []):
            if p in upstream_set:
                add_n(p)
                eid = f"{p}_{curr}"
                if eid not in seen_edges:
                    net.add_edge(p, curr, arrows="to", color="#475569", width=1.5)
                    seen_edges.add(eid)
                    queue.append(p)
    try:
        return net.generate_html()
    except Exception as e:
        return f"<p>오류: {e}</p>"

# ── 데이터 로드 ──
upstream_map, node_metadata, gdf_all_basins, gdf_all_pts, special_nodes = load_all_data()
river_layers = load_rivers()

# ── 세션 초기화 ──
_defaults = {
    "sp_box_key": "선택 없음", "out_box_key": "선택 없음",
    "search_query": "", "map_clicked_node": None,
    "_clk_lat": None, "_clk_lng": None
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

col_side, col_map, col_graph = st.columns([1, 2.5, 1.5])

with col_side:
    st.subheader("🛠️ 설정")
    ws_choices = ["전체", "낙동강", "낙동강동해", "태화강", "형산강", "회야수영강"]
    selected_ws = st.selectbox("유역 선택", ws_choices)

    if selected_ws == "전체":
        disp_basins = gdf_all_basins
        disp_pts = gdf_all_pts
    else:
        disp_basins = gdf_all_basins[gdf_all_basins["watershed"] == selected_ws] if gdf_all_basins is not None else None
        disp_pts = gdf_all_pts[gdf_all_pts["watershed"] == selected_ws] if gdf_all_pts is not None else None

    sp_opts, out_opts = [], []
    if disp_pts is not None and not disp_pts.empty:
        for _, row in disp_pts.drop_duplicates(subset=["desc"]).iterrows():
            pfx = f"[{row['watershed']}] " if selected_ws == "전체" else ""
            lbl = f"{pfx}{row['Name']} ({row['desc']})"
            if row["pt_type"] == "특보":
                sp_opts.append(lbl)
            elif row["pt_type"] == "유역출구":
                out_opts.append(lbl)
        sp_opts.sort()
        out_opts.sort()

    def cb_sp():
        st.session_state.out_box_key = "선택 없음"
        st.session_state.search_query = ""
        st.session_state.map_clicked_node = None
        st.session_state["_clk_lat"] = None
        st.session_state["_clk_lng"] = None

    def cb_out():
        st.session_state.sp_box_key = "선택 없음"
        st.session_state.search_query = ""
        st.session_state.map_clicked_node = None
        st.session_state["_clk_lat"] = None
        st.session_state["_clk_lng"] = None

    def cb_search():
        st.session_state.sp_box_key = "선택 없음"
        st.session_state.out_box_key = "선택 없음"
        st.session_state.map_clicked_node = None
        st.session_state["_clk_lat"] = None
        st.session_state["_clk_lng"] = None

    st.selectbox("특보지점", ["선택 없음"] + sp_opts, key="sp_box_key", on_change=cb_sp)
    st.selectbox("유역출구", ["선택 없음"] + out_opts, key="out_box_key", on_change=cb_out)
    st.text_input("통합 검색 (지점명 또는 ID)", key="search_query",
                  placeholder="예: 200101#01", on_change=cb_search)

    # selected_node 결정 (우선순위: 지도클릭 > 검색 > 드롭다운)
    selected_node = None
    if st.session_state.map_clicked_node:
        selected_node = st.session_state.map_clicked_node
    elif st.session_state.search_query.strip():
        q = st.session_state.search_query.strip()
        if gdf_all_pts is not None:
            for _, row in gdf_all_pts.iterrows():
                if q in str(row["Name"]) or q in str(row["desc"]):
                    selected_node = row["desc"]
                    break
        if not selected_node:
            st.warning("검색 결과 없음")
    elif st.session_state.sp_box_key != "선택 없음":
        selected_node = st.session_state.sp_box_key.split("(")[-1].rstrip(")").strip()
    elif st.session_state.out_box_key != "선택 없음":
        selected_node = st.session_state.out_box_key.split("(")[-1].rstrip(")").strip()

    if selected_node:
        upstream_set = get_all_upstream(selected_node, upstream_map)
        nm = node_metadata.get(selected_node, selected_node)
        st.success(f"**{nm}** 위로 {len(upstream_set)}개 유역 연결됨")
        if not st.session_state.map_clicked_node and gdf_all_pts is not None:
            tgt = gdf_all_pts[gdf_all_pts["desc"] == selected_node]
            if not tgt.empty:
                st.session_state["fly_to_target"] = {
                    "center": [tgt.iloc[0].geometry.y, tgt.iloc[0].geometry.x],
                    "zoom": 12
                }
    else:
        upstream_set = set()

with col_map:
    st.subheader("🗺️ 대상 유역")
    if disp_basins is not None and not disp_basins.empty:
        fly_to = st.session_state.pop("fly_to_target", None)
        bounds = disp_basins.total_bounds
        default_center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
        center = fly_to["center"] if fly_to else st.session_state.get("map_center", default_center)
        zoom = fly_to["zoom"] if fly_to else st.session_state.get("map_zoom", 8 if selected_ws == "전체" else 9)

        m = folium.Map(location=center, zoom_start=zoom, tiles="CartoDB positron", zoomSnap=0.25)

        def style_fn(feature):
            fname = feature["properties"]["Name"]
            ws = feature["properties"].get("watershed", "기타")
            base = WS_COLORS.get(ws, "#d1d5db")
            if selected_node:
                if fname == selected_node:
                    return {"fillColor": "#dc2626", "color": "#991b1b", "weight": 2, "fillOpacity": 0.8}
                if fname in upstream_set:
                    return {"fillColor": "#f97316", "color": "#c2410c", "weight": 1.5, "fillOpacity": 0.6}
                return {"fillColor": base, "color": base, "weight": 0.8, "fillOpacity": 0.15}
            return {"fillColor": base, "color": "#475569", "weight": 1, "fillOpacity": 0.35}

        folium.GeoJson(
            disp_basins.to_json(), style_function=style_fn,
            tooltip=folium.GeoJsonTooltip(
                fields=["Name", "watershed", "desc"],
                aliases=["소유역:", "권역:", "지점:"]
            )
        ).add_to(m)

        for r_gdf in river_layers:
            if r_gdf is not None and not r_gdf.empty:
                folium.GeoJson(r_gdf.to_json(),
                    style_function=lambda x: {"color": "#0284c7", "weight": 1.2, "opacity": 0.7}
                ).add_to(m)

        if disp_pts is not None and not disp_pts.empty:
            for _, row in disp_pts.drop_duplicates(subset=["desc"]).iterrows():
                pt_id = row["desc"]
                pt_name = row["Name"]
                pt_type = row.get("pt_type", "지점")
                is_sel = (str(pt_id).strip() == str(selected_node).strip()) if selected_node else False

                if pt_type == "특보":
                    bc, sz, wt = "red", 4, 4
                else:
                    bc, sz, wt = "black", 3, 1
                if is_sel:
                    bc, sz, wt = "blue", 9, 5

                popup_content = f"<b>{pt_name}</b><br><small style='color:#555'>{pt_id}</small>"
                if is_sel:
                    popup_content += "<br><small style='color:blue'>✔ 선택됨</small>"

                folium.CircleMarker(
                    [row.geometry.y, row.geometry.x],
                    radius=sz,
                    popup=folium.Popup(popup_content, max_width=200),
                    tooltip=f"{pt_name} [{pt_type}] — 클릭하여 선택",
                    color=bc, weight=wt,
                    fill=True, fill_color="black", fill_opacity=1.0
                ).add_to(m)

        # ── last_object_clicked로 마커 클릭 감지 (공식 streamlit-folium 방식) ──
        st_data = st_folium(m, use_container_width=True, height=750,
                            returned_objects=["center", "zoom", "last_object_clicked"])

        if st_data:
            if st_data.get("center"):
                st.session_state["map_center"] = [
                    st_data["center"]["lat"], st_data["center"]["lng"]
                ]
            if st_data.get("zoom"):
                st.session_state["map_zoom"] = st_data["zoom"]

            clk = st_data.get("last_object_clicked")
            if clk and isinstance(clk, dict):
                clk_lat = clk.get("lat")
                clk_lng = clk.get("lng")
                prev_lat = st.session_state.get("_clk_lat")
                prev_lng = st.session_state.get("_clk_lng")

                # 새로운 클릭인 경우만 처리 (무한 rerun 방지)
                if clk_lat is not None and (clk_lat, clk_lng) != (prev_lat, prev_lng):
                    st.session_state["_clk_lat"] = clk_lat
                    st.session_state["_clk_lng"] = clk_lng

                    # 가장 가까운 마커 찾기 (전체 지점에서 검색)
                    min_d = float("inf")
                    nearest_id = None
                    if gdf_all_pts is not None:
                        for _, r in gdf_all_pts.iterrows():
                            d = ((r.geometry.y - clk_lat) ** 2 +
                                 (r.geometry.x - clk_lng) ** 2) ** 0.5
                            if d < min_d:
                                min_d = d
                                nearest_id = r["desc"]

                    # 임계값 0.005도 ≈ 약 500m 이내이면 마커 클릭으로 판단
                    if nearest_id and min_d < 0.005:
                        if st.session_state.map_clicked_node != nearest_id:
                            st.session_state.map_clicked_node = nearest_id
                            st.session_state.sp_box_key = "선택 없음"
                            st.session_state.out_box_key = "선택 없음"
                            st.session_state.search_query = ""
                            st.rerun()
    else:
        st.warning("공간 데이터 로딩에 실패했습니다.")

with col_graph:
    st.subheader("📊 유역 흐름도")
    if selected_node and len(upstream_set) > 0:
        html_str = draw_network_flowchart(
            selected_node, frozenset(upstream_set),
            upstream_map, node_metadata, frozenset(special_nodes)
        )
        if html_str:
            components.html(html_str, height=730, scrolling=False)
            st.caption("※ 마우스 휠: 줌인/아웃 | 바탕 드래그: 이동 | 상자 드래그: 재배치")
    elif selected_node:
        st.info("선택하신 지점은 최상단 지점입니다.")
    else:
        st.info("지도의 마커를 클릭하거나, 좌측 드롭다운으로 지점을 선택하면 유역흐름도가 표시됩니다.")
"""

target = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'interactive_map.py')
with open(target, 'w', encoding='utf-8') as f:
    f.write(code)
print(f"Written to: {target}")
print(f"Lines: {code.count(chr(10))}")
