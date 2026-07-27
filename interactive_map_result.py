import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import glob
import os
import pandas as pd
from pyvis.network import Network
import streamlit.components.v1 as components
from urllib.parse import quote, unquote

# Streamlit 기본 설정
st.set_page_config(layout="wide", page_title="예측 잠재력을 고려한 홍수특보지점 확대 검토", page_icon="📈")

# CSS 커스텀 디자인
st.markdown("""
<style>
    .main .block-container {
        padding-top: 1rem;
    }
    h1 { color: #1E3A8A; font-size: 28px; }
    h2 { font-size: 20px; }
</style>
""", unsafe_allow_html=True)

st.title("📈 예측 잠재력을 고려한 홍수특보지점 확대 검토")

DATA_DIR = "D:/RESEARCH/Nakdong"

# 각 권역별 대분류 고유 컬러 (기본 컬러)
WS_COLORS = {
    "낙동강": "#f1f5f9",        
    "낙동강동해": "#f1f5f9",    
    "태화강": "#f1f5f9",        
    "형산강": "#f1f5f9",        
    "회야수영강": "#f1f5f9",    
    "기타": "#f1f5f9"
}

@st.cache_data
def load_eval_data():
    eval_file = os.path.join(DATA_DIR, "성능비교Q&T_03.xlsx")
    if os.path.exists(eval_file):
        df = pd.read_excel(eval_file, sheet_name='비교결과', header=2)
        # 키와 값 모두 공백 제거하여 매칭 확률 높임
        df['지점'] = df['지점'].astype(str).str.strip()
        df['종합판정'] = df['종합판정'].astype(str).str.strip()
        eval_dict = dict(zip(df['지점'], df['종합판정']))
        return eval_dict
    return {}

@st.cache_data
def load_param_data():
    param_files = glob.glob(os.path.join(DATA_DIR, "매개변수비교", "*_매개변수비교.xlsx"))
    opt_dict = {}
    for f in param_files:
        try:
            df = pd.read_excel(f)
            for _, row in df.iterrows():
                code = str(row['지점코드']).strip()
                amc = row.get('AMC_변화량', 0)
                bk = row.get('bas_K_변화량', 0)
                btl = row.get('bas_Tl_변화량', 0)
                if amc != 0 or bk != 0 or btl != 0:
                    opt_dict[code] = "최적화 지점"
                else:
                    opt_dict[code] = "default 지점"
        except Exception:
            pass
    return opt_dict

@st.cache_data
def load_all_data():
    inf_files = glob.glob(os.path.join(DATA_DIR, "30_subbasin_*.inf"))
    watersheds_names = [os.path.basename(f).replace("30_subbasin_", "").replace(".inf", "") for f in inf_files]
    
    global_upstream_map = {}
    global_node_meta = {}
    special_nodes = set()
    
    gdf_basins_list = []
    gdf_pts_list = []
    
    for ws in watersheds_names:
        inf_file = os.path.join(DATA_DIR, f"30_subbasin_{ws}.inf")
        try:
            with open(inf_file, encoding='euc-kr', errors='ignore') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 6 and parts[0].isdigit() and '#' in parts[2]:
                        code = parts[2]
                        name = parts[3].strip('"')
                        next_code = parts[4]
                        
                        if next_code not in global_upstream_map:
                            global_upstream_map[next_code] = []
                        global_upstream_map[next_code].append(code)
                        global_node_meta[code] = name
        except:
            pass
            
        basin_files = glob.glob(os.path.join(DATA_DIR, f"*유역도_{ws}.geojson"))
        if not basin_files:
            basin_files = glob.glob(os.path.join(DATA_DIR, f"유역도_{ws}.geojson"))
        if basin_files:
            b_gdf = gpd.read_file(basin_files[0])
            if b_gdf.crs is None: b_gdf = b_gdf.set_crs(epsg=5186)
            b_gdf = b_gdf.to_crs(epsg=4326)
            b_gdf.geometry = b_gdf.geometry.simplify(0.001)
            b_gdf['watershed'] = ws
            gdf_basins_list.append(b_gdf)
            
        pts_files_1 = glob.glob(os.path.join(DATA_DIR, f"*_{ws}_특보지점.geojson"))
        pts_files_2 = glob.glob(os.path.join(DATA_DIR, f"*_{ws}_유역출구.geojson"))
        
        if pts_files_1:
            p_gdf1 = gpd.read_file(pts_files_1[0])
            if p_gdf1.crs is None: p_gdf1 = p_gdf1.set_crs(epsg=5186)
            p_gdf1 = p_gdf1.to_crs(epsg=4326)
            p_gdf1['pt_type'] = '특보'
            p_gdf1['watershed'] = ws
            for idx, row in p_gdf1.iterrows():
                special_nodes.add(row['desc'])
            gdf_pts_list.append(p_gdf1)
        
        if pts_files_2:
            p_gdf2 = gpd.read_file(pts_files_2[0])
            if p_gdf2.crs is None: p_gdf2 = p_gdf2.set_crs(epsg=5186)
            p_gdf2 = p_gdf2.to_crs(epsg=4326)
            p_gdf2['pt_type'] = '유역출구'
            p_gdf2['watershed'] = ws
            gdf_pts_list.append(p_gdf2)

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

