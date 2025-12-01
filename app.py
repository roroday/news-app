import streamlit as st
import requests
import google.generativeai as genai
import json
import re
from gnews import GNews 

# --- 1. Page Config & CSS ---
st.set_page_config(
    page_title="NewsIQ: AI Briefs",  # <--- Change this
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* Card Look */
    div[data-testid="stExpander"] details summary p {
        font-weight: bold;
        font-size: 1.1rem;
    }
    div[data-testid="stImage"] img {
        border-radius: 10px;
    }
    /* Card Hover Effect */
    div[data-testid="stContainer"] {
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    div[data-testid="stContainer"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 20px rgba(0,0,0,0.3);
        border: 1px solid #00ADB5;
    }
    /* Metric Styling */
    div[data-testid="stMetricValue"] {
        font-size: 2rem !important;
        color: #00ADB5 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. State Initialization ---
if 'study_list' not in st.session_state: st.session_state.study_list = []
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = None
if 'quiz_submitted' not in st.session_state: st.session_state.quiz_submitted = False
if 'analysis_cache' not in st.session_state: st.session_state.analysis_cache = {}

# --- 3. Functions ---

@st.cache_data(ttl=3600)
def fetch_news(api_key, query):
    articles = []
    
    # --- SOURCE 1: GNEWS (Real-time, Headlines) ---
    try:
        # We limit to 3 to keep it fast
        google_news = GNews(language='en', country='IN', period='1d', max_results=3)
        g_resp = google_news.get_news(query)
        for item in g_resp:
            articles.append({
                "title": f"⚡ {item.get('title')}", 
                "description": item.get('description', 'Live update from Google News.'),
                "url": item.get('url'),
                "urlToImage": None, 
                "publishedAt": item.get('published date'),
                "source": "GNews"
            })
    except:
        pass # If GNews fails, just keep going

    # --- SOURCE 2: NEWSDATA.IO (Good for Indian/Regional context) ---
    try:
        nd_key = st.secrets["NEWSDATA_KEY"]
        # NewsData requires simplified queries (no complex AND/OR logic in free tier sometimes)
        # So we take the first few words of your query to be safe
        simple_query = query.replace('(', '').replace(')', '').split(" OR ")[0]
        
        url = f"https://newsdata.io/api/1/news?apikey={nd_key}&q={simple_query}&language=en"
        response = requests.get(url)
        data = response.json()
        
        if data.get("status") == "success":
            for item in data.get("results", [])[:3]: # Limit to 3
                articles.append({
                    "title": f"🇮🇳 {item.get('title')}", # Flag to show it's from NewsData
                    "description": item.get('description', 'Click to read more...'),
                    "url": item.get('link'),
                    "urlToImage": item.get('image_url'), # They provide images!
                    "publishedAt": item.get('pubDate'),
                    "source": "NewsData"
                })
    except:
        pass

    # --- SOURCE 3: NEWSAPI (Global, High Quality Images) ---
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "apiKey": api_key,
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 8 # Get 8 from here
        }
        response = requests.get(url, params=params)
        data = response.json()
        
        if data.get("status") == "ok":
            news_api_articles = data.get("articles", [])
            articles.extend(news_api_articles)
            
    except:
        pass
        
    return articles

def generate_deep_dive(article_text):
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"""
    Analyze this news article for a Product Management interview.
    Return strictly valid JSON.
    Format:
    {{
        "keywords": ["keyword1", "keyword2", "keyword3"],
        "talking_points": ["Point 1", "Point 2", "Point 3"],
        "summary": "One sentence executive summary."
    }}
    Article: {article_text}
    """
    try:
        res = model.generate_content(prompt)
        clean = res.text.replace("```json", "").replace("```", "").strip()
        match = re.search(r'\{.*\}', clean, re.DOTALL)
        return json.loads(match.group(0)) if match else json.loads(clean)
    except:
        return None

def generate_quiz_json(text_chunk, num_q):
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"""
    Create {num_q} difficult multiple-choice questions based on this text.
    Return strictly valid JSON array.
    
    IMPORTANT: The 'correct_answer' field must match the EXACT text of the option.
    
    Format:
    [
        {{
            "question": "Question?",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_answer": "Option A",
            "explanation": "Why A is correct."
        }}
    ]
    
    Text: {text_chunk}
    """
    try:
        res = model.generate_content(prompt)
        clean = res.text.replace("```json", "").replace("```", "").strip()
        match = re.search(r'\[.*\]', clean, re.DOTALL)
        return json.loads(match.group(0)) if match else json.loads(clean)
    except:
        return []


def submit_feedback_to_github(feedback_text, topic_request, rating):
    token = st.secrets["GITHUB_TOKEN"]
    owner = st.secrets["REPO_OWNER"]
    repo = st.secrets["REPO_NAME"]
    
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # The Template for the GitHub Issue
    issue_title = f"📢 Feedback: {topic_request} ({rating}/5)"
    issue_body = f"""
    ### 👤 User Feedback
    **Rating:** {rating}/5
    
    ### 📝 Comments
    {feedback_text}
    
    ### 🚀 Topic Request
    {topic_request}
    
    ---
    *Submitted via Streamlit App*
    """
    
    data = {"title": issue_title, "body": issue_body, "labels": ["feedback"]}
    
    response = requests.post(url, json=data, headers=headers)
    return response.status_code == 201

# --- 4. Sidebar Logic ---
with st.sidebar:
    st.header("⚙️ Settings")
    news_api_key = st.secrets.get("NEWS_API_KEY", None)
    gemini_api_key = st.secrets.get("GEMINI_API_KEY", None)

    if not news_api_key or not gemini_api_key:
        st.error("❌ Keys missing in .streamlit/secrets.toml")
        st.stop()

    genai.configure(api_key=gemini_api_key)
    # --- FEEDBACK SYSTEM ---
    st.divider()
    with st.expander("💬 Feedback & Requests"):
        st.write("What topics should we add next?")
        
        with st.form("feedback_form"):
            topic_req = st.text_input("Topic Request (e.g. 'SpaceX', 'Fashion')")
            feedback_text = st.text_area("Any bugs or suggestions?")
            rating = st.slider("Rate the app", 1, 5, 5)
            
            if st.form_submit_button("Submit Feedback"):
                if submit_feedback_to_github(feedback_text, topic_req, rating):
                    st.success("✅ Feedback sent to developer!")
                    st.balloons()
                else:
                    st.error("❌ Could not send. Check GitHub settings.")

  # --- FEED CUSTOMIZER (The "Settings" Panel) ---
    st.divider()
    with st.expander("🛠️ Customize Your Feed", expanded=True):
        st.caption("Select topics to display on your dashboard:")
        
        # MASTER TOPIC LIST
        master_topics = {
            "Product Management": '("Product Launch" OR "New Feature" OR "UX Design" OR "App Update" OR "SaaS Metrics") AND NOT (Job OR Hiring)',
            "Indian Biz Giants": '("Tata Group" OR "Reliance Industries" OR "Adani" OR "Infosys" OR "HDFC Bank" OR "Sensex")',
            "Tech Infrastructure": '("Data Center" OR "Microchip" OR "Semiconductor" OR "Cloud Computing" OR "NVIDIA")',
            "AI & GenAI": '("Generative AI" OR "OpenAI" OR "LLM" OR "Machine Learning" OR "Gemini")',
            "EdTech": '("EdTech" OR "Online Learning" OR "Coursera" OR "Byju" OR "PhysicsWallah")',
            "Crypto & Web3": '("Bitcoin" OR "Ethereum" OR "Blockchain" OR "Web3")',
            "Indian Startups": '("Startup India" OR "Unicorn" OR "Venture Capital India" OR "Zepto" OR "Swiggy")',
            "Global Business": '("Wall Street" OR "Fed Rate" OR "Recession" OR "Global Economy" OR "Oil Prices")',
            "National (India)": '("India Politics" OR "Government of India" OR "Delhi" OR "Mumbai" OR "Bangalore News")',
            "Sports": '("Cricket" OR "Virat Kohli" OR "IPL" OR "BCCI" OR "Indian Football")',
            "Entertainment": '("Bollywood" OR "Cinema" OR "Movie Release" OR "Shah Rukh Khan" OR "Box Office")',
            "Books and Authors": '("Book Release" OR "Author Interview" OR "Bestseller" OR "Literature Festival")',
            "International": '("Geopolitics" OR "United Nations" OR "International Relations" OR "War" OR "Diplomacy")',
            "Marketing & Sales": '("SEO" OR "Content Strategy" OR "Sales Growth" OR "Customer Acquisition") AND NOT ("Digital Marketing" OR "Social Media")',
            "Fashion & Lifestyle": '("Fashion Trends" OR "Lifestyle Brands" OR "Sustainable Fashion" OR "Designer Collections")',
            "FMCG": '("Fast-Moving Consumer Goods" OR "FMCG Brands" OR "Consumer Behavior" OR "Retail Market")',
        }

        # --- NEW LOGIC: URL PERSISTENCE ---
        # 1. check if topics exist in URL
        url_topics = st.query_params.get_all("topic")
        
        # 2. If URL has topics, verify they are valid. If not, use hardcoded default.
        if url_topics:
            # Filter out any topics that might not exist in our master list anymore
            valid_defaults = [t for t in url_topics if t in master_topics]
            if valid_defaults:
                default_options = valid_defaults
            else:
                default_options = ["Product Management", "Tech Infrastructure", "Indian Biz Giants", "National (India)"]
        else:
            default_options = ["Product Management", "Tech Infrastructure", "Indian Biz Giants", "National (India)"]
        
        # 3. Create the Multiselect
        selected_topics = st.multiselect(
            "Topic List:",
            options=list(master_topics.keys()),
            default=default_options,
            label_visibility="collapsed"
        )
        
        # 4. Sync Selection BACK to URL
        # This updates the browser URL bar instantly when they change selection
        st.query_params["topic"] = selected_topics

    # --- QUIZ SECTION ---
    st.divider()
    st.header("📝 Master Quiz")
    
    if not st.session_state.study_list:
        st.caption("Read articles & click 'Study This' to unlock.")
    else:
        num_articles = len(st.session_state.study_list)
        st.write(f"**{num_articles} Articles Queued**")
        
        if st.button("Generate Quiz", type="primary"):
            with st.spinner("Crafting questions..."):
                full_text = " ".join([f"{a['title']} {a['description']}" for a in st.session_state.study_list])
                
                # Logic: 10 mins if 1 article, else 5 per article
                if num_articles == 1:
                    q_count = 10
                else:
                    q_count = num_articles * 5
                
                st.session_state.quiz_data = generate_quiz_json(full_text, q_count)
                st.session_state.quiz_submitted = False
                st.rerun()

    if st.session_state.quiz_data:
        if not st.session_state.quiz_submitted:
            with st.form("quiz_form"):
                user_answers = {}
                for idx, q in enumerate(st.session_state.quiz_data):
                    st.markdown(f"**{idx+1}. {q['question']}**")
                    user_answers[idx] = st.radio("Choose:", q['options'], key=f"q_{idx}", index=None)
                    st.write("---")
                
                if st.form_submit_button("Submit Quiz"):
                    st.session_state.user_answers = user_answers
                    st.session_state.quiz_submitted = True
                    st.rerun()
        else:
            # RESULTS
            st.success("📊 Quiz Results")
            score = 0
            for idx, q in enumerate(st.session_state.quiz_data):
                user_ans = st.session_state.user_answers.get(idx)
                correct_ans = q['correct_answer']
                with st.expander(f"Q{idx+1}: {q['question']}", expanded=True):
                    if user_ans == correct_ans:
                        st.success(f"✅ Correct! ({user_ans})")
                        score += 1
                    else:
                        st.error(f"❌ You chose: {user_ans}")
                        st.success(f"Correct Answer: {correct_ans}")
                    if 'explanation' in q:
                        st.info(f"💡 **Insight:** {q['explanation']}")
            
            final_score = (score / len(st.session_state.quiz_data)) * 100
            st.divider()
            col1, col2 = st.columns(2)
            col1.metric("Score", f"{score}/{len(st.session_state.quiz_data)}")
            col2.metric("Accuracy", f"{final_score:.0f}%")
            st.progress(final_score / 100)
            
            import pandas as pd
            chart_data = pd.DataFrame({
                "Status": ["Correct", "Wrong"],
                "Count": [score, len(st.session_state.quiz_data) - score]
            })
            st.bar_chart(chart_data, x="Status", y="Count", color="Status") 

            if final_score == 100:
                st.balloons()
                st.success("🏆 Perfect Score!")
            elif final_score > 70:
                st.info("👏 Good job!")
            else:
                st.warning("⚠️ Keep studying.")
            
            if st.button("Start New Quiz"):
                st.session_state.quiz_data = None
                st.session_state.quiz_submitted = False
                st.rerun()

# --- 5. Main Layout ---
st.title("🧠 NewsIQ: Read, Analyze, Gamify")

if not selected_topics:
    st.warning("👈 Please select at least one topic in the sidebar!")
else:
    tabs = st.tabs(selected_topics)

    for i, tab_name in enumerate(selected_topics):
        with tabs[i]:
            # Get the query for this specific topic
            query = master_topics[tab_name]
            
            # Use session state to store data so it doesn't reload on every click
            data_key = f"data_{tab_name}"
            
            if data_key not in st.session_state:
                with st.spinner(f"Fetching {tab_name} news..."):
                    st.session_state[data_key] = fetch_news(news_api_key, query)
            
            articles = st.session_state[data_key]
            
            if not articles:
                st.info(f"No recent articles found for {tab_name}. Try another topic.")
            else:
                # GRID LAYOUT (3 columns)
                cols = st.columns(3)
                for idx, art in enumerate(articles):
                    with cols[idx % 3]: 
                        with st.container(border=True):
                            st.caption(f"📌 {tab_name} • ⏱️ {art['publishedAt'][:10]}")

                            img_url = art.get('urlToImage') or "https://placehold.co/600x400?text=News"
                            st.image(img_url, use_container_width=True)

                            with st.expander(art['title']):
                                st.write(art.get('description', ''))
                                st.markdown(f"[🔗 Read Source]({art['url']})")
                                
                                cache_key = art['title']
                                if st.button("🤖 Analyze", key=f"analyze_{i}_{idx}"):
                                    with st.spinner("Analyzing..."):
                                        analysis = generate_deep_dive(f"{art['title']} {art['description']}")
                                        if analysis:
                                            st.session_state.analysis_cache[cache_key] = analysis
                                
                                if cache_key in st.session_state.analysis_cache:
                                    data = st.session_state.analysis_cache[cache_key]
                                    st.info(f"**Summary:** {data['summary']}")
                                    st.markdown("**🔑 Key Terms:**")
                                    st.write(", ".join(data['keywords']))
                                    st.markdown("**🗣️ Talking Points:**")
                                    for p in data['talking_points']:
                                        st.markdown(f"- {p}")

                                if any(a['title'] == art['title'] for a in st.session_state.study_list):
                                    st.success("✅ In Study List")
                                else:
                                    if st.button("➕ Study This", key=f"add_{i}_{idx}"):
                                        st.session_state.study_list.append(art)
                                        st.toast("Added to Study List")
                                        st.rerun()