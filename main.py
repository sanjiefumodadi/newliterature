import time
import concurrent.futures
from datetime import datetime

import streamlit as st

from api.pubmed_api import search_pubmed
from api.crossref_api import search_crossref
from api.openalex_api import search_openalex
from utils.data_process import merge_and_deduplicate, build_expanded_queries
from utils.translation import (
    should_show_translate_button,
    paper_translate_id,
    translate_paper_to_chinese,
)

SOURCE_LABELS = {
    "OpenAlex": "综合学术",
    "Crossref": "引文索引",
    "PubMed": "生物医学",
}


def ensure_state():
    defaults = {
        "last_query": "",
        "raw_results": [],
        "last_health": {"PubMed": "ok", "Crossref": "ok", "OpenAlex": "ok"},
        "last_elapsed": 0.0,
        "last_total": 0,
        "current_page": 1,
        "search_ready": False,
        "translated_states": {},
        "translated_cache": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def fetch_source_results(query, max_results, timeout_sec=6):
    api_health = {"PubMed": "ok", "Crossref": "ok", "OpenAlex": "ok"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            "PubMed": executor.submit(search_pubmed, query, max_results),
            "Crossref": executor.submit(search_crossref, query, max_results),
            "OpenAlex": executor.submit(search_openalex, query, max_results),
        }

        results = {"PubMed": [], "Crossref": [], "OpenAlex": []}
        for source_name, future in futures.items():
            try:
                results[source_name] = future.result(timeout=timeout_sec) or []
            except concurrent.futures.TimeoutError:
                api_health[source_name] = "timeout"
                results[source_name] = []
            except Exception:
                api_health[source_name] = "error"
                results[source_name] = []

    return results, api_health


def blend_by_source(papers, per_source_cap=180):
    grouped = {"OpenAlex": [], "Crossref": [], "PubMed": []}
    for paper in papers:
        src = paper.get("api_source")
        if src in grouped:
            grouped[src].append(paper)

    for src in grouped:
        grouped[src].sort(key=lambda item: item.get("citations", 0), reverse=True)
        grouped[src] = grouped[src][:per_source_cap]

    blended = []
    pointers = {"OpenAlex": 0, "Crossref": 0, "PubMed": 0}
    while True:
        progressed = False
        for src in ["OpenAlex", "Crossref", "PubMed"]:
            idx = pointers[src]
            if idx < len(grouped[src]):
                blended.append(grouped[src][idx])
                pointers[src] = idx + 1
                progressed = True
        if not progressed:
            break

    return blended


def run_search_pipeline(query, fetch_size):
    start = time.time()

    source_results, health = fetch_source_results(query, fetch_size)
    # 兼容处理：检查 merge_and_deduplicate 的参数签名，防止 Streamlit 环境缓存或未更新
    import inspect
    sig = inspect.signature(merge_and_deduplicate)
    kwargs = {}
    if "recent_years" in sig.parameters:
        kwargs["recent_years"] = None
    if "enrich_by_doi" in sig.parameters:
        kwargs["enrich_by_doi"] = False

    merged = merge_and_deduplicate(
        source_results["PubMed"] + source_results["Crossref"] + source_results["OpenAlex"],
        **kwargs
    )

    # 若召回不足，单关键词执行小范围扩展补召回。
    if len(query.split()) == 1 and len(merged) < 120:
        expansion_queries = build_expanded_queries(query, max_queries=5)[1:]
        for expand_query in expansion_queries:
            extra_results, extra_health = fetch_source_results(expand_query, max(40, fetch_size // 2))
            for src_name, status in extra_health.items():
                if health[src_name] == "ok" and status != "ok":
                    health[src_name] = status

            merged = merge_and_deduplicate(
                merged
                + extra_results["PubMed"]
                + extra_results["Crossref"]
                + extra_results["OpenAlex"],
                **kwargs
            )
            if len(merged) >= 220:
                break

    blended = blend_by_source(merged, per_source_cap=max(80, fetch_size))

    elapsed = time.time() - start
    return blended, health, elapsed


def normalize_year_value(year_text):
    if not year_text:
        return 0
    text = str(year_text).strip()
    return int(text) if text.isdigit() else 0


def get_click_url(paper):
    doi = str(paper.get("doi", "") or "").strip()
    url = str(paper.get("url", "") or "").strip()

    if doi and doi != "暂无数据":
        return f"https://doi.org/{doi}"
    if url:
        return url
    return ""


def apply_filters(papers, min_citations, year_start, year_end, selected_sources):
    filtered = []
    for paper in papers:
        citations = int(paper.get("citations", 0) or 0)
        year_val = normalize_year_value(paper.get("year"))
        src = paper.get("api_source", "")

        if citations < min_citations:
            continue
        if year_val and (year_val < year_start or year_val > year_end):
            continue
        if selected_sources and src not in selected_sources:
            continue

        if not paper.get("title"):
            continue

        filtered.append(paper)

    return filtered


def sort_results(papers, sort_mode):
    if sort_mode == "发表年份（新到旧）":
        return sorted(
            papers,
            key=lambda item: (
                normalize_year_value(item.get("year")),
                int(item.get("citations", 0) or 0),
            ),
            reverse=True,
        )

    # 默认：被引数高到低（你当前最核心需求）
    return sorted(
        papers,
        key=lambda item: (
            int(item.get("citations", 0) or 0),
            normalize_year_value(item.get("year")),
        ),
        reverse=True,
    )


def sidebar_filters(raw_results):
    with st.sidebar:
        st.markdown("## 筛选与排序")
        
        st.markdown("### 快速预设")
        current_year = datetime.now().year
        col1, col2 = st.columns(2)
        if col1.button("经典高被引", help="被引数≥100，不限年份", use_container_width=True):
            st.session_state["min_citations_input"] = 100
            st.session_state["year_range_slider"] = (1990, current_year)
            st.rerun()
            
        if col2.button("近五年热点", help="被引数≥0，近5年", use_container_width=True):
            st.session_state["min_citations_input"] = 0
            st.session_state["year_range_slider"] = (current_year - 5, current_year)
            st.rerun()

        st.markdown("---")

        if "min_citations_input" not in st.session_state:
            st.session_state["min_citations_input"] = 50
        min_citations = st.number_input("最低被引数", min_value=0, step=10, key="min_citations_input")

        if "year_range_slider" not in st.session_state:
            st.session_state["year_range_slider"] = (2000, current_year)
        year_range = st.slider(
            "发表年份范围",
            min_value=1990,
            max_value=current_year,
            step=1,
            key="year_range_slider"
        )

        selected_label_values = st.multiselect(
            "数据来源",
            options=["综合学术", "引文索引", "生物医学"],
            default=["综合学术", "引文索引", "生物医学"],
        )
        label_to_source = {v: k for k, v in SOURCE_LABELS.items()}
        selected_sources = [label_to_source[label] for label in selected_label_values]

        sort_mode = st.selectbox(
            "结果排序",
            options=["被引数（高到低）", "发表年份（新到旧）"],
            index=0,
        )
        page_size = st.selectbox("每页显示", options=[20, 30, 50], index=0)

        st.caption("默认按被引数排序，可直接得到高被引文献列表。")

        if raw_results:
            st.markdown("---")
            st.markdown("### 检索统计")
            src_counts = {"OpenAlex": 0, "Crossref": 0, "PubMed": 0}
            for p in raw_results:
                s = p.get("api_source")
                if s in src_counts:
                    src_counts[s] += 1
            
            st.markdown(f"**文献总数**: {len(raw_results)}")
            st.markdown(f"**综合学术**: {src_counts['OpenAlex']}")
            st.markdown(f"**引文索引**: {src_counts['Crossref']}")
            st.markdown(f"**生物医学**: {src_counts['PubMed']}")

    return min_citations, year_range, selected_sources, sort_mode, page_size


def render_top_banner():
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 18px;">
            <h1 style="font-size: 2.15em; color: #1f2d3d; font-weight: 700; letter-spacing: 0.01em; margin-bottom: 0.2rem;">智慧农业文献检索</h1>
            <p style="font-size: 1.0em; color: #6b7280; margin-top: 0;">高被引优先 · 多页结果 · 一键跳转原文链接</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_search_form():
    col_center = st.columns([1, 3, 1])[1]
    with col_center:
        with st.form("search_form", clear_on_submit=False):
            query = st.text_input(
                "输入关键词",
                value=st.session_state.get("last_query", ""),
                placeholder="例如: rice genomics",
                label_visibility="hidden",
            )
            submitted = st.form_submit_button("开始搜索", use_container_width=True)
    return query.strip(), submitted


def render_source_health(health):
    bad = [src for src, status in health.items() if status != "ok"]
    if not bad:
        return
    bad_text = "、".join(bad)
    st.info(f"网络波动提示：{bad_text} 当前响应较慢，系统已自动使用其余可用结果。")


def render_results(papers, query, elapsed, sort_mode, page_size):
    total_results = len(papers)
    total_pages = max(1, (total_results + page_size - 1) // page_size)

    if st.session_state["current_page"] > total_pages:
        st.session_state["current_page"] = total_pages
    if st.session_state["current_page"] < 1:
        st.session_state["current_page"] = 1

    current_page = st.session_state["current_page"]
    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_results)
    page_items = papers[start_idx:end_idx]

    # 生成可视化的筛选条件标签
    active_filters_html = ""
    min_c = st.session_state.get("min_citations_input", 0)
    y_range = st.session_state.get("year_range_slider", (1990, datetime.now().year))
    if min_c > 0:
        active_filters_html += f"<span style='background:#f3f4f6;color:#475569;padding:4px 10px;border-radius:999px;font-size:0.84rem;'>筛选被引≥{min_c}</span>"
    if y_range[0] > 1990 or y_range[1] < datetime.now().year:
        active_filters_html += f"<span style='background:#f3f4f6;color:#475569;padding:4px 10px;border-radius:999px;font-size:0.84rem;'>筛选年份:{y_range[0]}-{y_range[1]}</span>"

    st.subheader(f"搜索结果（共 {total_results} 条，耗时 {elapsed:.2f} 秒）")
    st.markdown(
        f"<div style='display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 10px 0;'>"
        f"<span style='background:#eef2ff;color:#243b6b;padding:4px 10px;border-radius:999px;font-size:0.84rem;'>关键词: {query}</span>"
        f"<span style='background:#fff7ed;color:#9a3412;padding:4px 10px;border-radius:999px;font-size:0.84rem;'>排序: {sort_mode}</span>"
        f"{active_filters_html}"
        f"<span style='background:#eff6ff;color:#1f3d63;padding:4px 10px;border-radius:999px;font-size:0.84rem;'>第 {current_page}/{total_pages} 页</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    nav1, nav2, nav3, nav4 = st.columns([1, 1.6, 1, 1])
    with nav1:
        if st.button("上一页", disabled=current_page <= 1):
            st.session_state["current_page"] = current_page - 1
            st.rerun()
    with nav2:
        jump_to = st.number_input("页码", min_value=1, max_value=total_pages, value=current_page, step=1)
    with nav3:
        if st.button("跳转"):
            st.session_state["current_page"] = int(jump_to)
            st.rerun()
    with nav4:
        if st.button("下一页", disabled=current_page >= total_pages):
            st.session_state["current_page"] = current_page + 1
            st.rerun()

    st.caption(f"当前显示 {start_idx + 1 if total_results else 0}-{end_idx} / {total_results}")

    if not page_items:
        st.warning("当前筛选条件下暂无可展示结果。")
        st.markdown("1. 降低最低被引数。")
        st.markdown("2. 放宽年份范围。")
        st.markdown("3. 保留全部数据来源后再试。")
        return

    for idx, paper in enumerate(page_items, start=start_idx + 1):
        show_trans_btn = should_show_translate_button(paper)
        pid = paper_translate_id(paper, idx)
        is_translated = st.session_state["translated_states"].get(pid, False)

        display_paper = paper
        if is_translated:
            if pid not in st.session_state["translated_cache"]:
                with st.spinner("翻译中..."):
                    st.session_state["translated_cache"][pid] = translate_paper_to_chinese(paper)
            display_paper = st.session_state["translated_cache"][pid]

        title = str(display_paper.get("title") or "暂无标题")
        authors = str(display_paper.get("authors") or "暂无作者")
        year = str(display_paper.get("year") or "未知年份")
        source = str(display_paper.get("source") or "未知来源")
        citations = int(display_paper.get("citations", 0) or 0)
        source_name = SOURCE_LABELS.get(display_paper.get("api_source", ""), display_paper.get("api_source", "未知"))
        link = get_click_url(display_paper)

        st.markdown("---")
        if link:
            st.markdown(f"### {idx}. [{title}]({link})")
        else:
            st.markdown(f"### {idx}. {title}")

        left, right = st.columns([5, 2])
        with left:
            st.markdown(
                f"<div style='font-size:0.97rem;color:#334155;line-height:1.55;'>"
                f"<b>{year}</b> · {authors} · <i>{source}</i>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with right:
            st.markdown(
                f"<div style='display:flex;flex-direction:column;gap:8px; margin-bottom:8px;'>"    
                f"<span style='background:#eff6ff;color:#1d4f91;border-radius:999px;padding:4px 10px;font-size:0.84rem;width:fit-content;'>来源 {source_name}</span>"
                f"<span style='background:#f5f3ff;color:#5b2d8c;border-radius:999px;padding:4px 10px;font-size:0.84rem;width:fit-content;'>被引 {citations}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if show_trans_btn:
                btn_label = "取消翻译" if is_translated else "翻译为中文"
                if st.button(btn_label, key=f"trans_btn_{pid}"):
                    st.session_state["translated_states"][pid] = not is_translated
                    st.rerun()

def main():
    st.set_page_config(page_title="智慧农业文献检索", page_icon=None, layout="wide")

    st.markdown(
        """
        <style>
            .block-container {max-width: 1240px; padding-top: 1.6rem; padding-bottom: 1.6rem;}
            [data-testid="stAppViewContainer"] {background: linear-gradient(180deg, #fbfcfe 0%, #ffffff 100%);}
            section[data-testid="stSidebar"] {border-right: 1px solid #e5e7eb; background: #f8fafc;}
            h3 {margin-top: 0.42rem; margin-bottom: 0.32rem; line-height: 1.35;}
            [data-testid="stMarkdownContainer"] p {line-height: 1.5;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    ensure_state()
    render_top_banner()

    query, submitted = render_search_form()
    
    raw_res = st.session_state.get("raw_results", [])
    min_citations, year_range, selected_sources, sort_mode, page_size = sidebar_filters(raw_res)

    if submitted:
        if not query:
            st.warning("请输入关键词后再搜索。")
        else:
            with st.spinner("正在检索并整合文献..."):
                fetch_size = 140 if len(query.split()) == 1 else 90
                raw_results, health, elapsed = run_search_pipeline(query, fetch_size)

            st.session_state["last_query"] = query
            st.session_state["raw_results"] = raw_results
            st.session_state["last_health"] = health
            st.session_state["last_elapsed"] = elapsed
            st.session_state["last_total"] = len(raw_results)
            st.session_state["current_page"] = 1
            st.session_state["search_ready"] = True

    if not st.session_state["search_ready"]:
        st.info("输入关键词后点击“开始搜索”，系统将默认按被引数从高到低返回多页文献。")
        return

    render_source_health(st.session_state["last_health"])

    filtered = apply_filters(
        papers=st.session_state["raw_results"],
        min_citations=min_citations,
        year_start=year_range[0],
        year_end=year_range[1],
        selected_sources=selected_sources,
    )
    sorted_results = sort_results(filtered, sort_mode)

    render_results(
        papers=sorted_results,
        query=st.session_state["last_query"],
        elapsed=st.session_state["last_elapsed"],
        sort_mode=sort_mode,
        page_size=page_size,
    )


if __name__ == "__main__":
    main()