@st.cache_data
def get_all_upstream(target_node, upstream_map):
    visited = set()
    def dfs(curr):
        visited.add(curr)
        for parent in upstream_map.get(curr, []):
            if parent not in visited:
                dfs(parent)
    dfs(target_node)
    return visited

@st.cache_data
def get_geojson_data(data_id, _gdf):
    """지리 데이터를 JSON 문자열로 변환하여 캐싱 (속도 향상)"""
    if _gdf is None or _gdf.empty:
        return None
    return _gdf.to_json()

@st.cache_data
def draw_network_flowchart(target_node, upstream_set, upstream_map, node_metadata, special_nodes, eval_dict, map_mode, param_dict):
    if not upstream_set:
        return None
        
    net = Network(height='700px', width='100%', directed=True, bgcolor="#ffffff", font_color="black", cdn_resources='remote')
    
    net.set_options("""
    var options = {
      "interaction": {
        "dragNodes": true,
        "zoomView": true,
        "dragView": true
      },
      "layout": {
        "hierarchical": {
          "enabled": true,
          "direction": "UD",
          "sortMethod": "directed",
          "nodeSpacing": 160,
          "levelSeparation": 120
        }
      },
      "physics": {
        "enabled": false
      }
    }
    """)
    
    added_nodes = set()
    
    def add_n(n):
        if n not in added_nodes:
            lbl = node_metadata.get(n, n)
            is_target = (n == target_node)
            is_special = (n in special_nodes)
            
            # 모드별 노드 색상
            if map_mode == "매개변수비교":
                p_status = param_dict.get(n, "default 지점")
                if p_status == "최적화 지점": bg, border = ("#ffedd5", "#ea580c")
                else: bg, border = ("#f8fafc", "#94a3b8")
            elif map_mode == "최적화결과":
                eval_status = eval_dict.get(lbl, "평가없음")
                if eval_status == "개선": bg, border = "#dcfce7", "#16a34a"
                elif eval_status == "부분개선": bg, border = "#fef08a", "#ca8a04"
                elif eval_status in ["불가", "불가(본류)", "불가(조석)"]: bg, border = "#fee2e2", "#ef4444"
                elif eval_status == "변화없음": bg, border = "#f3f4f6", "#6b7280"
                else: bg, border = "#f8fafc", "#94a3b8"
            else:
                bg, border = ("#ffe4e6", "#e11d48") if is_special else ("#f8fafc", "#94a3b8")
            
            font_col = "#000000"
            bwidth = 4 if is_target else 2
            
            # 타겟 노드일 경우 가장 두꺼운 파란 외곽선 부여
            if is_target:
                border = "#1d4ed8"
            
            net.add_node(n, label=lbl, shape="box",
                         borderWidth=bwidth,
                         color={"background": bg, "border": border, 
                                "highlight": {"background": "#cbd5e1", "border": "#334155"}},
                         font={"color": font_col, "face": "Malgun Gothic", "bold": "true"})
            added_nodes.add(n)

    queue = [target_node]
    add_n(target_node)
    visited_edges = set()
    
    while queue:
        curr = queue.pop(0)
        for parent in upstream_map.get(curr, []):
            if parent in upstream_set:
                add_n(parent)
                edge_id = f"{parent}_{curr}"
                if edge_id not in visited_edges:
                    net.add_edge(parent, curr, arrows='to', color='#475569', width=1.5)
                    visited_edges.add(edge_id)
                    queue.append(parent)
                    
    try:
        html = net.generate_html()
        if "network = new vis.Network" in html:
            click_script = """
            network.on("click", function(params) {
                if (params.nodes && params.nodes.length > 0) {
                    var clickedNode = params.nodes[0];
                    var targetUrl = window.location.origin + "/?node=" + encodeURIComponent(clickedNode);
                    var link = document.createElement("a");
                    link.href = targetUrl;
                    link.target = "_top";
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                }
            });
            """
            html = html.replace(
                "network = new vis.Network(container, data, options);",
                "network = new vis.Network(container, data, options);\n" + click_script
            )
        return html
    except Exception as e:
        return f"<p>Error generating chart: {e}</p>"

