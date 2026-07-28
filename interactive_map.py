import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import glob, os
import math
import pandas as pd
import re
from pyvis.network import Network
import streamlit.components.v1 as components

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


def _point_tooltip(point_name, point_id, point_type, status=None):
    """지도 클릭 결과에서 지점 ID를 손실 없이 회수할 수 있는 툴팁."""
    tooltip = f"{point_name} [{point_type}] · ID: {point_id}"
    return f"{tooltip} · {status}" if status else tooltip


def _clicked_node_from_event(clicked_object, clicked_tooltip, rendered_node_coords):
    """
    마커 툴팁에 심은 ID와 클릭 좌표가 같은 지점을 가리킬 때만 ID를 반환한다.

    streamlit-folium은 툴팁이 없는 폴리곤을 클릭하면 직전 툴팁 문자열을
    유지할 수 있다. 따라서 ID뿐 아니라 해당 마커 좌표와의 오차(30m 이내)
    도 함께 검증한다. 최근접 지점으로 대체하지는 않는다.
    """
    if not isinstance(clicked_object, dict) or not isinstance(clicked_tooltip, str):
        return None

    match = re.search(r"(?:^|[\s·>])ID:\s*([^\s·<]+)", clicked_tooltip)
    if not match:
        return None

    clicked_id = match.group(1).strip()
    marker_coords = rendered_node_coords.get(clicked_id)
    if marker_coords is None:
        return None

    try:
        click_lat = float(clicked_object["lat"])
        click_lng = float(clicked_object["lng"])
        marker_lat, marker_lng = marker_coords
    except (KeyError, TypeError, ValueError):
        return None

    mean_lat = math.radians((click_lat + marker_lat) / 2.0)
    dx_m = (click_lng - marker_lng) * 111_320.0 * math.cos(mean_lat)
    dy_m = (click_lat - marker_lat) * 110_574.0
    distance_m = math.hypot(dx_m, dy_m)
    return clicked_id if distance_m <= 30.0 else None


def _calc_css_dims_from_zoom_bounds(sw_lat, sw_lng, ne_lat, ne_lng, zoom):
    """
    Streamlit st_folium의 zoom + bounds 에서 실제 CSS 픽셀 크기 역산.
    (Leaflet 정확히 동일한 출력을 위해 사용)
    """
    import math
    TILE_SIZE = 256
    tiles = TILE_SIZE * (2.0 ** zoom)

    lng_diff = ne_lng - sw_lng
    css_w = lng_diff * tiles / 360.0

    def lat_to_merc(lat):
        return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    merc_diff = lat_to_merc(ne_lat) - lat_to_merc(sw_lat)
    css_h = merc_diff * tiles / (2 * math.pi)

    return max(200, int(round(css_w))), max(150, int(round(css_h)))


def get_high_res_tiff(m, dpi=(600, 600), bounds=None, zoom=None):
    """
    m: center/zoom/레이어가 세팅된 folium.Map 객체
    - zoom+bounds 로 Streamlit 콘테이너의 정확한 CSS px 크기를 역산
    - force-device-scale-factor=3으로 3배 해상도 캐트청
    - CSS 픽셀 레이아웃은 유지 → 마커 크기 동일
    """
    import tempfile, time, io
    from PIL import Image
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    DEVICE_SCALE = 3  # 3배 해상도

    css_w = 1200
    css_h = 900
    center_lat = 36.0
    center_lng = 128.4
    zoom_view = 8

    if bounds:
        try:
            sw_lat = bounds["_southWest"]["lat"]
            sw_lng = bounds["_southWest"]["lng"]
            ne_lat = bounds["_northEast"]["lat"]
            ne_lng = bounds["_northEast"]["lng"]
            center_lat = (sw_lat + ne_lat) / 2.0
            center_lng = (sw_lng + ne_lng) / 2.0
            if zoom is not None:
                zoom_view = zoom
                css_w, css_h = _calc_css_dims_from_zoom_bounds(
                    sw_lat, sw_lng, ne_lat, ne_lng, zoom
                )
                css_w = max(200, min(3000, css_w))
                css_h = max(150, min(3000, css_h))
        except Exception:
            pass

    # m을 HTML로 저장 (모든 레이어 포함)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
        m.save(tmp.name)
        tmp_path = tmp.name

    options = Options()
    options.add_argument("--headless")
    options.add_argument(f"--window-size={css_w},{css_h}")
    options.add_argument(f"--force-device-scale-factor={DEVICE_SCALE}")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    # JS: zoomSnap=0.01로 소수점 zoom 허용, setView로 정확한 븷 설정
    set_view_js = f"""
        for (var _k in window) {{
            try {{
                var _v = window[_k];
                if (_v && typeof _v === 'object' && _v.setView && _v.getZoom) {{
                    _v.options.zoomSnap = 0.01;
                    _v.setView([{center_lat}, {center_lng}], {zoom_view}, {{animate: false}});
                    break;
                }}
            }} catch(e) {{}}
        }}
    """

    try:
        driver = webdriver.Chrome(options=options)
        driver.get("file://" + tmp_path)
        time.sleep(2)  # Leaflet 초기화 대기
        driver.execute_script(set_view_js)
        time.sleep(4)  # 타일·마커 로딩 대기
        png_data = driver.get_screenshot_as_png()
        driver.quit()

        img = Image.open(io.BytesIO(png_data))
        out = io.BytesIO()
        img.save(out, format="TIFF", dpi=dpi)
        return out.getvalue()
    except Exception as e:
        import streamlit as st
        st.error(f"지도 저장 오류: {e}")
        return None
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)



@st.cache_data
def load_optimization_data():
    f1 = os.path.join(CURRENT_DIR, '최종_매개변수_SFM1_유역_20_낙동강_r1.xlsx')
    opt_dict = {}
    if os.path.exists(f1):
        try:
            xls1 = pd.ExcelFile(f1)
            for s in xls1.sheet_names:
                df = pd.read_excel(f1, sheet_name=s, header=1)
                for _, r in df.iterrows():
                    if pd.notna(r.get('bas_code')):
                        k1, k2 = r.get('bas_K_보정전'), r.get('bas_K_보정후')
                        t1, t2 = r.get('bas_Tl_보정전'), r.get('bas_Tl_보정후')
                        is_opt = (str(k1) != str(k2)) or (str(t1) != str(t2))
                        opt_dict[str(r['bas_code']).strip()] = is_opt
        except Exception as e:
            st.error(f"최적화 결과 로드 오류: {e}")
    return opt_dict

