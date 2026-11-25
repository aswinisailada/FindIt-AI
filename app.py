
from datetime import date
from io import BytesIO
from pathlib import Path
import sqlite3
import uuid

from PIL import Image

import pandas as pd
import streamlit as st

from database import (
    add_report,
    authenticate_user,
    get_finder_contact_for_lost_owner,
    get_my_reports,
    get_public_reports,
    register_user,
    update_report_status,
)
from matching import calculate_match, calculate_match_details


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


def save_uploaded_image(uploaded_file):
    """Validate image bytes and save a safe, randomly named image."""
    if uploaded_file is None:
        return None
    raw = uploaded_file.getvalue()
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Image must be 5 MB or smaller.")
    try:
        with Image.open(BytesIO(raw)) as image:
            image_format = image.format
            image.verify()
    except Exception as exc:
        raise ValueError("Please upload a valid JPG, PNG, or WEBP image.") from exc
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise ValueError("Only JPG, PNG, and WEBP images are allowed.")
    filename = f"{uuid.uuid4().hex}{ALLOWED_IMAGE_FORMATS[image_format]}"
    destination = UPLOAD_DIR / filename
    destination.write_bytes(raw)
    return f"uploads/{filename}"


def show_report_image(image_path, width=220):
    if not image_path:
        return
    full_path = BASE_DIR / str(image_path)
    if full_path.is_file():
        st.image(str(full_path), width=width)


# =========================================
# 1. PAGE SETTINGS
# =========================================