# =============== 메인 UI ===============
col_side, col_map, col_graph = st.columns([1, 2.5, 1.5])

# 쿼리 파라미터 연동 (URL 디코딩: %23 → #)
query_node_raw = st.query_params.get("node")
query_node = unquote(query_node_raw) if query_node_raw else None
if query_node:
    if st.session_state.get("map_clicked_node") != query_node:
        st.session_state["map_clicked_node"] = query_node
        st.session_state.search_query = ""
        st.session_state.sp_box_key = "선택 없음"
        st.session_state.out_box_key = "선택 없음"

with col_side:
    st.subheader("🛠️ 분석 설정")
    
    with st.spinner('전체 수계 공간 및 엑셀 평가결과 로딩 중...'):
        upstream_map, node_metadata, gdf_all_basins, gdf_all_pts, special_nodes = load_all_data()
        river_layers = load_rivers()
        eval_dict = load_eval_data()
        param_dict = load_param_data()
        
    # 0. 시각화 모드 선택
    map_mode = st.radio(
        "시각화 모드",
        options=["총 지점", "매개변수비교", "최적화결과"],
        index=0,
        horizontal=True
    )
        
    # 1. 수계 필터링 및 기초 데이터 준비
    ws_choices = ["전체", "낙동강", "낙동강동해", "태화강", "형산강", "회야수영강"]
    selected_ws = st.selectbox("유역 선택", ws_choices)
    
    if selected_ws == "전체":
        disp_basins = gdf_all_basins
        disp_pts = gdf_all_pts
    else:
        disp_basins = gdf_all_basins[gdf_all_basins['watershed'] == selected_ws] if gdf_all_basins is not None else None
        disp_pts = gdf_all_pts[gdf_all_pts['watershed'] == selected_ws] if gdf_all_pts is not None else None

    # 2. 통계 및 필터링용 데이터 사전 계산
    unique_pts = disp_pts.drop_duplicates(subset=['desc']) if disp_pts is not None else pd.DataFrame()
    tot_cnt = len(unique_pts)
    sp_cnt = sum(1 for _, r in unique_pts.iterrows() if r['desc'] in special_nodes)
    out_cnt = tot_cnt - sp_cnt
    
    # 평가 결과 통계 (성공한 30개 지점 식별용)
    success_evals = {"개선", "부분개선"}
    success_sp_ids = set()
    sp_eval = {}
    for _, r in unique_pts.iterrows():
        if r['desc'] in special_nodes:
            name = str(r['Name']).strip()
            ev = eval_dict.get(name, "평가없음")
            sp_eval[ev] = sp_eval.get(ev, 0) + 1
            if ev in success_evals:
                success_sp_ids.add(r['desc'])


    # 3. 매개변수 최적화 상태(param_dict) 롤백/필터링 로직
    # 성공한 특보지점(30개) 계통만 "최적화 지점" 유지, 나머지는 "기본값"
    final_optimized_nodes = set()
    for sid in success_sp_ids:
        final_optimized_nodes.update(get_all_upstream(sid, upstream_map))
    
    # param_dict 업데이트
    for node_code in list(param_dict.keys()):
        code_str = str(node_code).strip()
        is_sp = code_str in special_nodes
        
        # 1. 성공한 유역 계통에 속해야 함 (관련 지점)
        in_success_basin = code_str in final_optimized_nodes
        
        # 2. 특보지점인 경우, 본인의 평가 결과가 성공(개선/부분개선)이어야만 최종 최적화로 인정
        #    (실패한 특보지점은 비록 성공지점의 상류라 하더라도 기본값으로 롤백됨)
        local_success = True
        if is_sp:
            name = node_metadata.get(code_str, "").strip()
            local_success = (eval_dict.get(name) in success_evals)
            
        if in_success_basin and local_success and param_dict[node_code] == "최적화 지점":
            param_dict[node_code] = "최적화 지점"
        else:
            param_dict[node_code] = "default 지점"

    # 4. 필터링된 통계 재계산 (param_dict 변경 후)
    opt_cnt = sum(1 for _, r in unique_pts.iterrows() if param_dict.get(str(r['desc']).strip()) == "최적화 지점")
    def_cnt = tot_cnt - opt_cnt
    opt_sp_cnt = sum(1 for _, r in unique_pts.iterrows() if param_dict.get(str(r['desc']).strip()) == "최적화 지점" and r['desc'] in special_nodes)
    def_sp_cnt = sp_cnt - opt_sp_cnt

    # 5. 드롭다운 옵션 준비
    sp_opts = []
    out_opts = []
    if not unique_pts.empty:
        for _, row in unique_pts.iterrows():
            pt_id = row['desc']
            pt_name = row['Name']
            pt_type = row.get('pt_type', '지점')
            w_name = row.get('watershed', '기타')
            prefix = f"[{w_name}] " if selected_ws == "전체" else ""
            label_text = f"{prefix}{pt_name} ({pt_id})"
            if pt_type == '특보':
                sp_opts.append(label_text)
            elif pt_type == '유역출구':
                out_opts.append(label_text)
        sp_opts.sort()
        out_opts.sort()

    # 세션에 옵션 리스트 저장
    if "sp_box_key" not in st.session_state: st.session_state.sp_box_key = "선택 없음"
    if "out_box_key" not in st.session_state: st.session_state.out_box_key = "선택 없음"
    if "search_query" not in st.session_state: st.session_state.search_query = ""

    # 드롭다운 widget 정의 (on_change 콜백으로 다른 선택 초기화)
    def cb_sp():
        st.session_state.out_box_key = "선택 없음"
        st.session_state.search_query = ""
        st.session_state["map_clicked_node"] = None

    def cb_out():
        st.session_state.sp_box_key = "선택 없음"
        st.session_state.search_query = ""
        st.session_state["map_clicked_node"] = None

    def cb_search():
        st.session_state.sp_box_key = "선택 없음"
        st.session_state.out_box_key = "선택 없음"
        st.session_state["map_clicked_node"] = None

    st.selectbox("특보지점", ["선택 없음"] + sp_opts, key="sp_box_key", on_change=cb_sp)
    st.selectbox("일반지점", ["선택 없음"] + out_opts, key="out_box_key", on_change=cb_out)
    st.text_input("통합 검색 (지점 검색 창)", key="search_query", placeholder="지점명 또는 ID (예: 200101#01)", on_change=cb_search)

    # ── selected_node 결정 (우선순위: map_clicked_node > 검색창 > 드롭다운) ──
    selected_node = None
    
    if st.session_state.get('map_clicked_node'):
        selected_node = st.session_state['map_clicked_node']
    elif st.session_state.search_query.strip() != "":
        q = st.session_state.search_query.strip()
        matched = False
        if gdf_all_pts is not None and not gdf_all_pts.empty:
            for idx, row in gdf_all_pts.iterrows():
                if q in row['Name'] or q in str(row['desc']):
                    selected_node = row['desc']
                    matched = True
                    break
        if not matched:
            st.warning("경고: 입력하신 검색어와 일치하는 지점이 없습니다.")
    elif st.session_state.sp_box_key != "선택 없음":
        selected_node = st.session_state.sp_box_key.split('(')[-1].replace(')', '').strip()
    elif st.session_state.out_box_key != "선택 없음":
        selected_node = st.session_state.out_box_key.split('(')[-1].replace(')', '').strip()

    if selected_node:
        upstream_set = get_all_upstream(selected_node, upstream_map)
        st.success(f"**{node_metadata.get(selected_node, selected_node)}** 위로 {len(upstream_set)}개의 유역이 연결되어 있습니다.")
        
        # 드롭다운/검색으로 선택 시 지도 Fly-To
        if not st.session_state.get('map_clicked_node'):
            target_pt = gdf_all_pts[gdf_all_pts['desc'] == selected_node]
            if not target_pt.empty:
                lat = target_pt.iloc[0].geometry.y
                lon = target_pt.iloc[0].geometry.x
                st.session_state["fly_to_target"] = {"center": [lat, lon], "zoom": 12}
    else:
        upstream_set = set()