@st.cache_data
def load_performance_data():
    f_list = [x for x in glob.glob(os.path.join(CURRENT_DIR, '*04.xlsx')) if not os.path.basename(x).startswith('~')]
    perf_dict = {}
    reason_dict = {}  # 불가 사유 (Note 콼럼)
    if f_list:
        try:
            df = pd.read_excel(f_list[0], sheet_name=1, header=2, dtype=str)
            cols = df.columns.tolist()
            # 콼럼명이 깨져 있으니 위치 인덱스로 접근 지점=2, 종합판정=3, Note=-1
            for _, r in df.iterrows():
                name = r.iloc[2] if len(r) > 2 else None
                cat  = r.iloc[3] if len(r) > 3 else None
                note = r.iloc[-1] if len(r) > 1 else None
                if pd.notna(name) and pd.notna(cat):
                    perf_dict[str(name).strip()] = str(cat).strip()
                if pd.notna(name) and pd.notna(note) and str(note).strip() not in ('nan', ''):
                    reason_dict[str(name).strip()] = str(note).strip()
        except Exception as e:
            st.error(f"성능비교 결과 로드 오류: {e}")
    return perf_dict, reason_dict

st.set_page_config(layout="wide", page_title="낙동강유역 시각화 시스템", page_icon="🌊")
st.markdown(
    "<style>.main .block-container{padding-top:1rem;}h1{color:#1E3A8A;font-size:28px;}h2{font-size:20px;}</style>",
    unsafe_allow_html=True
)
st.markdown("""
<style>
/* 첫 번째 버튼(타이틀) 스타일 변경 */
[data-testid="stMain"] div.stButton:first-of-type > button {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    color: #1E3A8A !important;
    font-size: 28px !important;
    font-weight: bold !important;
    text-align: left !important;
    box-shadow: none !important;
    margin-bottom: 0px !important;
}
[data-testid="stMain"] div.stButton:first-of-type > button:hover {
    color: #3b82f6 !important;
}
[data-testid="stMain"] div.stButton:first-of-type > button p {
    font-size: 28px !important;
    font-weight: bold !important;
    margin: 0 !important;
}
</style>
""", unsafe_allow_html=True)

if st.button("낙동강유역", help="클릭하면 모든 선택이 초기화되고 처음 화면으로 돌아갑니다."):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

st.markdown("낙동강권역 홍수예보 체계 개선")

DATA_DIR = os.path.join(CURRENT_DIR, "input")
WS_COLORS = {
    "낙동강": "#93c5fd", "낙동강동해": "#6ee7b7", "태화강": "#fde047",
    "형산강": "#c4b5fd", "회야수영강": "#f9a8d4", "기타": "#d1d5db"
}

@st.cache_data
def load_all_data():
    # Cache invalidation trigger: 3
    inf_files = glob.glob(os.path.join(DATA_DIR, "30_subbasin_*.inf"))
    watersheds_names = [
        os.path.basename(f).replace("30_subbasin_", "").replace(".inf", "")
        for f in inf_files
    ]
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
        except Exception:
            pass

        GIS_DIR = os.path.join(DATA_DIR, "gis")
        basin_files = (
            glob.glob(os.path.join(GIS_DIR, f"*유역도_{ws}.geojson")) or
            glob.glob(os.path.join(GIS_DIR, f"유역도_{ws}.geojson"))
        )
        if basin_files:
            b = gpd.read_file(basin_files[0])
            if b.crs is None:
                b = b.set_crs(epsg=5186)
            b = b.to_crs(epsg=4326)
            b.geometry = b.geometry.simplify(0.001)
            b["watershed"] = ws
            gdf_basins_list.append(b)

        for tag, ptype in [("특보지점", "특보"), ("유역출구", "유역출구")]:
            flist = glob.glob(os.path.join(GIS_DIR, f"*_{ws}_{tag}.geojson"))
            if flist:
                p = gpd.read_file(flist[0])
                if p.crs is None:
                    p = p.set_crs(epsg=5186)
                p = p.to_crs(epsg=4326)
                p["pt_type"] = ptype
                p["watershed"] = ws
                for _, row in p.iterrows():
                    if ptype == "특보":
                        special_nodes.add(row["desc"])
                    if "Name" in row and "desc" in row:
                        global_node_meta[row["desc"]] = row["Name"]
                gdf_pts_list.append(p)

    gdf_all_basins = (
        gpd.GeoDataFrame(pd.concat(gdf_basins_list, ignore_index=True))
        if gdf_basins_list else None
    )
    gdf_all_pts = (
        gpd.GeoDataFrame(pd.concat(gdf_pts_list, ignore_index=True))
        if gdf_pts_list else None
    )
    return global_upstream_map, global_node_meta, gdf_all_basins, gdf_all_pts, special_nodes


@st.cache_data
def load_rivers():
    GIS_DIR = os.path.join(DATA_DIR, "gis")
    rivers = []
    for rfile in ["낙동강_국가하천.geojson", "낙동강_지방하천.geojson"]:
        paths = glob.glob(os.path.join(GIS_DIR, rfile))
        if paths:
            gdf = gpd.read_file(paths[0])
            if gdf.crs is None:
                gdf = gdf.set_crs(epsg=5186)
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

@st.cache_data
def get_all_special_boundaries(_disp_basins, _special_nodes, _upstream_map, selected_ws):
    if _disp_basins is None or _disp_basins.empty or not _special_nodes:
        return None
    
    geoms = []
    names = []
    
    for sp_node in _special_nodes:
        up_set = get_all_upstream(sp_node, _upstream_map)
        if not up_set:
            continue
            
        up_basins = _disp_basins[_disp_basins["Name"].isin(up_set)]
        if up_basins.empty:
            continue
            
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            buffered_geoms = up_basins.geometry.buffer(0.0015)
            if hasattr(buffered_geoms, 'union_all'):
                merged = buffered_geoms.union_all()
            else:
                merged = buffered_geoms.unary_union
            merged = merged.buffer(-0.0015)
            
        geoms.append(merged)
        names.append(sp_node)
        
    if geoms:
        return gpd.GeoDataFrame({"desc": names}, geometry=geoms, crs=_disp_basins.crs)
    return None

@st.cache_data
def get_watershed_boundary(_disp_basins, selected_ws):
    if _disp_basins is None or _disp_basins.empty:
        return None
        
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        buffered_geoms = _disp_basins.geometry.buffer(0.0015)
        if hasattr(buffered_geoms, 'union_all'):
            merged = buffered_geoms.union_all()
        else:
            merged = buffered_geoms.unary_union
        merged = merged.buffer(-0.0015)
        
    return gpd.GeoDataFrame(geometry=[merged], crs=_disp_basins.crs)

