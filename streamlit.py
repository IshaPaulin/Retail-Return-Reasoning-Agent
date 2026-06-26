import json
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st
import streamlit.components.v1 as components
from streamlit_cookies_manager import EncryptedCookieManager

st.set_page_config(
    page_title="Retail Return Reasoning Agent",
    page_icon="📦",
    layout="wide",
)

# ── Cookie manager (persists token across refreshes) ──────────────────────────
cookies = EncryptedCookieManager(prefix="rrra_", password="retail-return-agent-secret-2025")

if not cookies.ready():
    st.stop()

# ── Auth helpers ───────────────────────────────────────────────────────────────

def do_login(access_token: str):
    cookies["token"] = access_token
    cookies.save()
    st.session_state.chat_messages = []
    st.session_state.chat_conversation_id = str(uuid.uuid4())
    st.session_state.selected_product = None
    st.session_state.show_product_detail = False


def do_logout():
    cookies["token"] = ""
    cookies.save()
    st.session_state.chat_messages = []
    st.session_state.chat_conversation_id = str(uuid.uuid4())
    st.session_state.selected_product = None
    st.session_state.show_product_detail = False
     # Force login page
    st.query_params.clear()
   

# ── API helpers ────────────────────────────────────────────────────────────────

def api_request(
    base_url: str,
    path: str,
    method: str = "GET",
    token: str | None = None,
    payload: dict | None = None,
):
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
            error_data = json.loads(error_body) if error_body else {"detail": error_body}
        except json.JSONDecodeError:
            error_data = {"detail": error_body or str(exc)}
        return None, error_data.get("detail", str(exc))
    except URLError as exc:
        return None, f"Cannot reach backend at {base_url}: {exc.reason}"


def login_api(base_url: str, username: str, password: str):
    return api_request(
        base_url,
        "/auth/login",
        method="POST",
        payload={"username": username, "password": password},
    )


# ── Detail renderer ────────────────────────────────────────────────────────────

def render_detail(d: dict):
    signal = d.get("return_signal", "Low")
    signal_color = {"High": "🔴", "Medium": "🟡", "Normal": "🟢", "Low": "🟢"}.get(signal, "⚪")

    st.markdown(f"## {d.get('product_name', 'Product')}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Return Signal", f"{signal_color} {signal}")
    c2.metric("Risk Score", d.get("risk_score", "—"))
    c3.metric("Return Rate", f"{round(d.get('return_rate', 0) * 100, 2)}%")
    c4.metric("Confidence", d.get("confidence", "—").capitalize())

    trend = d.get("trend", "stable")
    trend_icon = {"increasing": "📈", "decreasing": "📉", "stable": "➡️"}.get(trend, "➡️")
    growth = d.get("trend_growth_rate", 0)
    st.caption(
        f"Trend: {trend_icon} {trend.capitalize()} "
        f"({'+' if growth >= 0 else ''}{round(growth * 100, 1)}%)"
    )
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
            st.write(f"Return rate: {round(wv.get('return_rate', 0) * 100, 1)}%")
            st.write(f"Returns: {wv.get('return_count', 0)}")

        cc = d.get("category_comparison") or {}
        if cc.get("category_name") and cc.get("category_name") != "Unknown":
            st.markdown("#### Category")
            st.write(f"{cc.get('category_name')}")
            st.write(f"Avg return rate: {round(cc.get('average_return_rate', 0) * 100, 1)}%")
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
                    f"- {sku.get('variant') or sku.get('sku_id', '?')}: "
                    f"{sku.get('return_count', 0)} returns"
                )

    components_data = d.get("score_components") or {}
    if components_data:
        with st.expander("Score breakdown"):
            for key, val in components_data.items():
                st.write(f"{key.replace('_', ' ').title()}: **{val} pts**")


# ── Session state ──────────────────────────────────────────────────────────────

if "selected_product" not in st.session_state:
    st.session_state.selected_product = None
if "show_product_detail" not in st.session_state:
    st.session_state.show_product_detail = False
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "chat_conversation_id" not in st.session_state:
    st.session_state.chat_conversation_id = str(uuid.uuid4())
if "base_url" not in st.session_state:
    st.session_state.base_url = "http://localhost:8000"

# Read token from cookie
token = cookies.get("token", "")


# ── Global styles + persistent top bar ────────────────────────────────────────