# === 메인 맵 랜더링 ===
with col_map:
    st.subheader("🗺️ 대상 유역 / 지점")
    
    if disp_pts is not None and not disp_pts.empty:
        # 중복 마커 제거 (특보이면서 유역출구인 경우 등)
        unique_pts = disp_pts.drop_duplicates(subset=['desc'])
        # (상단에서 이미 계산된 통계 변수 활용: tot_cnt, sp_cnt, out_cnt, opt_cnt, sp_eval 등)
        st.markdown(f"**[ {map_mode} ]** 총 지점: {tot_cnt}개")
        
        # 1. 모드별 필터 UI 분기
        mode_filters = {} # {label: bool}
        
        if map_mode == "총 지점":
            st.markdown("**지점유형 필터**")
            col_t1, col_t2 = st.columns(2)
            show_sp = col_t1.checkbox(f"🔴 특보지점 ({sp_cnt}개)", value=True, key="filter_sp_main")
            show_norm = col_t2.checkbox(f"⚫ 일반지점 ({out_cnt}개)", value=True, key="filter_norm_main")
            # 다른 모드 필터는 기본 True 처리
            mode_filters = {'최적화': True, '기본값': True}
            
        elif map_mode == "매개변수비교":
            st.markdown("**매개변수 필터**")
            c1, c2 = st.columns(2)
            mode_filters['최적화'] = c1.checkbox(f"🟠 최적화 {opt_cnt}개 (특보 {opt_sp_cnt}개)", value=True)
            mode_filters['기본값'] = c2.checkbox(f"⚫ 기본값 {def_cnt}개 (특보 {def_sp_cnt}개)", value=True)
            # 지점유형은 모두 표시
            show_sp = show_norm = True
            
        else:  # 최적화결과
            no_eval_cnt = tot_cnt - sum(1 for _, r in unique_pts.iterrows() if eval_dict.get(r['Name'].strip(), "평가없음") != "평가없음")
            st.markdown(f"**평가결과 필터** (특보지점 {sp_cnt}개 대상)")
            c1, c2, c3, c4 = st.columns(4)
            mode_filters['개선'] = c1.checkbox(f"🟢 개선 ({sp_eval.get('개선',0)})", value=True)
            mode_filters['부분개선'] = c2.checkbox(f"🟡 부분개선 ({sp_eval.get('부분개선',0)})", value=True)
            mode_filters['변화없음'] = c3.checkbox(f"⚪ 변화없음 ({sp_eval.get('변화없음',0)})", value=True)
            mode_filters['평가없음'] = c4.checkbox(f"⚫ 일반지점 ({no_eval_cnt})", value=True)
            c5, c6, c7 = st.columns(3)
            mode_filters['불가'] = c5.checkbox(f"🔴 불가 ({sp_eval.get('불가',0)})", value=True)
            mode_filters['불가(본류)'] = c6.checkbox(f"🔴 불가(본류) ({sp_eval.get('불가(본류)',0)})", value=True)
            mode_filters['불가(조석)'] = c7.checkbox(f"🔴 불가(조석) ({sp_eval.get('불가(조석)',0)})", value=True)
            # 지점유형은 모두 표시
            show_sp = show_norm = True

        # 3. 통합 필터링 적용
        filtered_pts = []
        for _, r in unique_pts.iterrows():
            # 1단계: 지점유형 필터 (Common)
            is_sp = r['desc'] in special_nodes
            if is_sp and not show_sp: continue
            if not is_sp and not show_norm: continue
            
            # 2단계: 모드별 상세 필터 (Mode-specific)
            if map_mode == "매개변수비교":
                is_opt = param_dict.get(str(r['desc']).strip()) == "최적화 지점"
                if is_opt and not mode_filters.get('최적화', True): continue
                if not is_opt and not mode_filters.get('기본값', True): continue
            elif map_mode == "최적화결과":
                ev = eval_dict.get(r['Name'].strip(), "평가없음")
                if not mode_filters.get(ev, True): continue
            
            filtered_pts.append(r)

        unique_pts = pd.DataFrame(filtered_pts) if filtered_pts else pd.DataFrame()

    if disp_basins is not None and not disp_basins.empty:
        bounds = disp_basins.total_bounds
        center_lat = (bounds[1] + bounds[3]) / 2
        center_lon = (bounds[0] + bounds[2]) / 2

        zoom_lvl = 8 if selected_ws == "전체" else 9
        
        # 지도 위치와 줌 레벨 설정
        # 1. Fly-To 요청이 있는 경우 (새로운 지점 선택)
        fly_to = st.session_state.get("fly_to_target")
        
        if fly_to:
            center = fly_to["center"]
            zoom = fly_to["zoom"]
            # 사용한 요청은 제거 (다음 리런 시에는 지도 자체 상태를 따르게 함)
            st.session_state.pop("fly_to_target")
        else:
            # 2. 평상시에는 세션에 저장된 마지막 상태 유지 (단, st_folium에 kwarg로 넘기지 않음으로써 충돌 방지)
            center = st.session_state.get("map_center", [center_lat, center_lon])
            zoom = st.session_state.get("map_zoom", zoom_lvl)
        
        # folium.Map 초기 객체 생성 (기본 위치는 Fly-To가 없을 때만 의미 있음)
        m = folium.Map(location=center, zoom_start=zoom, tiles="CartoDB positron",
                       zoomSnap=0.25, zoomDelta=0.25, wheelPxPerZoomLevel=60)

        if selected_ws != "전체":
            # 선택된 유역의 전체 경계(Boundary) 표시 (구멍 제거)
            ws_boundary = disp_basins.dissolve(by='watershed')
            
            from shapely.geometry import Polygon, MultiPolygon
            def remove_holes(geom):
                if geom.geom_type == 'Polygon':
                    return Polygon(geom.exterior.coords)
                elif geom.geom_type == 'MultiPolygon':
                    return MultiPolygon([Polygon(p.exterior.coords) for p in geom.geoms])
                return geom
                
            ws_boundary.geometry = ws_boundary.geometry.apply(remove_holes)
            
            ws_json = get_geojson_data(f"boundary_{selected_ws}", ws_boundary)
            if ws_json:
                folium.GeoJson(
                    ws_json,
                    style_function=lambda x: {'color': '#1e3a8a', 'weight': 4, 'fillOpacity': 0},
                    name="유역 전체 경계",
                    tooltip="유역 경계"
                ).add_to(m)

        def style_fn(feature):
            f_code = feature['properties']['Name']
            node_nm = node_metadata.get(f_code, "")
            
            # 유역 베이스 색상 (회색톤으로 통합하여 마커가 돋보이게 함)
            base_color = "#e2e8f0" 
            
            if selected_node:
                if f_code in upstream_set:
                    if f_code == selected_node:
                        return {'fillColor': '#dc2626', 'color': '#991b1b', 'weight': 2.0, 'fillOpacity': 0.7}
                    return {'fillColor': '#fbd38d', 'color': '#f6ad55', 'weight': 1.5, 'fillOpacity': 0.5}
                else:
                    return {'fillColor': base_color, 'color': base_color, 'weight': 0.8, 'fillOpacity': 0.15}
            else:
                return {'fillColor': base_color, 'color': "#94a3b8", 'weight': 1.0, 'fillOpacity': 0.35}

        basins_json = get_geojson_data(f"basins_{selected_ws}", disp_basins)
        if basins_json:
            folium.GeoJson(
                basins_json,
                style_function=style_fn,
                tooltip=folium.GeoJsonTooltip(fields=['Name', 'watershed', 'desc'], aliases=['소유역 ID:', '소속 권역:', '지점명:'])
            ).add_to(m)

        for i, r_gdf in enumerate(river_layers):
            if r_gdf is not None and not r_gdf.empty:
                r_json = get_geojson_data(f"river_{i}", r_gdf)
                if r_json:
                    folium.GeoJson(
                        r_json,
                        style_function=lambda x: {'color': '#38bdf8', 'weight': 0.8, 'opacity': 0.6},
                        name="하천(국가/지방)"
                    ).add_to(m)

        if disp_pts is not None and not disp_pts.empty:
            for idx, row in unique_pts.iterrows():
                pt_id = row['desc']
                pt_name = row['Name']
                pt_type = row.get('pt_type', '지점')
                lat_p = row.geometry.y
                lon_p = row.geometry.x
                
                is_special = (pt_type == '특보' or pt_id in special_nodes)
                
                # 기본값 설정
                fill_color = "black"
                border_color = "black"
                size = 3
                weight = 1
                tooltip_text = f"{pt_name}"
                
                if map_mode == "총 지점":
                    if is_special:
                        border_color, fill_color, size, weight = "#e11d48", "#f43f5e", 5, 3
                    else:
                        border_color, fill_color, size, weight = "#000000", "#475569", 3.5, 1
                elif map_mode == "매개변수비교":
                    p_status = param_dict.get(str(pt_id).strip(), "default 지점")
                    if p_status == "최적화 지점":
                        fill_color, border_color, size, weight = "#f97316", "#c2410c", 5, 2
                        tooltip_text = f"[최적화] {pt_name}"
                    else:
                        fill_color, border_color, size, weight = "#94a3b8", "#475569", 3.5, 1
                        tooltip_text = f"[기본값] {pt_name}"
                else:  # 최적화결과
                    eval_status = eval_dict.get(pt_name, "평가없음")
                    if eval_status == "개선": fill_color, border_color, weight = "#22c55e", "#14532d", 2
                    elif eval_status == "부분개선": fill_color, border_color, weight = "#eab308", "#713f12", 2
                    elif eval_status == "불가": fill_color, border_color, weight = "#ef4444", "#7f1d1d", 2
                    elif eval_status == "불가(본류)": fill_color, border_color, weight = "#ef4444", "#7f1d1d", 2
                    elif eval_status == "불가(조석)": fill_color, border_color, weight = "#ef4444", "#7f1d1d", 2
                    elif eval_status == "변화없음": fill_color, border_color, weight = "#9ca3af", "#374151", 2
                    if eval_status != "평가없음": size = max(size, 4.5)
                    if is_special: size = max(size, 4); weight = max(weight, 3)
                
                is_selected = (pt_id == selected_node)
                if is_selected:
                    border_color = "#1d4ed8"
                    size = 8
                    weight = 5

                # 팝업 내에 '선택' 단추 HTML 추가
                # pt_id에 '#'이 포함되어 있으므로 반드시 URL 인코딩 필요 (%23으로 치환)
                encoded_id = quote(str(pt_id), safe='')
                popup_html = f"""
                <div style='white-space: nowrap; font-size: 13px; font-weight: bold;'>
                    {pt_name} ({pt_id})<br>
                    <a href='/?node={encoded_id}' target='_top' style='display: inline-block; margin-top: 6px; padding: 3px 10px; background-color: #1E3A8A; color: white; text-decoration: none; border-radius: 4px; font-size: 11px; font-weight: bold; cursor: pointer; border: 1px solid #1E3A8A;'>선택</a>
                </div>
                """

                folium.CircleMarker(
                    location=[lat_p, lon_p],
                    radius=size,
                    popup=folium.Popup(popup_html, max_width='100%'),
                    tooltip=tooltip_text,
                    color=border_color,
                    weight=weight,
                    fill=True,
                    fill_color=fill_color,
                    fill_opacity=1.0
                ).add_to(m)

        # st_folium 호출 시 뷰 상태(center/zoom)만 유지하고, 클릭을 통한 자동 선택 로직은 제거하여
        # 지도 지점을 클릭했을 때 강제 리런 없이 팝업 창만 뜨도록 합니다.
        st_data = st_folium(
            m,
            use_container_width=True, 
            height=750, 
            returned_objects=["center", "zoom"]
        )
        
        if st_data:
            if "center" in st_data and st_data["center"]:
                st.session_state["map_center"] = [st_data["center"]["lat"], st_data["center"]["lng"]]
            if "zoom" in st_data and st_data["zoom"]:
                st.session_state["map_zoom"] = st_data["zoom"]
    else:
        st.warning("공간 데이터 로딩에 실패했습니다.")

# === 하단/우측 개념도 ===
with col_graph:
    st.subheader("📊 유역 흐름도")
    if selected_node and len(upstream_set) > 0:
        html_str = draw_network_flowchart(
            selected_node, 
            frozenset(upstream_set), 
            upstream_map, 
            node_metadata, 
            frozenset(special_nodes), 
            eval_dict,
            map_mode,
            param_dict
        )
        if html_str:
            components.html(html_str, height=730, scrolling=False)
            st.caption("※ 상자 색상은 엑셀 평가 결과에 따릅니다 (범례 참조). Target 지점은 파란색 두꺼운 테두리로 강조됩니다.")
    elif selected_node:
        st.info("선택하신 지점은 최상단 지점입니다.")
    else:
        st.info("좌측 분석 설정에서 지점을 선택하거나, 지도에서 지점 마커를 클릭하고 팝업의 '선택' 단추를 누르면 유역 흐름도가 표시됩니다.")