def draw_network_flowchart(target_node, upstream_set, upstream_map, node_metadata, special_nodes, map_mode, opt_dict, perf_dict):
    if not upstream_set:
        return None

    net = Network(
        height="1000px", width="100%", directed=True,
        bgcolor="#ffffff", font_color="black", cdn_resources="in_line"
    )
    net.set_options(
        '{"interaction":{"dragNodes":true,"zoomView":true,"dragView":true},'
        '"layout":{"hierarchical":{"enabled":true,"direction":"UD",'
        '"sortMethod":"directed","nodeSpacing":180,"levelSeparation":180}},'
        '"physics":{"enabled":false}}'
    )

    added = set()

    def add_n(n):
        if n in added:
            return
        lbl = node_metadata.get(n, n)
        is_tgt = (n == target_node)
        is_sp = (n in special_nodes)
        
        bg_col = "#f8fafc"
        brd_col = "#64748b"
        fnt_col = "black"
        brd_wt = 1
        
        is_opt = opt_dict.get(n, False)
        opt_str = "🟢최적화" if is_opt else "⚪기본값"
        
        cat = str(perf_dict.get(lbl, "일반지점")).strip()
        cat_emoji = "⚫"
        if cat == "개선": cat_emoji = "🟢"
        elif cat == "부분개선": cat_emoji = "🟡"
        elif cat == "변화없음": cat_emoji = "🟣"
        elif cat.startswith("불가"): cat_emoji = "🔴"
        
        sp_str = "🔴특보" if is_sp else "⚫일반"
        display_label = f"{lbl}\n{sp_str}\n──────\n{opt_str} | {cat_emoji}{cat}"
        tooltip_text = f"지점명: {lbl}\n구분: {'특보지점' if is_sp else '일반지점'}\n매개변수: {'최적화 수행' if is_opt else '기본값 유지'}\n성능비교: {cat}"
        
        if map_mode == "매개변수 최적화 수행결과":
            if is_opt:
                bg_col, brd_col, fnt_col = "#dcfce7", "#16a34a", "#166534"
            else:
                bg_col, brd_col, fnt_col = "#f1f5f9", "#94a3b8", "#475569"
        elif map_mode == "카테고리별 분류 (성능비교)":
            if cat == "개선":
                bg_col, brd_col, fnt_col = "#dcfce7", "#10b981", "#047857"
            elif cat == "부분개선":
                bg_col, brd_col, fnt_col = "#fef3c7", "#f59e0b", "#b45309"
            elif cat == "변화없음":
                bg_col, brd_col, fnt_col = "#f3e8ff", "#a855f7", "#7e22ce"
            elif cat.startswith("불가"):
                bg_col, brd_col, fnt_col = "#fee2e2", "#ef4444", "#b91c1c"
            else:
                bg_col, brd_col, fnt_col = "#f1f5f9", "#94a3b8", "#475569"
        else:
            if is_sp:
                bg_col, brd_col, fnt_col = "#fecaca", "#b91c1c", "#b91c1c"
                brd_wt = 2
                
        if is_tgt:
            brd_wt = 3
            brd_col = "#2563eb"
            
        net.add_node(
            n, label=display_label, shape="box", title=tooltip_text,
            borderWidth=brd_wt,
            color={
                "background": bg_col,
                "border": brd_col,
                "highlight": {"background": "#e2e8f0", "border": "#0f172a"}
            },
            font={"color": fnt_col, "face": "Malgun Gothic"}
        )
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
        html_str = net.generate_html()
        inject_html = """
<div id="btn-fit" style="
    position: absolute; 
    top: 10px; 
    right: 10px; 
    z-index: 9999; 
    background-color: white;
    border: 2px solid rgba(0,0,0,0.2);
    background-clip: padding-box;
    border-radius: 4px;
    padding: 5px 10px;
    cursor: pointer;
    font-family: 'Helvetica Neue', Arial, Helvetica, sans-serif;
    font-size: 12px;
    color: #333;
    box-shadow: 0 1px 5px rgba(0,0,0,0.65);
    display: flex;
    align-items: center;
    gap: 5px;
    user-select: none;
">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
    </svg>
    <span>화면맞춤</span>
</div>
<script type="text/javascript">
var btn = document.getElementById('btn-fit');
btn.onmouseover = function() {
    btn.style.backgroundColor = '#f4f4f4';
};
btn.onmouseout = function() {
    btn.style.backgroundColor = 'white';
};
btn.onclick = function(e) {
    e.stopPropagation();
    window.location.reload();
};
</script>
"""
        html_str = html_str.replace("</body>", inject_html + "</body>")
        return html_str
    except Exception as e:
        return f"<p>오류: {e}</p>"


# ── 데이터 로드 ──
upstream_map, node_metadata, gdf_all_basins, gdf_all_pts, special_nodes = load_all_data()
river_layers = load_rivers()
opt_dict = load_optimization_data()
perf_dict, reason_dict = load_performance_data()