st.markdown(
    """
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        #MainMenu { visibility: hidden; }
        footer    { visibility: hidden; }
        header    { visibility: hidden; }
        [data-testid="collapsedControl"] { display: none; }

        .block-container {
            padding-top: 72px !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }

        /* ── top bar ── */
        #rr-topbar {
            position: fixed;
            top: 0; left: 0; right: 0;
            height: 60px;
            background: #0f172a;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            display: flex;
            align-items: center;
            padding: 0 24px;
            gap: 14px;
            z-index: 99000;
        }
        #rr-topbar-logo  { font-size: 26px; flex-shrink: 0; }
        #rr-topbar-title {
            font-family: 'Inter', sans-serif;
            font-size: 15px; font-weight: 700;
            color: #f1f5f9;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }
        #rr-topbar-spacer { flex: 1; }

        /* ── login page dark bg ── */
        [data-testid="stAppViewContainer"] { background: #0d1117 !important; }

        /* ── login card ── */
        .rr-login-card {
            background: #ffffff;
            border-radius: 20px;
            padding: 40px 36px 32px 36px;
            box-shadow: 0 8px 48px rgba(0,0,0,0.35);
            border: 1px solid rgba(255,255,255,0.08);
        }
        .rr-login-heading {
            font-family: 'Inter', sans-serif;
            font-size: 2rem; font-weight: 700;
            color: #1a1a2e;
            text-align: center;
            margin-bottom: 4px;
        }
        .rr-login-sub {
            font-family: 'Inter', sans-serif;
            font-size: 13px; color: #6b7280;
            text-align: center; margin-bottom: 24px;
        }
        .rr-field-label {
            font-family: 'Inter', sans-serif;
            font-size: 12px; font-weight: 600;
            color: #374151; margin-bottom: 4px;
            letter-spacing: 0.02em;
        }
        div[data-testid="stTextInput"] input {
            border-radius: 10px !important;
            border: 1.5px solid #e5e7eb !important;
            background: #f9fafb !important;
            font-family: 'Inter', sans-serif !important;
            font-size: 14px !important; color: #111827 !important;
        }
        div[data-testid="stTextInput"] input:focus {
            border-color: #6366f1 !important;
            box-shadow: 0 0 0 3px rgba(99,102,241,0.12) !important;
        }
        div[data-testid="stTextInput"] input::placeholder { color: #9ca3af !important; }
        div[data-testid="stButton"] button {
            border-radius: 10px !important;
            font-family: 'Inter', sans-serif !important;
            font-weight: 600 !important; font-size: 15px !important;
            height: 44px !important;
        }
        .rr-login-spacer { height: calc(50vh - 280px); min-height: 20px; }

        /* ── dashboard hero ── */
        .dash-hero {
            padding: 1.1rem 1.5rem; border-radius: 16px;
            background: linear-gradient(135deg, #101828 0%, #1f2937 55%, #0f172a 100%);
            color: white; margin-bottom: 1.25rem;
            border: 1px solid rgba(255,255,255,0.08);
        }
        .dash-hero h2 { margin: 0; font-size: 1.4rem; font-family: 'Inter', sans-serif; }
        .dash-hero p  { margin: 0.3rem 0 0 0; color: #94a3b8; font-size: 13px; font-family: 'Inter', sans-serif; }
    </style>

    <div id="rr-topbar">
        <span id="rr-topbar-logo">📦</span>
        <span id="rr-topbar-title">Retail Return Reasoning Agent</span>
        <span id="rr-topbar-spacer"></span>
    </div>
    """,
    unsafe_allow_html=True,
)


# ── Handle logout via query param (ensures cookie is cleared before render) ───

if st.query_params.get("logout") == "1":
    st.query_params.clear()
    do_logout()
    st.rerun()


# ── LOGIN PAGE ─────────────────────────────────────────────────────────────────

