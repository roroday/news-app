import streamlit as st
import requests
import google.generativeai as genai
import json
import re
import difflib 
from gnews import GNews 

# --- 1. Page Config ---
st.set_page_config(
    page_title="NewsIQ: AI Briefs",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    div[data-testid="stExpander"] details summary p {
        font-weight: bold;
        font-size: 1.1rem;
    }
    div[data-testid="stImage"] img {
        border-radius: 10px;
    }
    div[data-testid="stContainer"] {
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    div[data-testid="stContainer"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 20px rgba(0,0,0,0.3);
        border: 1px solid #00ADB5;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. State Initialization ---
if 'study_list' not in st.session_state: st.session_state.study_list = []
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = None
if 'quiz_submitted' not in st.session_state: st.session_state.quiz_submitted = False
if 'analysis_cache' not in st.session_state: st.session_state.analysis_cache = {}
if 'quiz_mode' not in st.session_state: st.session_state.quiz_mode = False
if 'current_q_index' not in st.session_state: st.session_state.current_q_index = 0
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}

# --- 3. Helper Functions ---

def deduplicate_articles(articles):
    unique_articles = []
    def get_keywords(text):
        if not text: return set()
        clean = re.sub(r'[^a-zA-Z0-9\s]', '', text.lower())
        words = set(clean.split())
        stop_words = {'the', 'a', 'an', 'in', 'on', 'at', 'for', 'to', 'of', 'and', 'is', 'with', 'by', 'from', 'news', 'update', 'live', 'says', 'report'}
        return {w for w in words if w not in stop_words and len(w) > 2}

    for art in articles:
        current_keywords = get_keywords(art['title'])
        is_duplicate = False
        for existing_art in unique_articles:
            existing_keywords = get_keywords(existing_art['title'])
            overlap = current_keywords.intersection(existing_keywords)
            if not current_keywords or not existing_keywords: continue
            ratio = len(overlap) / len(current_keywords.union(existing_keywords))
            if ratio > 0.3 or len(overlap) >= 3: 
                is_duplicate = True
                if art.get('urlToImage') and not existing_art.get('urlToImage'):
                    unique_articles.remove(existing_art)
                    unique_articles.append(art)
                break
        if not is_duplicate: unique_articles.append(art)
    return unique_articles

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
    except: return None

def generate_quiz_json(text_chunk, num_q):
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"""
    Create {num_q} multiple-choice questions based on this text.
    Return strictly valid JSON array.
    IMPORTANT: The 'correct_answer' field must match the EXACT text of the option.
    Format:
    [
        {{
            "question": "Question?",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "A",
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
    except: return []

def submit_feedback_to_github(feedback_text, topic_request, rating):
    try:
        token = st.secrets["GITHUB_TOKEN"]
        owner = st.secrets["REPO_OWNER"]
        repo = st.secrets["REPO_NAME"]
        url = f"https://api.github.com/repos/{owner}/{repo}/issues"
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        title = f"📢 Feedback: {topic_request} ({rating}/5)"
        body = f"### User Feedback\n**Rating:** {rating}/5\n\n### Comments\n{feedback_text}\n\n### Topic Request\n{topic_request}"
        data = {"title": title, "body": body, "labels": ["feedback"]}
        res = requests.post(url, json=data, headers=headers)
        return res.status_code == 201
    except: return False

# --- 4. Fetch Functions ---

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_gnews_layer(query):
    articles = []
    # If query is empty, GNews returns Top Headlines (Random stuff). We prevent that.
    if not query or len(query.strip()) < 2: return []
    
    try:
        google_news = GNews(language='en', country='IN', period='2d', max_results=10)
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
    except: pass
    return articles

@st.cache_data(ttl=21600, show_spinner=False)
def fetch_newsdata_layer(query):
    articles = []
    if not query or len(query.strip()) < 2: return []

    try:
        nd_key = st.secrets.get("NEWSDATA_KEY", None)
        if nd_key:
            simple_query = query.replace('(', '').replace(')', '').split(" OR ")[0]
            url = f"https://newsdata.io/api/1/news?apikey={nd_key}&q={simple_query}&language=en"
            response = requests.get(url)
            data = response.json()
            if data.get("status") == "success":
                for item in data.get("results", [])[:5]:
                    articles.append({
                        "title": f"🇮🇳 {item.get('title')}", 
                        "description": item.get('description', 'Click to read more...'),
                        "url": item.get('link'),
                        "urlToImage": item.get('image_url'), 
                        "publishedAt": item.get('pubDate'),
                        "source": "NewsData"
                    })
    except: pass
    return articles

@st.cache_data(ttl=43200, show_spinner=False)
def fetch_newsapi_layer(api_key, query):
    articles = []
    if not query or len(query.strip()) < 2: return []
    
    try:
        url = "https://newsapi.org/v2/everything"
        params = {"apiKey": api_key, "q": query, "language": "en", "sortBy": "publishedAt", "pageSize": 15}
        response = requests.get(url, params=params)
        data = response.json()
        if data.get("status") == "ok":
            articles.extend(data.get("articles", []))
    except: pass
    return articles

def fetch_news(api_key, query):
    all_articles = []
    all_articles.extend(fetch_newsapi_layer(api_key, query))
    all_articles.extend(fetch_newsdata_layer(query))
    all_articles.extend(fetch_gnews_layer(query))
    return deduplicate_articles(all_articles)

# --- 5. Sidebar ---
with st.sidebar:
    st.header("⚙️ Settings")
    news_api_key = st.secrets.get("NEWS_API_KEY", None)
    gemini_api_key = st.secrets.get("GEMINI_API_KEY", None)
    if not news_api_key or not gemini_api_key:
        st.error("❌ Keys missing.")
        st.stop()
    genai.configure(api_key=gemini_api_key)

    st.divider()
    with st.expander("🛠️ Customize Feed", expanded=True):
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
        
        # Custom Search Setup
        topic_options = ["🔍 Custom Search"] + list(master_topics.keys())
        url_topics = st.query_params.get_all("topic")
        valid_defaults = [t for t in url_topics if t in topic_options]
        
        selected_topics = st.multiselect(
            "Topic List:", 
            options=topic_options, 
            default=valid_defaults, 
            label_visibility="collapsed"
        )
        st.query_params["topic"] = selected_topics
        
        # Use a Form to prevent premature searching
        custom_query = ""
        if "🔍 Custom Search" in selected_topics:
            with st.form("search_form"):
                st.caption("Type your topic below:")
                raw_query = st.text_input("Search Keyword:", placeholder="e.g. SpaceX", label_visibility="collapsed")
                submitted = st.form_submit_button("Search 🔎")
                if submitted:
                    custom_query = raw_query
                    st.session_state['saved_custom_query'] = raw_query # Save for reloads
                elif 'saved_custom_query' in st.session_state:
                    custom_query = st.session_state['saved_custom_query']

    # --- STUDY LIST MANAGEMENT ---
    st.divider()
    st.header("📚 Study List")
    if not st.session_state.study_list:
        st.caption("No articles saved yet.")
    else:
        st.write(f"**{len(st.session_state.study_list)} Articles**")
        for i, article in enumerate(st.session_state.study_list):
            col_txt, col_btn = st.columns([4, 1])
            col_txt.caption(f"{i+1}. {article['title'][:25]}...")
            if col_btn.button("❌", key=f"rem_{i}"):
                st.session_state.study_list.pop(i)
                st.rerun()

        if st.button("📝 Start Quiz", type="primary", use_container_width=True):
            with st.spinner("Generating..."):
                full_text = " ".join([f"{a['title']} {a['description']}" for a in st.session_state.study_list])
                num_articles = len(st.session_state.study_list)
                q_count = 10 if num_articles == 1 else num_articles * 5
                st.session_state.quiz_data = generate_quiz_json(full_text, q_count)
                st.session_state.quiz_mode = True
                st.session_state.current_q_index = 0
                st.session_state.user_answers = {}
                st.session_state.quiz_submitted = False
                st.rerun()

    st.divider()
    with st.expander("🚀 Release Notes"):
        st.caption("Latest Updates")
        st.markdown("""
        **v1.6 - Search & Stability (Dec 2)**
        - Fixed crash when no topics selected.
        - Improved Custom Search (now requires button press).
        **v1.5 - Focus Mode**
        - Moved Quiz to central mobile-friendly card.
        """)
    
    with st.expander("💬 Feedback"):
        with st.form("feedback_form"):
            topic_req = st.text_input("Request Topic")
            feedback_text = st.text_area("Bugs/Suggestions")
            rating = st.slider("Rating", 1, 5, 5)
            if st.form_submit_button("Submit"):
                if submit_feedback_to_github(feedback_text, topic_req, rating): st.success("Sent!")
                else: st.error("Error sending.")

# --- 6. Main Layout ---
col_head_1, col_head_2 = st.columns([3, 1])
with col_head_1: st.title("🧠 NewsIQ")
with col_head_2:
    if st.session_state.quiz_mode:
        if st.button("❌ Exit Quiz", use_container_width=True):
            st.session_state.quiz_mode = False
            st.rerun()

# === MODE SWITCH ===
if st.session_state.quiz_mode and st.session_state.quiz_data:
    # QUIZ MODE Logic
    total_q = len(st.session_state.quiz_data)
    current_q = st.session_state.current_q_index
    progress = (current_q + 1) / total_q
    st.progress(progress)
    
    q_data = st.session_state.quiz_data[current_q]
    
    with st.container(border=True):
        st.subheader(f"Question {current_q + 1} of {total_q}")
        st.markdown(f"### {q_data['question']}")
        
        answer = st.radio("Select an answer:", q_data['options'], key=f"q_radio_{current_q}", index=None if current_q not in st.session_state.user_answers else q_data['options'].index(st.session_state.user_answers[current_q]))
        if answer: st.session_state.user_answers[current_q] = answer
        st.write("---")
        
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            if current_q > 0:
                if st.button("⬅️ Previous"):
                    st.session_state.current_q_index -= 1
                    st.rerun()
        with c3:
            if current_q < total_q - 1:
                if st.button("Next ➡️"):
                    st.session_state.current_q_index += 1
                    st.rerun()
            else:
                if st.button("Submit ✅", type="primary"):
                    st.session_state.quiz_submitted = True
                    st.rerun()

    if st.session_state.quiz_submitted:
        st.divider()
        st.header("📊 Results")
        score = 0
        for idx, q in enumerate(st.session_state.quiz_data):
            user_ans = st.session_state.user_answers.get(idx)
            if user_ans == q['correct_answer']: score += 1
            with st.expander(f"Q{idx+1}: {q['question']}"):
                if user_ans == q['correct_answer']: st.success(f"✅ Correct! ({user_ans})")
                else: 
                    st.error(f"❌ You chose: {user_ans}")
                    st.success(f"Correct: {q['correct_answer']}")
                if 'explanation' in q: st.info(f"💡 {q['explanation']}")
        
        final_score = (score / total_q) * 100
        c1, c2 = st.columns(2)
        c1.metric("Score", f"{score}/{total_q}")
        c2.metric("Accuracy", f"{final_score:.0f}%")
        if final_score == 100: st.balloons()

else:
    # FEED MODE
    if not selected_topics:
        # Welcome Screen (Fixes the st.tabs error)
        st.info("👈 **Start Here!** Open the Sidebar menu to select topics.")
        c1, c2, c3 = st.columns(3)
        with c1: st.container(border=True).markdown("#### 1. Select Topics\nChoose from Tech, Crypto, Sports...")
        with c2: st.container(border=True).markdown("#### 2. Analyze with AI\nGet instant summaries.")
        with c3: st.container(border=True).markdown("#### 3. Gamify\nTake a Master Quiz.")
    else:
        tabs = st.tabs(selected_topics)
        for i, tab_name in enumerate(selected_topics):
            with tabs[i]:
                # --- DYNAMIC QUERY LOGIC ---
                if tab_name == "🔍 Custom Search":
                    if custom_query:
                        query = custom_query
                        st.caption(f"Showing results for: **{query}**")
                    else:
                        st.info("👈 Enter a keyword in the sidebar and click **Search**.")
                        st.stop()
                else:
                    query = master_topics[tab_name]

                data_key = f"data_{tab_name}_{query}"
                if data_key not in st.session_state:
                    with st.spinner(f"Fetching {query}..."):
                        st.session_state[data_key] = fetch_news(news_api_key, query)
                
                articles = st.session_state[data_key]
                if not articles: st.warning("No articles found.")
                else:
                    cols = st.columns(3)
                    for idx, art in enumerate(articles):
                        with cols[idx % 3]: 
                            with st.container(border=True):
                                st.caption(f"{str(art.get('title', ''))[:2]} {tab_name} • {str(art.get('publishedAt', ''))[:10]}")
                                img_url = art.get('urlToImage') or "https://placehold.co/600x400?text=News"
                                st.image(img_url, use_container_width=True)
                                
                                is_in_list = any(a['title'] == art['title'] for a in st.session_state.study_list)
                                if is_in_list:
                                    st.success("✅ Saved")
                                else:
                                    if st.button("➕ Study", key=f"std_{i}_{idx}", use_container_width=True):
                                        st.session_state.study_list.append(art)
                                        st.toast("Saved!")
                                        st.rerun()

                                with st.expander(art['title']):
                                    st.write(art.get('description', ''))
                                    st.markdown(f"[🔗 Read Source]({art['url']})")
                                    cache_key = art['title']
                                    if st.button("🤖 Analyze", key=f"anl_{i}_{idx}"):
                                        with st.spinner("Thinking..."):
                                            analysis = generate_deep_dive(f"{art['title']} {art['description']}")
                                            if analysis: st.session_state.analysis_cache[cache_key] = analysis
                                    if cache_key in st.session_state.analysis_cache:
                                        d = st.session_state.analysis_cache[cache_key]
                                        st.info(f"**Summary:** {d['summary']}")
                                        st.write(f"**Keywords:** {', '.join(d['keywords'])}")
                                        for p in d['talking_points']: st.markdown(f"- {p}")