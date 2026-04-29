"""Single shared password gate via st.secrets['app_password']."""
import hmac

import streamlit as st


def require_password() -> None:
    if st.session_state.get("authed"):
        return
    expected = st.secrets.get("app_password")
    if not expected:
        st.error("`app_password` is not set in Streamlit secrets.")
        st.stop()
    pw = st.text_input("Password", type="password")
    if pw:
        if hmac.compare_digest(pw, expected):
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Wrong password")
    st.stop()