if not token:
    components.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;

            ["rr-chat-fab", "rr-chat-panel", "rr-chat-style"].forEach(id => {
                const el = doc.getElementById(id);
                if (el) el.remove();
            });
        })();
        </script>
        """,
        height=0,
    )
    st.markdown('<div class="rr-login-spacer"></div>', unsafe_allow_html=True)
    _, card_col, _ = st.columns([1, 1.4, 1])

    with card_col:
        st.markdown('<div class="rr-login-card">', unsafe_allow_html=True)
        st.markdown('<div class="rr-login-heading">Login</div>', unsafe_allow_html=True)
        st.markdown('<div class="rr-login-sub">Retail Return Reasoning Agent</div>', unsafe_allow_html=True)

        st.markdown('<div class="rr-field-label">Username</div>', unsafe_allow_html=True)
        username_input = st.text_input(
            "username_hidden", placeholder="Enter your username",
            key="login_username", label_visibility="hidden",
        )

        st.markdown('<div class="rr-field-label">Password</div>', unsafe_allow_html=True)
        password_input = st.text_input(
            "password_hidden", placeholder="Enter your password",
            type="password", key="login_password", label_visibility="hidden",
        )

        st.markdown("<br>", unsafe_allow_html=True)
        login_clicked = st.button("Login", use_container_width=True, type="primary")

        if login_clicked:
            if not username_input or not password_input:
                st.error("Please enter your username and password.")
            else:
                with st.spinner("Signing in…"):
                    login_data, login_error = login_api(
                        st.session_state.base_url, username_input, password_input
                    )
                if login_error:
                    st.error(login_error)
                else:
                    do_login(login_data.get("access_token", ""))
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    st.stop()


# ── POST-LOGIN SIDEBAR ─────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("Connection")
    new_url = st.text_input("Backend URL", value=st.session_state.base_url)
    st.session_state.base_url = new_url
    st.caption("FastAPI backend URL")
    st.divider()
    st.success("Session active")
    if st.button("Log out", use_container_width=True):
        do_logout()
        st.rerun()
        
   
base_url = st.session_state.base_url


# ── DASHBOARD ──────────────────────────────────────────────────────────────────

st.markdown(
    """
    <div class="dash-hero">
        <h2>Seller Dashboard</h2>
        <p>Product return insights and drill-down analysis</p>
    </div>
    """,
    unsafe_allow_html=True,
)

dashboard_data, dashboard_error = api_request(
    base_url, "/dashboard", token=token
)

if dashboard_error:
    st.error(dashboard_error)
    st.stop()

products = dashboard_data or []

col1, col2, col3 = st.columns(3)
col1.metric("Products", len(products))
col2.metric("High signals", sum(1 for p in products if p.get("return_signal") == "High"))
col3.metric("Normal/Low",  sum(1 for p in products if p.get("return_signal") in {"Normal", "Low"}))

st.markdown("### Seller Products")

if not products:
    st.warning("No products found for this seller.")
else:
    for product in products:
        with st.container(border=True):
            left, right = st.columns([3, 1])
            with left:
                st.markdown(
                    f"**{product.get('product_name', product.get('product_id', 'Unknown product'))}**"
                )
                st.caption(f"Product ID: {product.get('product_id', '-')}")
                st.write(product.get("summary", "No summary available."))
            with right:
                st.metric("Return signal", product.get("return_signal", "Low"))
                st.write(f"Pattern: {product.get('primary_pattern', 'No strong pattern detected')}")
                if st.button("View details", key=f"view-{product.get('product_id')}"):
                    st.session_state.selected_product = product.get("product_id")
                    st.session_state.show_product_detail = True


# ── PRODUCT DETAIL MODAL ───────────────────────────────────────────────────────

@st.dialog("Product Detail", width="large")
def show_product_modal(product_id: str):
    with st.spinner("Loading product analysis..."):
        detail_data, detail_error = api_request(
            base_url,
            f"/dashboard/product/{product_id}",
            token=token,
        )
    if detail_error:
        st.error(detail_error)
    else:
        render_detail(detail_data)


if st.session_state.show_product_detail and st.session_state.selected_product:
    show_product_modal(st.session_state.selected_product)
    st.session_state.show_product_detail = False
    st.session_state.selected_product = None


# ── CHAT SECTION (unchanged) ───────────────────────────────────────────────────

st.markdown("---")
st.markdown("## Returns Analytics Chat")

with st.form("chat_form", clear_on_submit=True):
    chat_text = st.text_area(
        "Ask your returns assistant", key="chat_input", height=120
    )
    submitted = st.form_submit_button("Send")

    if submitted:
        chat_text = chat_text.strip()
        if chat_text:
            chat_payload = {
                "message": chat_text,
                "history": [
                    {
                        "role": "user" if m["sender"] == "user" else "assistant",
                        "content": m["text"],
                    }
                    for m in st.session_state.chat_messages
                ],
            }

            response_data, response_error = api_request(
                base_url,
                "/chat",
                method="POST",
                token=token,
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
                    "conversation_id", st.session_state.chat_conversation_id
                )

# Render chat history
if st.session_state.chat_messages:
    for message in st.session_state.chat_messages:
        if message["sender"] == "user":
            with st.chat_message("user"):
                st.markdown(message["text"])
        else:
            with st.chat_message("assistant"):
                st.markdown(message["text"])


# ── FLOATING CHAT FAB (unchanged) ─────────────────────────────────────────────

_token           = token
_base_url        = base_url.rstrip("/")
_conversation_id = st.session_state.chat_conversation_id

_chat_html = f"""
<script>
(function() {{
  const TOKEN           = {json.dumps(_token)};
  const BASE_URL        = {json.dumps(_base_url)};
  let   conversationId  = {json.dumps(_conversation_id)};

  const doc = window.parent.document;
  ["rr-chat-fab", "rr-chat-panel", "rr-chat-style"].forEach(id => {{
    const old = doc.getElementById(id);
    if (old) old.remove();
}});

  // ── styles ──
  const style = doc.createElement("style");
  style.id = "rr-chat-style";
  style.textContent = `
    #rr-chat-fab {{
      position: fixed; bottom: 28px; right: 28px;
      width: 56px; height: 56px; border-radius: 50%;
      background: #6366f1; border: none; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      z-index: 999999; font-size: 26px;
      box-shadow: 0 4px 18px rgba(99,102,241,0.45);
      transition: transform 0.15s, box-shadow 0.15s; line-height: 1;
    }}
    #rr-chat-fab:hover {{ transform: scale(1.1); box-shadow: 0 6px 24px rgba(99,102,241,0.6); }}
    #rr-chat-panel {{
      position: fixed; bottom: 28px; right: 28px;
      width: 340px; height: 520px;
      background: #0a0a0a; border: 1px solid rgba(255,255,255,0.1);
      border-radius: 16px; display: none; flex-direction: column;
      z-index: 999999; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      overflow: hidden; box-shadow: 0 8px 40px rgba(0,0,0,0.5);
    }}
    #rr-chat-panel.open {{ display: flex; }}
    #rr-chat-header {{
      display: flex; align-items: center; justify-content: space-between;
      padding: 12px 14px; border-bottom: 1px solid rgba(255,255,255,0.08);
      background: #1f2937; border-radius: 16px 16px 0 0;
    }}
    #rr-chat-header-left {{ display: flex; align-items: center; gap: 8px; }}
    #rr-chat-title {{ font-size: 13px; font-weight: 600; color: #f1f5f9; }}
    #rr-chat-badge {{
      font-size: 10px; padding: 2px 7px; border-radius: 6px;
      background: rgba(255,255,255,0.12); color: #94a3b8; font-weight: 500;
    }}
    #rr-chat-close {{
      background: none; border: none; cursor: pointer; color: #94a3b8;
      font-size: 18px; line-height: 1; padding: 2px 4px; border-radius: 6px;
    }}
    #rr-chat-close:hover {{ background: rgba(255,255,255,0.1); color: #f1f5f9; }}
    #rr-chat-body {{
      flex: 1; padding: 14px 12px; overflow-y: auto;
      display: flex; flex-direction: column; gap: 10px; background: #0a0a0a;
    }}
    .rr-msg {{
      max-width: 85%; font-size: 12.5px; line-height: 1.55;
      padding: 8px 11px; border-radius: 12px; word-break: break-word;
    }}
    .rr-msg.user {{
      background: #1f2937; color: #f1f5f9;
      align-self: flex-end; border-bottom-right-radius: 4px;
    }}
    .rr-msg.bot {{
      background: #1a1a1a; color: #e2e8f0; align-self: flex-start;
      border: 1px solid rgba(255,255,255,0.08); border-bottom-left-radius: 4px;
    }}
    .rr-msg.thinking {{
      background: #1a1a1a; color: #94a3b8; align-self: flex-start;
      font-style: italic; border: 1px solid rgba(255,255,255,0.06);
      border-bottom-left-radius: 4px;
    }}
    #rr-chat-input-row {{
      display: flex; align-items: flex-end; gap: 8px;
      padding: 10px 12px; border-top: 1px solid rgba(255,255,255,0.08);
      background: #0a0a0a;
    }}
    #rr-chat-textarea {{
      flex: 1; font-size: 12.5px; font-family: inherit;
      border: 1px solid rgba(255,255,255,0.14); border-radius: 10px;
      padding: 8px 10px; resize: none; height: 36px; max-height: 100px;
      line-height: 1.45; background: #1a1a1a; color: #e2e8f0;
      outline: none; overflow-y: auto;
    }}
    #rr-chat-textarea::placeholder {{ color: #4b5563; }}
    #rr-chat-textarea:focus {{ border-color: #6366f1; }}
    #rr-chat-send {{
      width: 34px; height: 34px; border-radius: 50%; border: none;
      background: #6366f1; color: white; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0; font-size: 16px; margin-bottom: 1px;
      transition: background 0.15s, transform 0.1s;
    }}
    #rr-chat-send:hover {{ background: #4f46e5; }}
    #rr-chat-send:active {{ transform: scale(0.93); }}
  `;
  doc.head.appendChild(style);

  // ── FAB button ──
  const fab = doc.createElement("button");
  fab.id = "rr-chat-fab";
  fab.setAttribute("aria-label", "Open returns assistant");
  fab.textContent = "🤖";
  doc.body.appendChild(fab);

  // ── Chat panel ──
  const panel = doc.createElement("div");
  panel.id = "rr-chat-panel";
  panel.setAttribute("role", "dialog");
  panel.innerHTML = `
    <div id="rr-chat-header">
      <div id="rr-chat-header-left">
        <span>🤖</span>
        <span id="rr-chat-title">Returns assistant</span>
        <span id="rr-chat-badge">AI</span>
      </div>
      <button id="rr-chat-close" aria-label="Close chat">✕</button>
    </div>
    <div id="rr-chat-body">
      <div class="rr-msg bot">Hi! Ask me anything about your product returns 📦</div>
    </div>
    <div id="rr-chat-input-row">
      <textarea id="rr-chat-textarea" placeholder="Ask about returns…" rows="1"></textarea>
      <button id="rr-chat-send" aria-label="Send">➤</button>
    </div>
  `;
  doc.body.appendChild(panel);

  const chatBody = doc.getElementById("rr-chat-body");
  const textarea = doc.getElementById("rr-chat-textarea");

  fab.addEventListener("click", function() {{
    panel.classList.add("open");
    fab.style.display = "none";
    textarea.focus();
  }});

  doc.getElementById("rr-chat-close").addEventListener("click", function() {{
    panel.classList.remove("open");
    fab.style.display = "flex";
  }});

  function appendMessage(text, role) {{
    const div = doc.createElement("div");
    div.className = "rr-msg " + role;
    div.textContent = text;
    chatBody.appendChild(div);
    chatBody.scrollTop = chatBody.scrollHeight;
    return div;
  }}

  function autoResize() {{
    textarea.style.height = "36px";
    textarea.style.height = Math.min(textarea.scrollHeight, 100) + "px";
  }}

  textarea.addEventListener("input", autoResize);
  textarea.addEventListener("keydown", function(e) {{
    if (e.key === "Enter" && !e.shiftKey) {{ e.preventDefault(); sendMessage(); }}
  }});
  doc.getElementById("rr-chat-send").addEventListener("click", sendMessage);

  async function sendMessage() {{
    const text = textarea.value.trim();
    if (!text) return;
    textarea.value = "";
    autoResize();
    appendMessage(text, "user");
    const thinking = appendMessage("Thinking…", "thinking");

    try {{
      const response = await fetch(BASE_URL + "/chat", {{
        method: "POST",
        headers: {{
          "Content-Type": "application/json",
          "Authorization": "Bearer " + TOKEN,
        }},
        body: JSON.stringify({{
          message: text,
          conversation_id: conversationId,
        }}),
      }});

      const data = await response.json();
      thinking.remove();

      if (!response.ok) {{
        appendMessage("Error: " + (data.detail || "Something went wrong."), "bot");
        return;
      }}

      conversationId = data.conversation_id || conversationId;
      appendMessage(data.response || "No response.", "bot");

    }} catch (err) {{
      thinking.remove();
      appendMessage("Could not reach the server. Please check your connection.", "bot");
    }}
  }}
}})();
</script>
"""

if token:
    components.html(_chat_html, height=0)