# ── 세션 초기화 ──
for _k, _v in [
    ("sp_box_key", "선택 없음"), ("out_box_key", "선택 없음"),
    ("search_query", ""), ("map_clicked_node", None),
    ("_last_marker_click", None),
    ("_reset_widgets", False)
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

if st.session_state.get("_reset_widgets"):
    st.session_state["sp_box_key"] = "선택 없음"
    st.session_state["out_box_key"] = "선택 없음"
    st.session_state["search_query"] = ""
    st.session_state["_reset_widgets"] = False

col_side, col_map, col_graph = st.columns([1, 2.5, 1.5])

# ══════════════════════════════════════════
#  사이드바: 설정 및 지점 선택
# ══════════════════════════════════════════
with col_side:
    st.subheader("설정")

    ws_choices = ["전체", "낙동강", "낙동강동해", "태화강", "형산강", "회야수영강"]
    selected_ws = st.selectbox("유역 선택", ws_choices, index=1)

    if selected_ws == "전체":
        disp_basins = gdf_all_basins
        disp_pts = gdf_all_pts
    else:
        disp_basins = (
            gdf_all_basins[gdf_all_basins["watershed"] == selected_ws]
            if gdf_all_basins is not None else None
        )
        disp_pts = (
            gdf_all_pts[gdf_all_pts["watershed"] == selected_ws]
            if gdf_all_pts is not None else None
        )


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

    # on_change 콜백: 드롭다운/검색 사용 시 지도 클릭 초기화
    def cb_sp():
        st.session_state.out_box_key = "선택 없음"
        st.session_state.search_query = ""
        st.session_state.map_clicked_node = None
        st.session_state.pop("_last_marker_click", None)

    def cb_out():
        st.session_state.sp_box_key = "선택 없음"
        st.session_state.search_query = ""
        st.session_state.map_clicked_node = None
        st.session_state.pop("_last_marker_click", None)

    def cb_search():
        st.session_state.sp_box_key = "선택 없음"
        st.session_state.out_box_key = "선택 없음"
        st.session_state.map_clicked_node = None
        st.session_state.pop("_last_marker_click", None)

    st.selectbox("특보지점", ["선택 없음"] + sp_opts, key="sp_box_key", on_change=cb_sp)
    st.selectbox("유역출구", ["선택 없음"] + out_opts, key="out_box_key", on_change=cb_out)
    st.text_input(
        "통합 검색 (지점명 또는 ID)",
        key="search_query", placeholder="예: 200101#01", on_change=cb_search
    )

    # ── selected_node 결정 (우선순위: 지도클릭 > 검색 > 드롭다운) ──
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
        # 드롭다운/검색 선택 시 지도 Fly-To
        if not st.session_state.map_clicked_node and gdf_all_pts is not None:
            tgt = gdf_all_pts[gdf_all_pts["desc"] == selected_node]
            if not tgt.empty:
                st.session_state["fly_to_target"] = {
                    "center": [tgt.iloc[0].geometry.y, tgt.iloc[0].geometry.x],
                    "zoom": 12
                }
    else:
        upstream_set = set()

    # --- 지도 표시 옵션 & 동적 범례 렌더링 ---
    st.divider()
    map_mode = st.radio("지도 표시 옵션", ["기본 (특보/일반 지점)", "매개변수 최적화 수행결과", "카테고리별 분류 (성능비교)"])
    show_all_sp_bounds = st.checkbox("특보지점 유역 경계", value=False)
    active_pts = disp_pts
    if selected_node and len(upstream_set) > 0 and disp_pts is not None:
        active_pts = disp_pts[disp_pts["desc"].isin(upstream_set)]
    # 전체 지점 기준 카운트 (active_pts 블록 밖에서 항상 계산)
    if active_pts is not None and not active_pts.empty:
        unique_pts = active_pts["desc"].unique()
    elif disp_pts is not None and not disp_pts.empty:
        unique_pts = disp_pts["desc"].unique()
    else:
        unique_pts = []

    sp_cnt = sum(1 for pt_id in unique_pts if pt_id in special_nodes)
    gen_cnt = len(unique_pts) - sp_cnt
    opt_cnt = sum(1 for pt_id in unique_pts if opt_dict.get(pt_id, False))
    unopt_cnt = len(unique_pts) - opt_cnt
    opt_sp_cnt = sum(1 for pt_id in unique_pts if opt_dict.get(pt_id, False) and pt_id in special_nodes)
    unopt_sp_cnt = sp_cnt - opt_sp_cnt

    if active_pts is not None and not active_pts.empty:
        unique_names = active_pts.drop_duplicates(subset=["desc"])[["Name","desc"]]
        cat_counts = {
            "개선": 0, "부분개선": 0, "변화없음": 0,
            "재검토_1수위유량": 0, "재검토_2이상치": 0, "재검토_3본류": 0, "재검토_4조석": 0, "재검토_5댐보": 0, "재검토_기타": 0,
            "일반_최적화": 0, "일반_기본값": 0
        }
        for pt_name, pt_id in zip(unique_names["Name"], unique_names["desc"]):
            cat = perf_dict.get(pt_name, "일반지점").strip()
            note = reason_dict.get(pt_name, "")
            search_text = cat + " " + note
            if cat == "개선":
                cat_counts["개선"] += 1
            elif cat == "부분개선":
                cat_counts["부분개선"] += 1
            elif cat == "변화없음":
                cat_counts["변화없음"] += 1
            elif cat.startswith("불가") or cat.startswith("재검토"):
                if "수위" in search_text or "유량" in search_text or "모형" in search_text:
                    cat_counts["재검토_1수위유량"] += 1
                elif "이상치" in search_text or "결측" in search_text:
                    cat_counts["재검토_2이상치"] += 1
                elif "본류" in search_text:
                    cat_counts["재검토_3본류"] += 1
                elif "조석" in search_text:
                    cat_counts["재검토_4조석"] += 1
                elif "댐" in search_text or "보" in search_text or "운영" in search_text:
                    cat_counts["재검토_5댐보"] += 1
                else:
                    cat_counts["재검토_기타"] += 1
            else:
                is_opt = opt_dict.get(pt_id, False)
                if is_opt:
                    cat_counts["일반_최적화"] += 1
                else:
                    cat_counts["일반_기본값"] += 1
                
        # 타겟 노드 요약 정보 표시
        if selected_node:
            nm = node_metadata.get(selected_node, selected_node)
            tgt_cat = str(perf_dict.get(nm, "일반지점")).strip()
            cat_emoji = "⚫"
            if tgt_cat == "개선": cat_emoji = "🟢"
            elif tgt_cat == "부분개선": cat_emoji = "🟡"
            elif tgt_cat == "변화없음": cat_emoji = "🟣"
            elif tgt_cat.startswith("불가"): cat_emoji = "🔴"
            
            is_opt = opt_dict.get(selected_node, False)
            opt_str = "🟢최적화" if is_opt else "⚪기본값"
            
            st.info(
                f"**📌 [{nm}] 지점 요약**\n\n"
                f"**• 성능:** {cat_emoji} {tgt_cat} | **• 매개변수:** {opt_str}\n\n"
                f"**• 상류 지점 (총 {len(unique_pts)}개)** 중 최적화 완료: **{opt_cnt}개** (기본값: {unopt_cnt}개)"
            )
    else:
        cat_counts = {"개선": 0, "부분개선": 0, "변화없음": 0, "재검토_1수위유량": 0, "재검토_2이상치": 0, "재검토_3본류": 0, "재검토_4조석": 0, "재검토_5댐보": 0, "재검토_기타": 0, "일반_최적화": 0, "일반_기본값": 0}

    # 범례 (옵션별로 항상 표시)
    if map_mode == "기본 (특보/일반 지점)":
        st.markdown(f"🔴 특보지점 ({sp_cnt}개)<br>⚫ 일반지점 ({gen_cnt}개)", unsafe_allow_html=True)
    elif map_mode == "매개변수 최적화 수행결과":
        st.markdown(
            f"🟢 최적화 수행 지점 ({opt_cnt}개) | <span style='font-size:13px;color:#666'>특보 {opt_sp_cnt}개 포함</span><br>"
            f"🟠 기본값 유지 지점 ({unopt_cnt}개) | <span style='font-size:13px;color:#666'>특보 {unopt_sp_cnt}개 포함</span>", 
            unsafe_allow_html=True
        )
    elif map_mode == "카테고리별 분류 (성능비교)":
        total_bul = sum(cat_counts.get(k, 0) for k in ["재검토_1수위유량","재검토_2이상치","재검토_3본류","재검토_4조석","재검토_5댐보","재검토_기타"])
        total_gen = cat_counts["일반_최적화"] + cat_counts["일반_기본값"]
        st.markdown(
            f"🟢 개선 ({cat_counts['개선']}개)<br>"
            f"🟡 부분개선 ({cat_counts['부분개선']}개)<br>"
            f"🟣 변화없음 ({cat_counts['변화없음']}개)<br>"
            f"🔴 재검토 ({total_bul}개)<br>"
            f"<span style='font-size:11px;color:#888'>"
            f"&nbsp;&nbsp;① 수위-유량 곡선 ({cat_counts.get('재검토_1수위유량',0)}개)<br>"
            f"&nbsp;&nbsp;② 이상치/결측치 ({cat_counts.get('재검토_2이상치',0)}개)<br>"
            f"&nbsp;&nbsp;③ 본류(보운영) ({cat_counts.get('재검토_3본류',0)}개)<br>"
            f"&nbsp;&nbsp;④ 조석 ({cat_counts.get('재검토_4조석',0)}개)<br>"
            f"&nbsp;&nbsp;⑤ 댐/보 운영 ({cat_counts.get('재검토_5댐보',0)}개)"
            f"</span><br>"
            f"⚫ 일반지점 (총 {total_gen}개)<br>"
            f"<span style='font-size:11px;color:#888'>"
            f"&nbsp;&nbsp;🟢 최적화 수행 ({cat_counts['일반_최적화']}개)<br>"
            f"&nbsp;&nbsp;🟠 기본값 유지 ({cat_counts['일반_기본값']}개)"
            f"</span>",
            unsafe_allow_html=True
        )


# ══════════════════════════════════════════
#  지도 렌더링
# ══════════════════════════════════════════
with col_map:
    st.subheader("대상 유역")
    if disp_basins is not None and not disp_basins.empty:
        fly_to = st.session_state.pop("fly_to_target", None)
        bounds = disp_basins.total_bounds
        default_center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
        center = fly_to["center"] if fly_to else st.session_state.get("map_center", default_center)
        zoom = fly_to["zoom"] if fly_to else st.session_state.get(
            "map_zoom", 8 if selected_ws == "전체" else 9
        )

        m = folium.Map(
            location=center, zoom_start=zoom, tiles="CartoDB positron",
            zoomSnap=0.1,
            zoom_control=False,       # 확대/축소 버튼 숨기기
            attributionControl=False  # 기본 내장 attribution 숨기기
        )
        
        # Ctrl+휠 미세 줌: MacroElement로 지도 초기화 이후 JS 실행 보장
        from folium import MacroElement
        from jinja2 import Template
        _ctrl_zoom = MacroElement()
        
        bounds_arr = f"[[{bounds[1]}, {bounds[0]}], [{bounds[3]}, {bounds[2]}]]" if bounds is not None else "null"
        
        _ctrl_zoom._template = Template("""
            {% macro script(this, kwargs) %}
            (function() {
                var ctrlHeld = false;
                document.addEventListener('keydown', function(e) {
                    if (e.key === 'Control' || e.keyCode === 17) ctrlHeld = true;
                }, true);
                document.addEventListener('keyup', function(e) {
                    if (e.key === 'Control' || e.keyCode === 17) ctrlHeld = false;
                }, true);
                window.addEventListener('blur', function() { ctrlHeld = false; });

                var _map = {{ this._parent.get_name() }};
                
                var FitControl = L.Control.extend({
                    options: { position: 'topright' },
                    onAdd: function (map) {
                        var btn = L.DomUtil.create('button', 'fit-button');
                        btn.innerHTML = '🔄 화면맞춤';
                        btn.style.backgroundColor = 'white';
                        btn.style.border = '1px solid rgba(49, 51, 63, 0.2)';
                        btn.style.borderRadius = '0.5rem';
                        btn.style.padding = '0.25rem 0.75rem';
                        btn.style.color = 'rgb(49, 51, 63)';
                        btn.style.fontFamily = '"Source Sans Pro", sans-serif';
                        btn.style.fontSize = '14px';
                        btn.style.fontWeight = '400';
                        btn.style.cursor = 'pointer';
                        btn.style.boxShadow = 'rgba(0, 0, 0, 0.05) 0px 1px 2px 0px';
                        btn.style.margin = '10px';
                        
                        btn.onmouseover = function() {
                            btn.style.borderColor = 'rgb(255, 75, 75)';
                            btn.style.color = 'rgb(255, 75, 75)';
                        };
                        btn.onmouseout = function() {
                            btn.style.borderColor = 'rgba(49, 51, 63, 0.2)';
                            btn.style.color = 'rgb(49, 51, 63)';
                        };
                        
                        L.DomEvent.disableClickPropagation(btn);
                        L.DomEvent.on(btn, 'click', function (e) {
                            var b = __BOUNDS_PLACEHOLDER__;
                            if(b) map.fitBounds(b);
                        });
                        return btn;
                    }
                });
                _map.addControl(new FitControl());
                
                _map.scrollWheelZoom.disable();
                _map.getContainer().addEventListener('wheel', function(e) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    var fine = ctrlHeld || e.ctrlKey || e.metaKey;
                    var delta = e.deltaY > 0 ? -1 : 1;
                    if (fine) delta = e.deltaY > 0 ? -0.1 : 0.1;
                    _map.setZoom(_map.getZoom() + delta);
                }, { passive: false, capture: true });
                
                // 1. 축척표기 (Scale bar) - 우측 하단
                L.control.scale({position: 'bottomright', metric: true, imperial: false}).addTo(_map);

                // 2. 방위각 (Compass Rose) - 좌측 상단
                var compass = L.control({position: 'topleft'});
                compass.onAdd = function(map) {
                    var div = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
                    div.style.backgroundColor = 'rgba(255, 255, 255, 0.8)';
                    div.style.padding = '5px';
                    div.style.textAlign = 'center';
                    div.style.lineHeight = '1.2';
                    div.style.fontWeight = 'bold';
                    div.style.color = '#333';
                    // 심플한 나침반 화살표 아이콘
                    div.innerHTML = '<span style="font-size:14px;color:red;">N</span><br><span style="font-size:18px;">▲</span>';
                    return div;
                };
                compass.addTo(_map);

                // 3. 지도 바깥 위경도 축(Axes) 및 4면 Box 구현
                var graticuleLayer = L.layerGroup().addTo(_map);
                
                var mapDiv = _map.getContainer();
                
                // 1) 상단 마스크 (Top Axis)
                var topAxis = document.createElement("div");
                topAxis.style.position = "absolute"; topAxis.style.left = "0px"; topAxis.style.top = "0px";
                topAxis.style.width = "100%"; topAxis.style.height = "15px";
                topAxis.style.backgroundColor = "white"; topAxis.style.zIndex = "9999";
                mapDiv.appendChild(topAxis);

                // 2) 우측 마스크 (Right Axis)
                var rightAxis = document.createElement("div");
                rightAxis.style.position = "absolute"; rightAxis.style.right = "0px"; rightAxis.style.top = "0px";
                rightAxis.style.width = "15px"; rightAxis.style.height = "100%";
                rightAxis.style.backgroundColor = "white"; rightAxis.style.zIndex = "9999";
                mapDiv.appendChild(rightAxis);

                // 3) 좌측 마스크 (Left Axis)
                var leftAxis = document.createElement("div");
                leftAxis.style.position = "absolute"; leftAxis.style.left = "0px"; leftAxis.style.top = "0px";
                leftAxis.style.width = "45px"; leftAxis.style.height = "100%";
                leftAxis.style.backgroundColor = "white"; leftAxis.style.zIndex = "9999";
                mapDiv.appendChild(leftAxis);

                // 4) 하단 마스크 (Bottom Axis)
                var bottomAxis = document.createElement("div");
                bottomAxis.style.position = "absolute"; bottomAxis.style.left = "0px"; bottomAxis.style.bottom = "0px";
                bottomAxis.style.width = "100%"; bottomAxis.style.height = "25px";
                bottomAxis.style.backgroundColor = "white"; bottomAxis.style.zIndex = "9999";
                mapDiv.appendChild(bottomAxis);

                // 지도 영역 테두리 박스 (Inner Box)
                var innerBox = document.createElement("div");
                innerBox.style.position = "absolute";
                innerBox.style.left = "45px"; innerBox.style.right = "15px";
                innerBox.style.top = "15px"; innerBox.style.bottom = "25px";
                innerBox.style.border = "2px solid #555";
                innerBox.style.pointerEvents = "none"; // 클릭 통과
                innerBox.style.zIndex = "9999";
                mapDiv.appendChild(innerBox);

                // 방위각과 축척표기가 마스크에 가려지지 않도록 위치 조정
                var compassDiv = compass.getContainer();
                if(compassDiv) { 
                    compassDiv.style.marginLeft = "50px"; 
                    compassDiv.style.marginTop = "20px"; 
                }
                
                var scaleDivs = document.getElementsByClassName("leaflet-control-scale");
                if(scaleDivs.length > 0) { 
                    scaleDivs[0].style.marginRight = "20px"; 
                    scaleDivs[0].style.marginBottom = "30px"; 
                }

                function drawGraticule() {
                    graticuleLayer.clearLayers();
                    // 레이블 초기화
                    var axes = [leftAxis, bottomAxis, rightAxis, topAxis];
                    axes.forEach(function(axis) {
                        var lbls = axis.getElementsByClassName("graticule-lbl");
                        while(lbls.length > 0) { lbls[0].parentNode.removeChild(lbls[0]); }
                    });
                    
                    var bounds = _map.getBounds();
                    var minLat = Math.floor(bounds.getSouth());
                    var maxLat = Math.ceil(bounds.getNorth());
                    var minLng = Math.floor(bounds.getWest());
                    var maxLng = Math.ceil(bounds.getEast());

                    var lineStyle = {color: '#555', weight: 1, dashArray: '4, 4', opacity: 0.6, interactive: false};

                    // 위도선 및 테두리 (좌측 라벨, 우측 틱)
                    for (var lat = minLat; lat <= maxLat; lat++) {
                        L.polyline([[lat, -180], [lat, 180]], lineStyle).addTo(graticuleLayer);
                        
                        var y = _map.latLngToContainerPoint([lat, 0]).y;
                        if(y >= 15 && y <= mapDiv.clientHeight - 25) {
                            // 좌측 라벨 (위경도 텍스트)
                            var lbl = document.createElement("div");
                            lbl.className = "graticule-lbl";
                            lbl.style.position = "absolute"; lbl.style.right = "5px"; lbl.style.top = (y - 8) + "px";
                            lbl.style.fontSize = "12px"; lbl.style.fontWeight = "bold"; lbl.style.color = "#333";
                            lbl.innerText = lat + "°N";
                            leftAxis.appendChild(lbl);
                            
                            // 우측 틱 (선만 표시)
                            var tick = document.createElement("div");
                            tick.className = "graticule-lbl";
                            tick.style.position = "absolute"; tick.style.left = "0px"; tick.style.top = y + "px";
                            tick.style.width = "5px"; tick.style.height = "2px"; tick.style.backgroundColor = "#555";
                            rightAxis.appendChild(tick);
                        }
                    }
                    
                    // 경도선 및 테두리 (하단 라벨, 상단 틱)
                    for (var lng = minLng; lng <= maxLng; lng++) {
                        L.polyline([[-90, lng], [90, lng]], lineStyle).addTo(graticuleLayer);
                        
                        var x = _map.latLngToContainerPoint([0, lng]).x;
                        if(x >= 45 && x <= mapDiv.clientWidth - 15) {
                            // 하단 라벨 (위경도 텍스트)
                            var lbl = document.createElement("div");
                            lbl.className = "graticule-lbl";
                            lbl.style.position = "absolute"; lbl.style.left = (x - 15) + "px"; lbl.style.top = "5px";
                            lbl.style.fontSize = "12px"; lbl.style.fontWeight = "bold"; lbl.style.color = "#333";
                            lbl.innerText = lng + "°E";
                            bottomAxis.appendChild(lbl);
                            
                            // 상단 틱 (선만 표시)
                            var tick = document.createElement("div");
                            tick.className = "graticule-lbl";
                            tick.style.position = "absolute"; tick.style.left = x + "px"; tick.style.bottom = "0px";
                            tick.style.width = "2px"; tick.style.height = "5px"; tick.style.backgroundColor = "#555";
                            topAxis.appendChild(tick);
                        }
                    }
                }

                _map.on('move moveend zoom zoomend resize', drawGraticule);
                setTimeout(drawGraticule, 100);
            })();
            {% endmacro %}
        """.replace("__BOUNDS_PLACEHOLDER__", bounds_arr))
        m.add_child(_ctrl_zoom)


        def style_fn(feature):
            ws = feature["properties"].get("watershed", "미상")
            base = WS_COLORS.get(ws, "#d1d5db")
            return {"fillColor": base, "color": "transparent", "weight": 0, "fillOpacity": 0.2}
        folium.GeoJson(
            disp_basins.to_json(),
            style_function=style_fn,
            interactive=False
        ).add_to(m)
        
        # (2) 현재 선택된 유역(들)의 최외곽 경계선 (두꺼운 테두리)
        watershed_bound_gdf = get_watershed_boundary(disp_basins, selected_ws)
        if watershed_bound_gdf is not None and not watershed_bound_gdf.empty:
            folium.GeoJson(
                watershed_bound_gdf.to_json(),
                style_function=lambda x: {
                    "fillColor": "none",
                    "color": "#ff0000", # 빨간색 (전체 유역 경계)
                    "weight": 3,
                    "opacity": 0.9,
                },
                name="유역 최외곽 경계",
                tooltip="선택된 유역 전체 범위"
            ).add_to(m)
        
        # (3) 모든 특보지점의 개별 상류유역 경계선 (옵션 켰을 때 표출)
        if show_all_sp_bounds:
            all_sp_bounds_gdf = get_all_special_boundaries(disp_basins, special_nodes, upstream_map, selected_ws)
            if all_sp_bounds_gdf is not None and not all_sp_bounds_gdf.empty:
                folium.GeoJson(
                    all_sp_bounds_gdf.to_json(),
                    style_function=lambda x: {
                        "fillColor": "none",
                        "color": "#ff0000", # 빨간색
                        "weight": 1.5, # 얇게
                        "opacity": 0.9,
                        "dashArray": "3, 6" # 얇은 점선 스타일
                    },
                    name="특보지점 개별 상류유역",
                    tooltip=folium.GeoJsonTooltip(
                        fields=["desc"],
                        aliases=["특보지점 ID:"]
                    )
                ).add_to(m)

        # (4) 현재 사용자가 선택한(클릭/검색) 지점의 상류 유역 경계선
        if selected_node and len(upstream_set) > 0:
            upstream_basins = disp_basins[disp_basins["Name"].isin(upstream_set)]
            if not upstream_basins.empty:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    buffered_geoms = upstream_basins.geometry.buffer(0.0015)
                    if hasattr(buffered_geoms, 'union_all'):
                        merged_geom = buffered_geoms.union_all()
                    else:
                        merged_geom = buffered_geoms.unary_union
                    merged_geom = merged_geom.buffer(-0.0015)
                
                merged_gdf = gpd.GeoDataFrame(geometry=[merged_geom], crs=disp_basins.crs)
                folium.GeoJson(
                    merged_gdf.to_json(),
                    style_function=lambda x: {
                        "fillColor": "none",
                        "color": "#ff0000", # 빨간색
                        "weight": 3,
                        "opacity": 1.0,
                        "dashArray": "4, 6" # 점선 스타일
                    },
                    tooltip="상류 유역 전체 경계"
                ).add_to(m)

        for r_gdf in river_layers:
            if r_gdf is not None and not r_gdf.empty:
                folium.GeoJson(
                    r_gdf.to_json(),
                    style_function=lambda x: {"color": "#38bdf8", "weight": 1.0, "opacity": 0.5},
                    name="하천망"
                ).add_to(m)

        if disp_pts is not None and not disp_pts.empty:
            pts_to_render = disp_pts.drop_duplicates(subset=["desc"]).copy()
            if "pt_type" not in pts_to_render.columns:
                pts_to_render["pt_type"] = "지점"
            pts_to_render["_is_sp"] = pts_to_render["pt_type"] == "특보"
            pts_to_render = pts_to_render.sort_values("_is_sp")
            
            # iterrows 대신 zip 활용하여 속도 대폭 향상
            pt_ids = pts_to_render["desc"].tolist()
            pt_names = pts_to_render["Name"].tolist()
            pt_types = pts_to_render["pt_type"].tolist()
            lats = pts_to_render.geometry.y.tolist()
            lngs = pts_to_render.geometry.x.tolist()
            rendered_node_coords = {
                str(pt_id).strip(): (float(lat), float(lng))
                for pt_id, lat, lng in zip(pt_ids, lats, lngs)
            }

            for pt_id, pt_name, pt_type, lat, lng in zip(pt_ids, pt_names, pt_types, lats, lngs):
                pt_id = str(pt_id).strip()
                is_sel = (str(pt_id).strip() == str(selected_node).strip()) if selected_node else False
                is_special = (pt_type == "특보")
                
                # 사전(Dictionary) 조회 최적화 (루프 내 1회만 조회)
                is_opt = opt_dict.get(pt_id, False) if map_mode != "기본 (특보/일반 지점)" else False
                cat = perf_dict.get(pt_name, "일반지점") if map_mode == "카테고리별 분류 (성능비교)" else None
                note = reason_dict.get(pt_name, "") if map_mode == "카테고리별 분류 (성능비교)" else None

                # Set default styles
                bc, sz, wt, fc = "black", 3, 1, "black"
                
                if map_mode == "매개변수 최적화 수행결과":
                    sz_gen = 5 if is_special else (4 if is_opt else 3)
                    if is_opt:
                        bc, sz, wt, fc = ("black" if is_special else "#16a34a"), sz_gen, (1.5 if is_special else 2), "#16a34a"  # 초록
                    else:
                        bc, sz, wt, fc = ("black" if is_special else "#f97316"), sz_gen, (1.5 if is_special else 1.5), "#f97316"  # 주황색
                elif map_mode == "카테고리별 분류 (성능비교)":
                    base_sz = 8.5 if is_special else 5  # 특보지점 20% 더 크게
                    if cat == "개선":
                        bc, sz, wt, fc = ("black" if is_special else "#16a34a"), base_sz, (1.5 if is_special else 2), "#16a34a"
                    elif cat == "부분개선":
                        bc, sz, wt, fc = ("black" if is_special else "#f59e0b"), base_sz, (1.5 if is_special else 2), "#f59e0b"
                    elif cat == "변화없음":
                        bc, sz, wt, fc = ("black" if is_special else "#a855f7"), base_sz, (1.5 if is_special else 2), "#a855f7"
                    elif str(cat).startswith("불가") or str(cat).startswith("재검토"):
                        bc, sz, wt, fc = ("black" if is_special else "#ef4444"), base_sz, (1.5 if is_special else 2), "#ef4444"
                    else:
                        sz_gen = 5 if is_special else 3
                        if is_opt:
                            bc, sz, wt, fc = ("black" if is_special else "#16a34a"), sz_gen, 1.5, "#16a34a"  # 최적화
                        else:
                            bc, sz, wt, fc = ("black" if is_special else "#f97316"), sz_gen, 1.5, "#f97316"  # 기본값
                else: # 기본
                    if is_special:
                        bc, sz, wt, fc = "black", 5, 1.5, "red"
                    else:
                        bc, sz, wt, fc = "black", 3, 1, "black"

                # 재검토 사유 기반 원문자 심볼 (카테고리 모드에서만 적용)
                불가_symbol = None
                if map_mode == "카테고리별 분류 (성능비교)" and (str(cat).startswith("불가") or str(cat).startswith("재검토")):
                    search_text = str(cat) + " " + note
                    if "수위" in search_text or "유량" in search_text or "모형" in search_text:
                        불가_symbol = "①"
                    elif "이상치" in search_text or "결측" in search_text:
                        불가_symbol = "②"
                    elif "본류" in search_text:
                        불가_symbol = "③"
                    elif "조석" in search_text:
                        불가_symbol = "④"
                    elif "댐" in search_text or "보" in search_text or "운영" in search_text:
                        불가_symbol = "⑤"
                    else:
                        불가_symbol = "●"

                if is_sel:
                    # 선택된 노드는 특별한 애니메이션 DivIcon으로 렌더링 (깜빡임 효과)
                    icon_html = f"""
                    <div style="
                        width: 20px;
                        height: 20px;
                        background-color: red;
                        border-radius: 50%;
                        border: 3px solid white;
                        box-shadow: 0 0 15px 5px rgba(255,0,0,0.8);
                        animation: pulse 1s infinite alternate;
                    "></div>
                    <style>
                        @keyframes pulse {{
                            0% {{ transform: scale(0.8); box-shadow: 0 0 5px 2px rgba(255,0,0,0.5); }}
                            100% {{ transform: scale(1.5); box-shadow: 0 0 20px 8px rgba(255,0,0,0.9); }}
                        }}
                    </style>
                    """
                    folium.Marker(
                        [lat, lng],
                        icon=folium.DivIcon(html=icon_html),
                        tooltip=_point_tooltip(pt_name, pt_id, pt_type, "선택됨")
                    ).add_to(m)
                elif 불가_symbol:
                    # 재검토 지점: 원문자 DivIcon 마커
                    icon_sz = 22 if is_special else 15
                    font_sz = 12 if is_special else 9
                    border_css = "border:1.5px solid black;" if is_special else "border:2px solid white;"
                    icon_html = (
                        f"<div style='"
                        f"width:{icon_sz}px;height:{icon_sz}px;"
                        f"background:{fc};border-radius:50%;"
                        f"{border_css}"
                        f"color:white;text-align:center;"
                        f"line-height:{icon_sz-3}px;"
                        f"font-weight:bold;font-size:{font_sz}px;"
                        f"box-shadow:0 0 3px rgba(0,0,0,0.4);"
                        f"'>{불가_symbol}</div>"
                    )
                    folium.Marker(
                        [lat, lng],
                        icon=folium.DivIcon(
                            html=icon_html,
                            icon_size=(icon_sz, icon_sz),
                            icon_anchor=(icon_sz//2, icon_sz//2)
                        ),
                        tooltip=_point_tooltip(pt_name, pt_id, pt_type)
                    ).add_to(m)
                else:
                    folium.CircleMarker(
                        [lat, lng],
                        radius=sz,
                        tooltip=_point_tooltip(pt_name, pt_id, pt_type),
                        color=bc, weight=wt,
                        fill=True, fill_color=fc, fill_opacity=1.0
                    ).add_to(m)
        else:
            rendered_node_coords = {}

        def on_map_change():
            """컴포넌트 재실행 전에 마커 선택을 세션 상태에 반영한다."""
            map_event = st.session_state.get("target_watershed_map", {})
            if not isinstance(map_event, dict):
                return

            clicked_object = map_event.get("last_object_clicked")
            clicked_tooltip = map_event.get("last_object_clicked_tooltip")
            clicked_id = _clicked_node_from_event(
                clicked_object, clicked_tooltip, rendered_node_coords
            )
            if not clicked_id:
                return

            click_signature = (
                clicked_id,
                clicked_object.get("lat"),
                clicked_object.get("lng"),
            )
            if click_signature == st.session_state.get("_last_marker_click"):
                return

            st.session_state["_last_marker_click"] = click_signature
            st.session_state["map_clicked_node"] = clicked_id
            st.session_state["_reset_widgets"] = True

            marker_lat, marker_lng = rendered_node_coords[clicked_id]
            st.session_state["fly_to_target"] = {
                "center": [marker_lat, marker_lng],
                "zoom": 12
            }

        # 지도 바탕(last_clicked)이 아닌 ID가 포함된 마커 클릭만 선택으로 처리한다.
        st_data = st_folium(
            m, use_container_width=True, height=1000,
            returned_objects=[
                "center", "zoom", "bounds",
                "last_object_clicked", "last_object_clicked_tooltip"
            ],
            key="target_watershed_map",
            on_change=on_map_change
        )

        if st_data:
            if st_data.get("center"):
                st.session_state["map_center"] = [
                    st_data["center"]["lat"], st_data["center"]["lng"]
                ]
            if st_data.get("zoom"):
                st.session_state["map_zoom"] = st_data["zoom"]
            if st_data.get("bounds"):
                st.session_state["map_bounds"] = st_data["bounds"]
    else:
        st.warning("공간 데이터 로딩에 실패했습니다.")

# ══════════════════════════════════════════
#  지도 내보내기 (TIFF)
# ══════════════════════════════════════════
with col_side:
    st.markdown("---")
    
    if disp_basins is not None and not disp_basins.empty:
        tb = disp_basins.total_bounds
        fallback_b = {
            "_southWest": {"lat": tb[1], "lng": tb[0]},
            "_northEast": {"lat": tb[3], "lng": tb[2]}
        }
    else:
        fallback_b = {
            "_southWest": {"lat": 34.0, "lng": 127.0},
            "_northEast": {"lat": 37.0, "lng": 130.0}
        }
    
    b = st.session_state.get("map_bounds") or fallback_b

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("TIFF 저장", help="현재 보이는 화면 영역 기준으로 고해상도 이미지를 생성합니다."):
            with st.spinner("이미지 생성 중..."):
                cur_bounds = st.session_state.get("map_bounds") or fallback_b
                cur_zoom   = st.session_state.get("map_zoom")
                tiff_data = get_high_res_tiff(m, bounds=cur_bounds, zoom=cur_zoom)
                if tiff_data:
                    st.session_state["tiff_data"] = tiff_data

    with col_btn2:
        if "tiff_data" in st.session_state:
            st.download_button(
                label="다운로드",
                data=st.session_state["tiff_data"],
                file_name="nakdong_map_600dpi.tiff",
                mime="image/tiff"
            )




# ══════════════════════════════════════════
#  유역 흐름도
# ══════════════════════════════════════════
with col_graph:
    st.subheader("유역 흐름도")
    if selected_node and len(upstream_set) > 0:
        html_str = draw_network_flowchart(
            selected_node, frozenset(upstream_set),
            upstream_map, node_metadata, frozenset(special_nodes),
            map_mode, opt_dict, perf_dict
        )
        if html_str:
            components.html(html_str, height=1000, scrolling=False)
    elif selected_node:
        st.info("선택하신 지점은 최상단 지점입니다.")
