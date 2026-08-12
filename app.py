import streamlit as st

from services import auth_service
from views import review_queue, topic_dashboard

st.set_page_config(page_title="Legal Content Pipeline", layout="wide")

try:
    current_user = auth_service.get_current_user_email()
except PermissionError as exc:
    st.error(f"Access denied: {exc}")
    st.stop()

st.sidebar.title("Legal Content Pipeline")
st.sidebar.caption(f"Signed in as {current_user}")
view = st.sidebar.radio("Navigate", ["Topic Dashboard", "Review Queue"])

if view == "Topic Dashboard":
    topic_dashboard.render()
else:
    review_queue.render()
