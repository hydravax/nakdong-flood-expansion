# Ai홍수예보 5대 대권역 통합 상하류 네트워크 시각화 대시보드

## 1. 개요 (Overview)
본 대시보드는 5대 주요 권역(낙동강, 낙동강동해, 태화강, 형산강, 회야수영강)의 복잡한 유역망 관계를 직관적으로 분석하고 시각화할 목적으로 개발된 **Streamlit** 기반의 로컬 웹 애플리케이션입니다.
# 낙동강유역 홍수특보지점 검토 시각화

Streamlit 기반의 상호작용형 유역 지도 시각화 대시보드입니다.

## 폴더 구조 (Directory Structure)
- `interactive_map.py`: Streamlit 앱 메인 실행 파일 (Streamlit Cloud 연동)
- `input/`: 분석에 필요한 매개변수 파일 (.inf, .xlsx 등)
  - `input/gis/`: 시각화에 필요한 공간 데이터 파일 (.geojson, .qmd 등)
- `code/`: 추가 분석 스크립트 모음
- `requirements.txt`: Python 패키지 의존성
- `packages.txt`: Linux 시스템 패키지 (Chromium 등)

## 실행 방법 (로컬)
```bash
pip install -r requirements.txt
streamlit run interactive_map.py
```

## 실행 방법 (Streamlit Cloud)
1. GitHub 저장소를 Streamlit Cloud에 연결합니다.
2. Main file path를 `interactive_map.py`로 지정하여 배포합니다.
