import json
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st

st.set_page_config(page_title="Retail Return Reasoning Agent",
                   page_icon="📦", layout="wide")


def api_request(base_url: str, path: str, method: str = "GET", token: str | None = None, payload: dict | None = None):
    url = base_url.rstrip("/") + path
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None, None
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        try:
            error_data = json.loads(error_body) if error_body else {
                "detail": error_body}
        except json.JSONDecodeError:
            error_data = {"detail": error_body or str(exc)}
        return None, error_data.get("detail", str(exc))
    except URLError as exc:
        return None, f"Cannot reach backend at {base_url}: {exc.reason}"


def login(base_url: str, username: str, password: str):
    return api_request(
        base_url,
        "/auth/login",
        method="POST",
        payload={"username": username, "password": password},
    )


def render_detail(d: dict):
    signal = d.get("return_signal", "Low")
    signal_color = {"High": "🔴", "Medium": "🟡",
                    "Normal": "🟢", "Low": "🟢"}.get(signal, "⚪")

    st.markdown(f"## {d.get('product_name', 'Product')}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Return Signal", f"{signal_color} {signal}")
    c2.metric("Risk Score", d.get("risk_score", "—"))
    c3.metric("Return Rate", f"{round(d.get('return_rate', 0) * 100, 2)}%")
    c4.metric("Confidence", d.get("confidence", "—").capitalize())
    trend = d.get("trend", "stable")
    trend_icon = {"increasing": "📈", "decreasing": "📉",
                  "stable": "➡️"}.get(trend, "➡️")
    growth = d.get("trend_growth_rate", 0)
    st.caption(
        f"Trend: {trend_icon} {trend.capitalize()} ({'+' if growth >= 0 else ''}{round(growth * 100, 1)}%)")
    st.divider()

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown("#### Summary")
        st.write(d.get("summary") or "No summary available.")

        st.markdown("#### Root Cause")
        st.write(d.get("root_cause") or "No root cause identified.")

        points = d.get("supporting_points") or []
        if points:
            st.markdown("#### Supporting Evidence")
            for point in points:
                st.markdown(f"- {point}")

        recs = d.get("recommendations") or []
        if recs:
            st.markdown("#### Recommendations")
            for i, rec in enumerate(recs, 1):
                st.markdown(f"**{i}.** {rec}")

    with col_right:
        wv = d.get("worst_variant") or {}
        if wv.get("variant") or wv.get("sku_id"):
            st.markdown("#### Worst Variant")
            st.markdown(f"**{wv.get('variant') or wv.get('sku_id', '—')}**")
            st.write(
                f"Return rate: {round(wv.get('return_rate', 0) * 100, 1)}%")
            st.write(f"Returns: {wv.get('return_count', 0)}")

        cc = d.get("category_comparison") or {}
        if cc.get("category_name") and cc.get("category_name") != "Unknown":
            st.markdown("#### Category")
            st.write(f"{cc.get('category_name')}")
            st.write(
                f"Avg return rate: {round(cc.get('average_return_rate', 0) * 100, 1)}%")
            st.write(f"Relative risk: {round(cc.get('relative_risk', 0), 2)}x")

    st.divider()

    evidence = d.get("evidence") or {}
    if evidence:
        st.markdown("#### Evidence")
        e1, e2, e3 = st.columns(3)
        e1.metric("Sales Units", evidence.get("sales_units", "—"))
        e2.metric("Returns", evidence.get("return_count", "—"))
        e3.metric("Feedback Count", evidence.get("feedback_count", "—"))

        recent = evidence.get("recent_windows") or {}
        if any(recent.values()):
            r1, r2, r3 = st.columns(3)
            r1.metric("Returns (7d)", recent.get("7d", 0))
            r2.metric("Returns (30d)", recent.get("30d", 0))
            r3.metric("Returns (90d)", recent.get("90d", 0))

        reasons = evidence.get("return_reasons") or {}
        if reasons:
            st.markdown("**Return Reasons**")
            for reason, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
                st.write(f"- {reason}: {count}")

        sku_breakdown = evidence.get("sku_breakdown") or []
        if sku_breakdown:
            st.markdown("**SKU Breakdown**")
            for sku in sku_breakdown:
                st.write(
                    f"- {sku.get('variant') or sku.get('sku_id', '?')}: {sku.get('return_count', 0)} returns")

    components = d.get("score_components") or {}
    if components:
        with st.expander("Score breakdown"):
            for key, val in components.items():
                st.write(f"{key.replace('_', ' ').title()}: **{val} pts**")


