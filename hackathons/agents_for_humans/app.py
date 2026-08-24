"""Streamlit interface for Opportunity Guardian."""

from __future__ import annotations

import streamlit as st

from opportunity_guardian import build_agent

st.set_page_config(page_title="Opportunity Guardian", page_icon="🛡️", layout="centered")
st.title("Opportunity Guardian")
st.caption("Evidence-first decisions for paid open-source work")

with st.form("bounty"):
    issue_url = st.text_input("GitHub issue URL", placeholder="https://github.com/owner/repo/issues/123")
    col1, col2 = st.columns(2)
    reward = col1.number_input("Advertised reward (USD)", min_value=0.0, value=100.0)
    claims = col2.number_input("Known claims", min_value=0, value=0)
    platform = st.text_input("Platform", value="unknown")
    escrow = st.selectbox("Funding evidence", ["unknown", "not_escrowed", "verified_escrow"])
    col3, col4 = st.columns(2)
    hours = col3.number_input("Estimated hours", min_value=0.1, value=5.0)
    floor = col4.number_input("Your hourly floor", min_value=0.0, value=20.0)
    submitted = st.form_submit_button("Investigate")

if submitted:
    if not issue_url:
        st.error("Enter a public GitHub issue URL.")
    else:
        prompt = f"""Investigate this opportunity end-to-end:
Issue: {issue_url}
Advertised reward: ${reward}
Platform: {platform}
Known claims: {claims}
Funding evidence: {escrow}
Estimated effort: {hours} hours
Hourly floor: ${floor}
Use both verification and expected-value tools. Give a short evidence table and decision."""
        with st.spinner("Checking primary evidence…"):
            try:
                result = build_agent()(prompt)
            except Exception as error:
                st.error(f"The agent could not finish: {error}")
            else:
                st.markdown(str(result))

st.divider()
st.caption("Advertised rewards are not guaranteed income. No credentials are stored by this app.")

