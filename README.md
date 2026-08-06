# 낙동강권역 홍수예보 체계 개선 시각화 대시보드

낙동강권역 5개 유역(낙동강, 낙동강동해, 태화강, 형산강, 회야수영강)의 상·하류 연결 관계와 홍수특보 대상 지점을 지도와 유역 흐름도로 탐색하는 Streamlit 애플리케이션입니다.

## 바로 실행

[🌐 Streamlit 앱 열기](https://nakdong-flood-expansion-equdycu48r63xjh5yp4qks.streamlit.app/)

## 주요 기능

- 유역별 또는 전체 권역 지도 조회
- 특보지점·유역출구 선택 및 지점명/ID 통합 검색
- 지도 지점 클릭 시 해당 지점과 상류 연결 유역 강조
- 특보지점별 상류 유역 경계 표시
- 시군구 행정구역 클릭 선택, 선택 영역 강조 및 줌 수준에 따라 크기가 변하는 중앙 행정구역명 표시
- 국가하천·지방하천과 유역 경계 중첩 표시
- 수위관측소 일람표의 전체 관측소를 최적(A)·우수(B)·보통(C)·없음 등급별 색상과 개수로 지도에 표시
- 유역 흐름도에서 관측소의 유역면적, 관측소등급 표시
- 흐름도 노드 툴팁에서 관측자료 유형과 하천명 확인
- 선택 유역별 수위관측지점의 행정구역·지점 구분·대표하천·주소 현황표, 관측지점 셀 클릭 시 지도 위치 이동·선택 강조, 지도 연동 행정구역 다중 선택 필터 제공
- 현재 지도 화면을 고해상도 TIFF로 저장

> **매개변수 최적화 수행결과**와 **카테고리별 분류 (성능비교)** 지도 옵션은 현재 화면에서 숨겨져 있으며, 관련 구현은 추후 다시 사용할 수 있도록 코드에 유지되어 있습니다.

## 입력 자료

- **input/30_subbasin_*.inf**: 유역 상·하류 연결 정보
- **input/gis/유역도_*.geojson**: 유역 공간정보
- **input/gis/*_특보지점.geojson**: 홍수특보 지점
- **input/gis/*_유역출구.geojson**: 유역출구 지점
- **input/gis/낙동강_국가하천.geojson**, **낙동강_지방하천.geojson**: 하천망
- **input/gis/SGG_korea/SGG_korea.shp**: 시군구 행정구역 경계
- **input/1.강수량관측소 일람표_낙동강(2025).xlsx**: 강수량관측소 등급 정보
- **input/2.수위관측소 일람표_낙동강(2025).xlsx**: 수위관측소 유역면적·등급·하천·주소·좌표 정보

수위관측소 자료를 우선 사용하고, 일치하는 수위관측소 자료가 없을 때 강수량관측소 등급을 보완 정보로 사용합니다. 관측소 일람표와 지점명이 일치하지 않는 내부 유역 노드는 흐름도에 **자료 없음**으로 표시됩니다.

등급별 분류 모드와 하단 현황표는 수위관측소 일람표의 290개 관측소를 기준으로 합니다. **전체** 유역 선택 시 최적(A) 129개, 우수(B) 26개, 보통(C) 7개, 없음 128개가 표시되며, 개별 유역 선택 시 관측소 좌표가 해당 유역 경계 안에 포함되는 지점만 집계합니다.

## 폴더 구조

- **interactive_map.py**: Streamlit 앱 메인 파일
- **input/**: 유역 연결 및 관측소 입력 자료
- **input/gis/**: 유역·지점·하천·행정구역 원본 공간자료
- **input/gis/optimized/**: 지도 표출용으로 단순화한 경량 공간자료
- **input/optimized/station_metadata.json**: 관측소 일람표를 변환한 경량 메타데이터
- **requirements.txt**: Python 패키지 의존성
- **packages.txt**: Streamlit Cloud용 Linux 시스템 패키지

## 성능 최적화

앱은 원본 자료를 보존하면서 **input/gis/optimized/**와 **input/optimized/**의 경량 자료를 우선 사용합니다. 경량 파일이 없으면 원본 SHP·GeoJSON·XLSX를 자동으로 읽어 동일한 결과를 생성합니다. 행정구역 공간 연산, GeoJSON 직렬화, 유역 흐름도 HTML은 Streamlit 캐시를 사용하며, 화면에서 숨겨진 분석 자료는 관련 모드가 활성화될 때만 불러옵니다.

## 로컬 실행

    git clone https://github.com/hydravax/nakdong-flood-expansion.git
    cd nakdong-flood-expansion
    git lfs pull
    pip install -r requirements.txt
    streamlit run interactive_map.py

행정구역 SHP 파일은 GitHub의 일반 파일 크기 제한을 초과하여 Git LFS로 관리됩니다. 저장소를 내려받을 때 [Git LFS](https://git-lfs.com/)가 설치되어 있어야 합니다.

## Streamlit Community Cloud 배포

1. GitHub 저장소를 Streamlit Community Cloud에 연결합니다.
2. Main file path를 **interactive_map.py**로 지정합니다.
3. 배포 환경에서 Git LFS 파일이 정상적으로 내려받아졌는지 확인합니다.

앱 실행 후 왼쪽 설정 영역의 **행정구역 경계**를 선택하면 실제 유역과 겹치는 시군구 경계와 명칭이 표시됩니다. 지도에서 행정구역을 클릭하면 해당 폴리곤 범위가 초록색으로 강조됩니다.