st.markdown(
    """
    <style>
        .hero {
            padding: 1.25rem 1.5rem;
            border-radius: 18px;
            background: linear-gradient(135deg, #101828 0%, #1f2937 55%, #0f172a 100%);
            color: white;
            margin-bottom: 1.25rem;
            border: 1px solid rgba(255,255,255,0.08);
        }
        .hero h1 { margin: 0; font-size: 2rem; }
        .hero p { margin: 0.35rem 0 0 0; color: #cbd5e1; }
        .metric-card {
            padding: 1rem 1.1rem;
            border-radius: 14px;
            background: #0f172a;
            color: white;
            border: 1px solid rgba(148,163,184,0.18);
        }
        .muted { color: #94a3b8; }
    </style>
    """,
    unsafe_allow_html=True,
)

if "token" not in st.session_state:
    st.session_state.token = ""

if "selected_product" not in st.session_state:
    st.session_state.selected_product = None

if "show_product_detail" not in st.session_state:
    st.session_state.show_product_detail = False

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "chat_conversation_id" not in st.session_state:
    st.session_state.chat_conversation_id = str(uuid.uuid4())

st.markdown(
    """
    <div class="hero">
        <h1>Retail Return Reasoning Agent</h1>
        <p>Seller dashboard for login, product return insights, and product drill-down.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Connection")
    base_url = st.text_input("Backend URL", value="http://localhost:8000")
    st.caption("This frontend calls the FastAPI backend directly.")

    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Sign in", use_container_width=True):
        login_data, login_error = login(base_url, username, password)
        if login_error:
            st.session_state.token = ""
            st.error(login_error)
        else:
            st.session_state.token = login_data.get("access_token", "")
            st.session_state.selected_product = None
            st.session_state.show_product_detail = False
            st.success("Logged in")

    if st.session_state.token:
        st.success("Session active")
        if st.button("Log out", use_container_width=True):
            st.session_state.token = ""
            st.session_state.selected_product = None
            st.session_state.show_product_detail = False

if not st.session_state.token:
    st.info("Log in from the sidebar to load your seller dashboard.")
    st.stop()

dashboard_data, dashboard_error = api_request(
    base_url, "/dashboard", token=st.session_state.token)

if dashboard_error:
    st.error(dashboard_error)
    st.stop()

products = dashboard_data or []

col1, col2, col3 = st.columns(3)
col1.metric("Products", len(products))
col2.metric("High signals", sum(
    1 for item in products if item.get("return_signal") == "High"))
col3.metric("Normal/Low",
            sum(1 for item in products if item.get("return_signal") in {"Normal", "Low"}))

st.markdown("### Seller Products")

if not products:
    st.warning("No products found for this seller.")
else:
    for product in products:
        with st.container(border=True):
            left, right = st.columns([3, 1])
            with left:
                st.markdown(
                    f"**{product.get('product_name', product.get('product_id', 'Unknown product'))}**")
                st.caption(f"Product ID: {product.get('product_id', '-')}")
                st.write(product.get("summary", "No summary available."))
            with right:
                st.metric("Return signal", product.get("return_signal", "Low"))
                st.write(
                    f"Pattern: {product.get('primary_pattern', 'No strong pattern detected')}")
                if st.button("View details", key=f"view-{product.get('product_id')}"):
                    st.session_state.selected_product = product.get(
                        "product_id")
                    st.session_state.show_product_detail = True

selected_product = st.session_state.selected_product if st.session_state.show_product_detail else None


@st.dialog("Product Detail", width="large")
def show_product_modal(product_id: str):
    with st.spinner("Loading product analysis..."):
        detail_data, detail_error = api_request(
            base_url,
            f"/dashboard/product/{product_id}",
            token=st.session_state.token,
        )
    if detail_error:
        st.error(detail_error)
    else:
        render_detail(detail_data)


if st.session_state.show_product_detail and st.session_state.selected_product:
    show_product_modal(st.session_state.selected_product)
    st.session_state.show_product_detail = False
    st.session_state.selected_product = None

st.markdown("---")
st.markdown("## Returns Analytics Chat")

with st.form("chat_form", clear_on_submit=True):
    chat_text = st.text_area("Ask your returns assistant",
                             key="chat_input", height=120)
    submitted = st.form_submit_button("Send")

    if submitted:
        chat_text = chat_text.strip()
        if chat_text:
            chat_payload = {
                "message": chat_text,
            }
            response_data, response_error = api_request(
                base_url,
                "/chat",
                method="POST",
                token=st.session_state.token,
                payload=chat_payload,
            )

            if response_error:
                st.error(response_error)
            elif response_data:
                st.session_state.chat_messages.append({
                    "sender": "user",
                    "text": chat_text,
                })
                st.session_state.chat_messages.append({
                    "sender": "assistant",
                    "text": response_data.get("response", "No response."),
                })
                st.session_state.chat_conversation_id = response_data.get(
                    "conversation_id", st.session_state.chat_conversation_id)

if st.session_state.chat_messages:
    for message in st.session_state.chat_messages:
        if message["sender"] == "user":
            with st.chat_message("user"):
                st.markdown(message["text"])
        else:
            with st.chat_message("assistant"):
                st.markdown(message["text"])
