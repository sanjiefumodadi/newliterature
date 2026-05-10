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


@st.cache_data(ttl=3600, show_spinner=False)
@st.cache_data(ttl=3600, show_spinner=False)
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


import re

def compute_relevance(paper, query):
    if not query:
        return 1.0, True
    
    terms = [t.lower() for t in query.split()]
    title = str(paper.get("title", "") or "").lower()
    abstract = str(paper.get("abstract", "") or "").lower()
    
    score = 0.0
    hit_in_core = False
    
    for term in terms:
        t_count = title.count(term)
        a_count = abstract.count(term)
        
        if t_count > 0 or a_count > 0:
            hit_in_core = True
            
        score += (t_count * 5.0) + (a_count * 1.0)
        
    return score, hit_in_core

def apply_filters(papers, min_citations, year_start, year_end, selected_sources, query=""):
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
            
        # Hard filter & Scoring
        score, hit_core = compute_relevance(paper, query)
        if query and not hit_core:
            continue  # 步骤10：做硬过滤

        paper["relevance_score"] = score
        filtered.append(paper)

    return filtered


def sort_results(papers, sort_mode):
    if sort_mode == "综合相关度":
        return sorted(
            papers,
            key=lambda item: (
                item.get("relevance_score", 0),
                int(item.get("citations", 0) or 0),
                normalize_year_value(item.get("year")),
            ),
            reverse=True,
        )
    elif sort_mode == "发表年份（新到旧）":
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


        if raw_results:
            import pandas as pd
            import altair as alt
            st.markdown("---")
            st.markdown("**按年份筛选**")
            years = [int(p.get("year", 0)) for p in raw_results if str(p.get("year", 0)).isdigit()]
            valid_years = [y for y in years if 1990 <= y <= current_year]
            if valid_years:
                year_counts = pd.Series(valid_years).value_counts().sort_index().reset_index()
                year_counts.columns = ['年份', '篇数']
                chart = alt.Chart(year_counts).mark_bar(color='#64748b').encode(
                    x=alt.X('年份:O', axis=alt.Axis(labelAngle=0, title='')),
                    y=alt.Y('篇数:Q', axis=alt.Axis(title='')),
                    tooltip=['年份', '篇数']
                ).properties(height=100)
                st.altair_chart(chart, use_container_width=True)
        
        st.markdown("**范围调节**")
        if "year_range_slider" not in st.session_state:
            st.session_state["year_range_slider"] = (2000, current_year)
        year_range = st.slider(
            "年份范围",
            min_value=1990,
            max_value=current_year,
            step=1,
            key="year_range_slider"
        )

        # 计算每个来源的文献数量
        source_counts = {"OpenAlex": 0, "Crossref": 0, "PubMed": 0}
        if raw_results:
            for p in raw_results:
                s = p.get("api_source")
                if s in source_counts:
                    source_counts[s] += 1
        
        # 构建包含数量的选项标签
        options_with_counts = [
            f"{SOURCE_LABELS['OpenAlex']} ({source_counts['OpenAlex']}篇)",
            f"{SOURCE_LABELS['Crossref']} ({source_counts['Crossref']}篇)",
            f"{SOURCE_LABELS['PubMed']} ({source_counts['PubMed']}篇)",
        ]
        
        selected_label_values = st.multiselect(
            "数据来源",
            options=options_with_counts,
            default=options_with_counts,
        )
        label_to_source = {v.split(' (')[0]: k for k, v in SOURCE_LABELS.items()}
        selected_sources = [label_to_source[label.split(' (')[0]] for label in selected_label_values]

        sort_mode = st.selectbox(
            "结果排序",
            options=["被引数（高到低）", "发表年份（新到旧）", "综合相关度"],
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

            source_chart_data = {
                SOURCE_LABELS["OpenAlex"]: src_counts["OpenAlex"],
                SOURCE_LABELS["Crossref"]: src_counts["Crossref"],
                SOURCE_LABELS["PubMed"]: src_counts["PubMed"],
            }
            st.bar_chart(source_chart_data)

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

    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.subheader("检索分析与结果洞察")
        st.markdown(f"**找到关于 \"{query}\" 的文献共 {total_results} 条，当前显示第 {start_idx + 1 if total_results else 0}-{end_idx} 条。** (查询耗时: {elapsed:.2f}s)")
    with col_h2:
        if total_results > 0:
            import io
            import csv
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=["title", "authors", "year", "source", "citations", "api_source", "doi", "url"])
            writer.writeheader()
            for p in papers:
                writer.writerow({
                    "title": p.get("title", ""),
                    "authors": p.get("authors", ""),
                    "year": p.get("year", ""),
                    "source": p.get("source", ""),
                    "citations": p.get("citations", ""),
                    "api_source": p.get("api_source", ""),
                    "doi": str(p.get("doi", "") or "").strip(),
                    "url": str(p.get("url", "") or "").strip()
                })
            csv_data = output.getvalue().encode('utf-8-sig')
            st.download_button("📥 导出结果 (CSV)", data=csv_data, file_name="search_results.csv", mime="text/csv", use_container_width=True)

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
        if st.button("⬅️ 上一页", disabled=current_page <= 1, use_container_width=True):
            st.session_state["current_page"] = current_page - 1
            st.rerun()
    with nav2:
        jump_to = st.number_input("页码", min_value=1, max_value=total_pages, value=current_page, step=1, label_visibility="collapsed")
    with nav3:
        if st.button("跳转", use_container_width=True):
            st.session_state["current_page"] = int(jump_to)
            st.rerun()
    with nav4:
        if st.button("下一页 ➡️", disabled=current_page >= total_pages, use_container_width=True):
            st.session_state["current_page"] = current_page + 1
            st.rerun()

    if not page_items:
        st.info("💡 当前筛选条件下暂无可展示结果，您可以尝试：")
        st.markdown("- 降低左侧的 **最低被引数** 要求")
        st.markdown("- 放宽 **年份范围**")
        st.markdown("- 勾选更多的 **数据库来源**")
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
            abstract = str(display_paper.get("abstract", "") or "").strip()
            if abstract and abstract != "暂无摘要" and abstract != "暂无数据":
                with st.expander("查看摘要 / Show Abstract"):
                    st.markdown(f"<div style='font-size:0.9rem;color:#475569;line-height:1.6;'>{abstract}</div>", unsafe_allow_html=True)
        with right:
            st.markdown(
                f"<div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;'>"
                f"<span style='background:#fef08a;color:#713f12;border-radius:999px;padding:3px 8px;font-size:0.80rem;font-weight:500;'>[{year}年]</span>"
                f"<span style='background:#dbeafe;color:#0c4a6e;border-radius:999px;padding:3px 8px;font-size:0.80rem;font-weight:500;'>[引: {citations}]</span>"
                f"<span style='background:#f3e8ff;color:#581c87;border-radius:999px;padding:3px 8px;font-size:0.80rem;font-weight:500;'>[{source_name}]</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='display:flex;flex-direction:column;gap:8px; margin-bottom:8px;'>"    
                f"<span style='background:#eff6ff;color:#1d4f91;border-radius:999px;padding:4px 10px;font-size:0.84rem;width:fit-content;'>来源: {source_name}</span>"
                f"<span style='background:#f5f3ff;color:#5b2d8c;border-radius:999px;padding:4px 10px;font-size:0.84rem;width:fit-content;'>被引: {citations}</span>"
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
            with st.status("正在执行多源文献检索...", expanded=True) as status:
                st.write("⏳ 并发请求 OpenAlex / PubMed / Crossref ...")
                fetch_size = 140 if len(query.split()) == 1 else 90
                raw_results, health, elapsed = run_search_pipeline(query, fetch_size)
                
                st.write("🔄 合并结果与排重清洗计算...")
                bad_srcs = [k for k, v in health.items() if v != 'ok']
                if bad_srcs:
                    status.update(label=f"部分数据源超时，已自动降级 ({elapsed:.1f}s)", state="complete", expanded=False)
                else:
                    status.update(label=f"检索成功整合了 {len(raw_results)} 条文献 ({elapsed:.1f}s)", state="complete", expanded=False)

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
        query=st.session_state.get("last_query", ""),
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