st.set_page_config(
    page_title="FindIt AI | Lost & Found",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================
# 2. DESIGN
# =========================================

st.markdown("""
<style>
.stApp {
    background: linear-gradient(
        135deg, #edf5ff 0%, #f1edff 48%, #e5f4f7 100%
    );
}

[data-testid="stSidebar"] {
    background: linear-gradient(
        180deg, #102a43 0%, #164e63 100%
    );
}

[data-testid="stSidebar"] * {
    color: white;
}

[data-testid="stSidebar"] [data-baseweb="select"] * {
    color: #102a43;
}

.main .block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
    max-width: 1250px;
}

h1, h2, h3 {
    color: #12304a;
}

[data-testid="stMetric"] {
    background: rgba(255, 255, 255, 0.95);
    padding: 18px;
    border-radius: 14px;
    border: 1px solid #d7e6f4;
    box-shadow: 0 4px 14px rgba(16, 42, 67, 0.06);
}

.stButton > button,
.stFormSubmitButton > button {
    background: #087e8b;
    color: white;
    border: none;
    border-radius: 9px;
    font-weight: 600;
    min-height: 42px;
}

.stButton > button:hover,
.stFormSubmitButton > button:hover {
    background: #05616b;
    color: white;
    border: 1px solid #05616b;
}

div[data-testid="stForm"] {
    background: rgba(255, 255, 255, 0.82);
    padding: 22px;
    border: 1px solid #d7e6f4;
    border-radius: 14px;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255, 255, 255, 0.82);
    border-radius: 12px;
}

[data-testid="stDataFrame"] {
    border: 1px solid #d7e6f4;
    border-radius: 10px;
}

#MainMenu {
    visibility: hidden;
}

footer {
    visibility: hidden;
}
</style>
""", unsafe_allow_html=True)


# =========================================
# 3. SESSION STATE
# =========================================

if "user" not in st.session_state:
    st.session_state["user"] = None

if "auth_page" not in st.session_state:
    st.session_state["auth_page"] = "Login"

if "registered_success" not in st.session_state:
    st.session_state["registered_success"] = False


# =========================================
# 4. LOGIN AND REGISTRATION
# =========================================

def show_authentication():

    st.title("🔎 FindIt AI")
    st.subheader("Welcome to FindIt AI")

    st.write(
        "Create an account or log in to report lost and found items. "
        "Contact details are protected."
    )

    # Display the success message on the Login page.
    if (
        st.session_state["auth_page"] == "Login"
        and st.session_state["registered_success"]
    ):
        st.success(
            "Account created successfully! Please log in."
        )

    # -------------------------------------
    # LOGIN PAGE
    # -------------------------------------

    if st.session_state["auth_page"] == "Login":

        with st.form("login_form"):

            login_name = st.text_input(
                "Username or Email"
            )

            login_password = st.text_input(
                "Password",
                type="password",
            )

            login_button = st.form_submit_button(
                "Login",
                use_container_width=True,
            )

        if login_button:

            if not login_name.strip() or not login_password:
                st.error(
                    "Please enter your username/email and password."
                )

            else:
                try:
                    account = authenticate_user(
                        login_name.strip(),
                        login_password,
                    )

                    if account:
                        st.session_state["user"] = account
                        st.session_state["registered_success"] = False
                        st.rerun()

                    else:
                        st.error(
                            "Incorrect username/email or password."
                        )

                except Exception as exc:
                    st.error(f"Login failed: {exc}")

        st.markdown("---")

        if st.button(
            "Don't have an account? Register",
            use_container_width=True,
        ):
            st.session_state["auth_page"] = "Register"
            st.rerun()

    # -------------------------------------
    # REGISTRATION PAGE
    # -------------------------------------

    else:

        st.subheader("Create Your Account")

        with st.form(
            "register_form",
            clear_on_submit=False,
        ):

            username = st.text_input(
                "Enter Username",
                autocomplete="off",
            )

            email = st.text_input(
                "Email Address",
            )

            password = st.text_input(
                "Create Password (minimum 8 characters)",
                type="password",
            )

            confirm_password = st.text_input(
                "Confirm Password",
                type="password",
            )

            register_button = st.form_submit_button(
                "Create Account",
                use_container_width=True,
            )

        if register_button:

            username = username.strip()
            email = email.strip()

            if (
                not username
                or not email
                or not password
                or not confirm_password
            ):
                st.error("Please fill in all fields.")

            elif password != confirm_password:
                st.error("Passwords do not match.")

            elif len(password) < 8:
                st.error(
                    "Password must contain at least 8 characters."
                )

            else:
                try:
                    success, message = register_user(
                        username,
                        email,
                        password,
                    )

                    if success:
                        # Save the message and switch to Login.
                        st.session_state["registered_success"] = True
                        st.session_state["auth_page"] = "Login"

                        # Remove the registration form from the page.
                        st.rerun()

                    else:
                        st.error(message)

                except (ValueError, sqlite3.Error) as exc:
                    st.error(f"Registration failed: {exc}")

                except Exception as exc:
                    st.error(
                        f"Something went wrong: {exc}"
                    )

        st.markdown("---")

        if st.button(
            "Already have an account? Login",
            use_container_width=True,
        ):
            st.session_state["auth_page"] = "Login"
            st.rerun()

    st.info(
        "For privacy, only the owner of a qualifying lost report "
        "can view the matched finder's contact details."
    )


# Display Login/Register until the user logs in.
if st.session_state["user"] is None:
    show_authentication()
    st.stop()


# =========================================
# 5. CURRENT AUTHENTICATED USER
# =========================================

user = st.session_state["user"]
user_id = int(user["id"])


# =========================================
# 6. HEADER AND SIDEBAR
# =========================================

st.title("🔎 FindIt AI")
st.markdown("#### Smart Lost-and-Found Matching System")

st.caption(
    "Report items • Search reports • Discover possible matches"
)

st.sidebar.markdown("### 👤 My Account")
st.sidebar.write(f"Username: {user['username']}")
st.sidebar.caption(
    "Your private contact details are protected."
)

if st.sidebar.button(
    "Log Out",
    use_container_width=True,
):
    st.session_state["user"] = None
    st.session_state["auth_page"] = "Login"
    st.session_state["registered_success"] = False
    st.rerun()

menu = st.sidebar.selectbox(
    "📌 Navigation",
    [
        "Home",
        "Report Lost Item",
        "Report Found Item",
        "View Reports",
        "AI Match Results",
        "My Reports",
        "Analytics",
    ],
)

st.sidebar.divider()
st.sidebar.markdown("### 🔎 FindIt AI")
st.sidebar.write(
    "Helping people reconnect with lost belongings."
)
st.sidebar.caption("")


# =========================================
# 7. PUBLIC SEARCH
# =========================================

st.markdown("---")
st.subheader("🔍 Search Lost & Found Reports")

search_col, clear_col = st.columns([5, 1])

with search_col:
    search_query = st.text_input(
        "Search item name, color, category, location or description",
        placeholder="Try: blue bottle, wallet, college library...",
        label_visibility="collapsed",
        key="global_search",
    )

with clear_col:
    if st.button("Clear Search", use_container_width=True):
        st.session_state["global_search"] = ""
        st.rerun()

public_reports = get_public_reports()

if search_query.strip():

    st.markdown("### Search Results")

    if public_reports.empty:
        search_results = public_reports

    else:
        search_columns = [
            "item_name",
            "category",
            "color",
            "location",
            "description",
            "report_type",
        ]

        searchable_text = (
            public_reports[search_columns]
            .fillna("")
            .astype(str)
            .agg(" ".join, axis=1)
        )

        search_mask = searchable_text.str.contains(
            search_query.strip(),
            case=False,
            regex=False,
            na=False,
        )

        search_results = public_reports[search_mask]

    if search_results.empty:
        st.info("No matching reports found.")

    else:
        st.success(
            f"{len(search_results)} matching report(s) found."
        )

        for _, report in search_results.iterrows():

            with st.container(border=True):

                label = (
                    "🔴 LOST"
                    if report["report_type"] == "Lost"
                    else "🟢 FOUND"
                )

                st.markdown(
                    f"**{label} · {report['item_name']}**"
                )
                show_report_image(report.get("image_path"))

                st.write(
                    f"Category: {report['category'] or 'Not specified'}"
                )
                st.write(
                    f"Color: {report['color'] or 'Not specified'}"
                )
                st.write(
                    f"Location: {report['location'] or 'Not specified'}"
                )
                st.write(
                    f"Date: {report['report_date'] or 'Not specified'}"
                )

                if report["description"]:
                    st.write(
                        f"Description: {report['description']}"
                    )

                st.caption(
                    f"Report ID: {int(report['id'])}"
                )

        st.caption(
            "🔒 Phone numbers and email addresses are never shown "
            "in public search results."
        )

st.markdown("---")


# =========================================
# 8. HOME
# =========================================

if menu == "Home":

    reports = get_public_reports()

    lost_count = (
        int((reports["report_type"] == "Lost").sum())
        if not reports.empty else 0
    )

    found_count = (
        int((reports["report_type"] == "Found").sum())
        if not reports.empty else 0
    )

    st.header("Welcome to FindIt AI 👋")
    st.write(
        "A smart platform to report lost belongings "
        "and identify potentially matching found items."
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Reports", len(reports))
    col2.metric("Lost Items", lost_count)
    col3.metric("Found Items", found_count)

    st.markdown("### How It Works")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### 📝 Report")
        st.write("Submit your lost or found item details.")

    with col2:
        st.markdown("#### 🤖 AI Match")
        st.write("Compare item descriptions, dates, locations and available photos.")

    with col3:
        st.markdown("#### 🔐 Private Contact")
        st.write(
            "The owner of a qualifying lost report can "
            "view the finder's contact details."
        )

    st.info(
        "Contact details are shared only when the finder has explicitly "
        "given consent. A high similarity score is not proof of a match."
    )


# =========================================
# 9. REPORT LOST / FOUND ITEM
# =========================================

elif menu in ["Report Lost Item", "Report Found Item"]:

    is_lost = menu == "Report Lost Item"
    report_type = "Lost" if is_lost else "Found"

    st.header(
        "📝 Report a Lost Item"
        if is_lost
        else "📦 Report a Found Item"
    )

    with st.form("report_form", clear_on_submit=True):

        item_name = st.text_input("Item Name *")

        category = st.selectbox(
            "Category",
            [
                "Electronics",
                "Documents",
                "Bags",
                "Clothing",
                "Jewellery",
                "Accessories",
                "Other",
            ],
        )

        color = st.text_input("Item Color")

        if is_lost:
            location_label = "Where did you lose it? *"
            date_label = "Date Lost"
        else:
            location_label = "Where did you find it? *"
            date_label = "Date Found"

        location = st.text_input(location_label)

        report_date = st.date_input(
            date_label,
            value=date.today(),
            max_value=date.today(),
        )

        description = st.text_area("Item Description")

        uploaded_image = st.file_uploader(
            "Upload Item Photo (optional, max 5 MB)",
            type=["jpg", "jpeg", "png", "webp"],
            help="Use a clear photo of the item. JPG, PNG and WEBP are supported.",
        )

        st.markdown("### 🔒 Private Contact Details")
        st.caption(
            "Provide at least one contact method. "
            "These details are not included in public reports."
        )

        contact_email = st.text_input("Contact Email")
        contact_phone = st.text_input("Contact Phone Number")
        contact_share_consent = st.checkbox(
            "I agree that my contact details may be shared privately "
            "with the owner of a possible matching lost-item report.",
            value=False,
        )

        submitted = st.form_submit_button(
            "Submit Lost Report"
            if is_lost
            else "Submit Found Report",
            use_container_width=True,
        )

    if submitted:

        if not item_name.strip() or not location.strip():
            st.error(
                "Please enter the item name and location."
            )

        elif not contact_email.strip() and not contact_phone.strip():
            st.error(
                "Please provide at least one contact method."
            )

        else:
            image_path = None
            try:
                image_path = save_uploaded_image(uploaded_image)
                add_report(
                    user_id=user_id,
                    report_type=report_type,
                    item_name=item_name,
                    category=category,
                    color=color,
                    location=location,
                    report_date=report_date,
                    description=description,
                    contact_email=contact_email,
                    contact_phone=contact_phone,
                    image_path=image_path,
                    contact_share_consent=contact_share_consent,
                )

                st.success(
                    f"{report_type} report saved successfully. "
                    "Your contact details remain private."
                )

            except (ValueError, sqlite3.Error) as exc:
                if image_path:
                    saved_file = BASE_DIR / image_path
                    if saved_file.is_file():
                        saved_file.unlink()
                st.error(f"Could not save report: {exc}")


# =========================================
# 10. VIEW PUBLIC REPORTS
# =========================================

elif menu == "View Reports":

    st.header("📋 View Reports")

    report_filter = st.selectbox(
        "Filter by report type",
        ["All", "Lost", "Found"],
    )

    reports = get_public_reports(
        None if report_filter == "All" else report_filter
    )

    if reports.empty:
        st.info("No reports available yet.")

    else:
        st.dataframe(
            reports[
                [
                    "id",
                    "report_type",
                    "item_name",
                    "category",
                    "color",
                    "location",
                    "report_date",
                    "description",
                    "status",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        st.caption(
            "Private contact details and account IDs are excluded."
        )


# =========================================
# 11. AI MATCH RESULTS
# =========================================

elif menu == "AI Match Results":

    st.header("🤖 AI Match Results")

    lost_reports = get_public_reports("Lost")
    found_reports = get_public_reports("Found")
    my_reports = get_my_reports(user_id)

    my_lost_ids = set()

    if not my_reports.empty:
        my_lost_ids = set(
            my_reports.loc[
                my_reports["report_type"] == "Lost",
                "id",
            ].astype(int)
        )

    if lost_reports.empty or found_reports.empty:

        st.warning(
            "At least one Lost report and one Found report "
            "are required to calculate matches."
        )

    else:

        minimum_score = st.slider(
            "Minimum similarity score",
            min_value=0,
            max_value=100,
            value=20,
        )

        matches = []

        for _, lost in lost_reports.iterrows():
            for _, found in found_reports.iterrows():

                score = calculate_match(lost, found)

                if score >= minimum_score:
                    matches.append({
                        "lost": lost,
                        "found": found,
                        "score": score,
                    })

        matches.sort(
            key=lambda row: row["score"],
            reverse=True,
        )

        st.caption(
            "Combined score uses available text, date, location and photo signals. "
            "It does not prove that the items are the same."
        )

        if not matches:

            st.info(
                "No possible matches meet the selected threshold."
            )

        else:

            st.success(
                f"{len(matches)} possible match(es) found."
            )

            for match in matches[:50]:

                lost = match["lost"]
                found = match["found"]
                score = match["score"]
                _, score_details = calculate_match_details(lost, found)

                lost_id = int(lost["id"])
                found_id = int(found["id"])

                with st.container(border=True):

                    left, right = st.columns(2)

                    with left:
                        st.markdown("**🔴 Lost Item**")
                        show_report_image(lost.get("image_path"), width=190)
                        st.write(lost["item_name"])
                        st.caption(lost["location"])
                        st.caption(f"Report ID: {lost_id}")

                    with right:
                        st.markdown("**🟢 Found Item**")
                        show_report_image(found.get("image_path"), width=190)
                        st.write(found["item_name"])
                        st.caption(found["location"])
                        st.caption(f"Report ID: {found_id}")

                    st.progress(
                        min(100, max(0, int(score)))
                    )

                    st.write(
                        f"**Combined Similarity Score: {score}%**"
                    )
                    with st.expander("View matching factors"):
                        factor_labels = {
                            "item_type": "Item type / main keywords",
                            "brand": "Brand / company",
                            "model": "Model number",
                            "other_details": "Other supporting details",
                            "description": "Description overlap",
                            "category": "Category",
                            "location": "Location",
                            "color": "Color",
                            "date": "Date proximity",
                            "image": "Image appearance",
                        }
                        for factor, value in score_details.items():
                            if value is not None:
                                st.caption(f"{factor_labels[factor]}: {value}%")
                            else:
                                st.caption(f"{factor_labels[factor]}: Not available")

                    # Database function must verify report ownership
                    # and the >=75% threshold before returning contact.
                    if score >= 70 and lost_id in my_lost_ids:

                        contact = get_finder_contact_for_lost_owner(
                            lost_report_id=lost_id,
                            found_report_id=found_id,
                            requester_user_id=user_id,
                            score=score,
                        )

                        if contact is not None:

                            st.success(
                                "This match belongs to your lost report. "
                                "Finder contact details are shown privately."
                            )

                            if contact["contact_email"]:
                                st.write(
                                    "**Finder Email:** "
                                    + contact["contact_email"]
                                )

                            if contact["contact_phone"]:
                                st.write(
                                    "**Finder Phone:** "
                                    + contact["contact_phone"]
                                )

                            if (
                                not contact["contact_email"]
                                and not contact["contact_phone"]
                            ):
                                st.info(
                                    "The finder has not provided contact details."
                                )

                    elif score >= 70:

                        st.caption(
                            "🔒 Contact details are hidden. Only the owner "
                            "of the matching lost report can access them."
                        )


# =========================================
# 12. MY REPORTS
# =========================================

elif menu == "My Reports":

    st.header("🔐 My Reports")

    my_reports = get_my_reports(user_id)

    if my_reports.empty:

        st.info("You have not submitted any reports yet.")

    else:

        st.caption(
            "Only your own reports and their contact details "
            "are shown on this page."
        )

        for _, report in my_reports.iterrows():

            report_id = int(report["id"])

            with st.container(border=True):

                st.markdown(
                    f"**{report['report_type']} · "
                    f"{report['item_name']}**"
                )

                st.caption(f"Report ID: {report_id}")
                show_report_image(report.get("image_path"))

                st.write(
                    f"Category: {report['category'] or 'Not specified'}"
                )
                st.write(
                    f"Color: {report['color'] or 'Not specified'}"
                )
                st.write(
                    f"Location: {report['location'] or 'Not specified'}"
                )
                st.write(f"Date: {report['report_date']}")
                st.write(f"Status: {report['status']}")

                if report["description"]:
                    st.write(
                        f"Description: {report['description']}"
                    )

                with st.expander("🔒 View My Contact Details"):

                    st.write(
                        "Email: "
                        f"{report['contact_email'] or 'Not provided'}"
                    )
                    st.write(
                        "Phone: "
                        f"{report['contact_phone'] or 'Not provided'}"
                    )

                if report["status"] != "Returned":

                    if st.button(
                        "Mark as Returned",
                        key=f"returned_{report_id}",
                    ):

                        updated = update_report_status(
                            report_id,
                            user_id,
                            "Returned",
                        )

                        if updated:
                            st.success("Report status updated.")
                            st.rerun()
                        else:
                            st.error(
                                "Unable to update this report."
                            )


# =========================================
# 13. ANALYTICS
# =========================================

elif menu == "Analytics":

    st.header("📊 Analytics Dashboard")

    reports = get_public_reports()

    if reports.empty:

        st.info("Add reports to see analytics.")

    else:

        lost_count = int(
            (reports["report_type"] == "Lost").sum()
        )

        found_count = int(
            (reports["report_type"] == "Found").sum()
        )

        col1, col2, col3 = st.columns(3)

        col1.metric("Total Reports", len(reports))
        col2.metric("Lost Reports", lost_count)
        col3.metric("Found Reports", found_count)

        st.subheader("Reports by Type")

        type_counts = (
            reports["report_type"]
            .value_counts()
            .reindex(["Lost", "Found"], fill_value=0)
        )

        st.bar_chart(type_counts)

        st.subheader("Reports by Category")

        category_counts = (
            reports["category"]
            .fillna("Not specified")
            .value_counts()
        )

        st.bar_chart(category_counts)

        st.subheader("Recent Reports")

        st.dataframe(
            reports[
                [
                    "report_type",
                    "item_name",
                    "category",
                    "location",
                    "report_date",
                ]
            ].head(10),
            use_container_width=True,
            hide_index=True,
        )

        st.caption(
            "Analytics contains public report information only."
        )


# =========================================
# 14. FOOTER
# =========================================

st.markdown("---")

st.caption(
    "FindIt AI | Smart Lost-and-Found Matching System | "
    "Possible matches require human verification."
)
