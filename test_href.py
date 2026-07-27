import streamlit as st

if "count" not in st.session_state:
    st.session_state.count = 0

st.session_state.count += 1
st.write(f"Count: {st.session_state.count}")

st.markdown(
    """
    <a href="." target="_self" style="text-decoration:none;">
        <h1 style="color:#1E3A8A;font-size:28px;">낙동강유역 홍수특보지점 검토</h1>
    </a>
    """,
    unsafe_allow_html=True
)
