import streamlit as st
import time
import concurrent.futures
from api.pubmed_api import search_pubmed
from api.crossref_api import search_crossref
from api.openalex_api import search_openalex
from utils.data_process import (
    merge_and_deduplicate,
    filter_by_citations,
    rerank_with_minimum_results,
    is_single_keyword_query,
    DEFAULT_MIN_RESULTS,
    build_expanded_queries,
    filter_by_title_abstract_relevance
)
from utils.translation import (
    should_show_translate_button,
    paper_translate_id,
    translate_paper_to_chinese
)


def render_no_result_guidance(query, single_keyword_mode, thresholds):
    """在无结果时给出可执行的下一步建议。"""
    st.warning("当前条件下未找到可展示文献")
    st.markdown("#### 建议下一步")
    st.markdown("1. 换一个更通用的关键词，或缩短为1到2个核心词")
    st.markdown("2. 适当降低被引次数阈值后再搜索")
    st.markdown("3. 尝试关键词同义词，例如 `genomics -> genetic`、`irrigation -> water`")

    if single_keyword_mode:
        st.caption("当前为单关键词模式，系统已自动执行扩展召回；若仍无结果，建议先放宽阈值。")

    st.caption(
        f"当前检索词：{query} ｜ 当前阈值：OpenAlex≥{thresholds['OpenAlex']} / "
        f"PubMed≥{thresholds['PubMed']} / CrossRef≥{thresholds['Crossref']}"
    )


if "paper_translation_toggle" not in st.session_state:
    st.session_state["paper_translation_toggle"] = {}
if "paper_translation_cache" not in st.session_state:
    st.session_state["paper_translation_cache"] = {}
if "paper_abstract_expand" not in st.session_state:
    st.session_state["paper_abstract_expand"] = {}

# 设置页面标题和布局
st.set_page_config(
    page_title="智慧农业文献检索工具",
    page_icon=None,
    layout="wide"
)

DEFAULT_THRESHOLDS = {
    "OpenAlex": 20,
    "PubMed": 50,
    "Crossref": 15,
}

# 页面标题 - 居中显示，字体放大
st.markdown("""
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="font-size: 2.3em; color: #1f2d3d; font-weight: 700; letter-spacing: 0.02em;">智慧农业文献检索工具</h1>
        <p style="font-size: 1.02em; color: #6b7280; margin-top: 0.35rem;">专业、高效的学术文献检索平台</p>
    </div>
""", unsafe_allow_html=True)

# 搜索区域 - 整体居中
search_container = st.container()
with search_container:
    # 创建居中列
    col_center = st.columns([1, 3, 1])[1]  # 中间列宽度为3，两侧各为1
    
    with col_center:
        # 关键词输入框 - 宽度70%，增加内边距
        search_query = st.text_input(
            "输入搜索关键词", 
            placeholder="例如: genomic selection breeding",
            help="输入与智慧农业相关的关键词进行文献检索",
            label_visibility="hidden"
        )
        
        # 搜索按钮 - 放在输入框正下方，宽度50%，居中对齐
        col_button = st.columns([1, 2, 1])[1]  # 中间列宽度为2，两侧各为1
        with col_button:
            search_button = st.button(
                "开始搜索", 
                use_container_width=True
            )

# 高级筛选区域
with st.sidebar:
    st.markdown("## 筛选面板")
    st.caption("类似 OpenAlex 的辅助控制区")

    if "openalex_threshold" not in st.session_state:
        st.session_state["openalex_threshold"] = DEFAULT_THRESHOLDS["OpenAlex"]
    if "pubmed_threshold" not in st.session_state:
        st.session_state["pubmed_threshold"] = DEFAULT_THRESHOLDS["PubMed"]
    if "crossref_threshold" not in st.session_state:
        st.session_state["crossref_threshold"] = DEFAULT_THRESHOLDS["Crossref"]

    action_col1, action_col2 = st.columns(2)
    with action_col1:
        if st.button("重置筛选", use_container_width=True):
            st.session_state["openalex_threshold"] = DEFAULT_THRESHOLDS["OpenAlex"]
            st.session_state["pubmed_threshold"] = DEFAULT_THRESHOLDS["PubMed"]
            st.session_state["crossref_threshold"] = DEFAULT_THRESHOLDS["Crossref"]
            st.rerun()
    with action_col2:
        if st.button("回到第1页", use_container_width=True):
            for key in list(st.session_state.keys()):
                if str(key).startswith("page_"):
                    st.session_state[key] = 1
            st.rerun()

    with st.expander("被引次数阈值", expanded=True):
        openalex_threshold = st.number_input(
            "OpenAlex (≥)",
            min_value=0,
            value=st.session_state["openalex_threshold"],
            step=5,
            key="openalex_threshold",
            help="综合学术库被引次数阈值"
        )
        pubmed_threshold = st.number_input(
            "PubMed (≥)",
            min_value=0,
            value=st.session_state["pubmed_threshold"],
            step=10,
            key="pubmed_threshold",
            help="生物医学核心库被引次数阈值"
        )
        crossref_threshold = st.number_input(
            "CrossRef (≥)",
            min_value=0,
            value=st.session_state["crossref_threshold"],
            step=5,
            key="crossref_threshold",
            help="官方引文索引被引次数阈值"
        )

    st.markdown("---")
    sort_mode = st.selectbox(
        "结果排序",
        options=["综合相关度", "被引次数（高到低）", "发表年份（新到旧）"],
        index=0,
        help="默认使用综合相关度；可切换为更偏引用或更偏最新年份"
    )
    page_size = st.selectbox(
        "每页显示",
        options=[10, 20, 30],
        index=0,
        help="控制每页显示文献条数"
    )

    st.markdown("---")
    st.caption("后续会在这里继续加入年份、排序、学科等筛选项")
    st.caption("提示：若网络波动，系统会自动降级到可用数据源并给出提示。")

# 自定义CSS - 增加按钮hover效果和输入框样式
st.markdown("""
    <style>
        /* 页面整体节奏：更接近数据库产品，减少上方空白 */
        .block-container {
            padding-top: 1.8rem;
            padding-bottom: 1.8rem;
            max-width: 1240px;
        }

        /* 主区域卡片感 */
        [data-testid="stAppViewContainer"] {
            background: linear-gradient(180deg, #fbfcfe 0%, #ffffff 100%);
        }

        /* 搜索按钮样式 */
        button[data-testid="base-button"] {
            margin-top: 10px;
            padding: 10px 0;
            border-radius: 8px;
            background-color: #3498db;
            color: white;
            font-size: 16px;
            font-weight: bold;
            transition: all 0.3s ease;
        }
        
        button[data-testid="base-button"]:hover {
            background-color: #2980b9;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        }
        
        /* 输入框样式 */
        input[data-testid="stTextInput"] {
            padding: 12px;
            border-radius: 8px;
            border: 2px solid #e0e0e0;
            font-size: 16px;
        }
        
        /* 结果区域样式 */
        .stExpander {
            margin-top: 15px;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
        }

        /* 结果列表密度优化 */
        h3 {
            margin-top: 0.45rem;
            margin-bottom: 0.35rem;
            line-height: 1.35;
        }

        [data-testid="stMarkdownContainer"] p {
            line-height: 1.55;
        }

        /* 侧边栏更像控制面板 */
        section[data-testid="stSidebar"] {
            border-right: 1px solid #e5e7eb;
            background: #f8fafc;
        }
    </style>
""", unsafe_allow_html=True)

# 搜索按钮
if search_button:
    if search_query:
        # 显示加载状态
        with st.spinner("正在检索并整合文献..."):
            try:
                start_time = time.time()
                single_keyword_mode = is_single_keyword_query(search_query)
                api_fetch_size = 30 if single_keyword_mode else 10
                target_count = DEFAULT_MIN_RESULTS if single_keyword_mode else 1
                api_health = {"PubMed": "ok", "Crossref": "ok", "OpenAlex": "ok"}
                
                # 并发调用三大API，设置超时时间
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                    # 设置API调用的超时时间为3秒
                    future_pubmed = executor.submit(search_pubmed, search_query, api_fetch_size)
                    future_crossref = executor.submit(search_crossref, search_query, api_fetch_size)
                    future_openalex = executor.submit(search_openalex, search_query, api_fetch_size)
                    
                    # 获取结果，设置总超时时间为4秒
                    try:
                        pubmed_results = future_pubmed.result(timeout=3)
                    except concurrent.futures.TimeoutError:
                        pubmed_results = []
                        api_health["PubMed"] = "timeout"
                    except Exception as e:
                        print(f"PubMed API调用异常: {e}")
                        pubmed_results = []
                        api_health["PubMed"] = "error"
                    
                    try:
                        crossref_results = future_crossref.result(timeout=3)
                    except concurrent.futures.TimeoutError:
                        crossref_results = []
                        api_health["Crossref"] = "timeout"
                    except Exception as e:
                        print(f"Crossref API调用异常: {e}")
                        crossref_results = []
                        api_health["Crossref"] = "error"
                    
                    try:
                        openalex_results = future_openalex.result(timeout=3)
                    except concurrent.futures.TimeoutError:
                        openalex_results = []
                        api_health["OpenAlex"] = "timeout"
                    except Exception as e:
                        print(f"OpenAlex API调用异常: {e}")
                        openalex_results = []
                        api_health["OpenAlex"] = "error"

                degraded_sources = [name for name, status in api_health.items() if status != "ok"]
                if degraded_sources:
                    degraded_msg = "、".join(degraded_sources)
                    st.info(f"网络波动提示：{degraded_msg} 当前响应不稳定，系统已自动使用其余可用结果。")
                
                # 合并结果
                try:
                    merged_results = merge_and_deduplicate(pubmed_results + crossref_results + openalex_results)
                except Exception as e:
                    print(f"数据处理异常: {e}")
                    merged_results = []

                # 严格过滤：仅保留标题或摘要中包含关键词/同义词的文献
                strict_pool = filter_by_title_abstract_relevance(merged_results, search_query)

                # 单关键词召回增强：分阶段使用同义词扩展查询，尽量保障严格过滤后仍有10条
                if single_keyword_mode and len(strict_pool) < DEFAULT_MIN_RESULTS:
                    expansion_rounds = [
                        {"max_queries": 5, "fetch_size": 12},
                        {"max_queries": 8, "fetch_size": 18}
                    ]

                    for round_cfg in expansion_rounds:
                        if len(strict_pool) >= DEFAULT_MIN_RESULTS:
                            break

                        expansion_queries = build_expanded_queries(
                            search_query,
                            max_queries=round_cfg["max_queries"]
                        )[1:]
                        extra_results = []

                        if not expansion_queries:
                            continue

                        with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(expansion_queries) * 3)) as executor:
                            expansion_futures = []
                            for expanded_query in expansion_queries:
                                expansion_futures.append(executor.submit(search_pubmed, expanded_query, round_cfg["fetch_size"]))
                                expansion_futures.append(executor.submit(search_crossref, expanded_query, round_cfg["fetch_size"]))
                                expansion_futures.append(executor.submit(search_openalex, expanded_query, round_cfg["fetch_size"]))

                            for future in expansion_futures:
                                try:
                                    extra_results.extend(future.result(timeout=3) or [])
                                except Exception:
                                    continue

                        if extra_results:
                            merged_results = merge_and_deduplicate(merged_results + extra_results)
                            strict_pool = filter_by_title_abstract_relevance(merged_results, search_query)

                if strict_pool and len(strict_pool) < len(merged_results):
                    st.caption(f"严格过滤生效：保留 {len(strict_pool)} / {len(merged_results)} 篇（仅标题/摘要命中关键词或同义词）")
                
                # 被引次数筛选
                thresholds = {
                    "OpenAlex": openalex_threshold,
                    "PubMed": pubmed_threshold,
                    "Crossref": crossref_threshold
                }
                staged_thresholds = [thresholds]

                # 保留原有“自动降阈值”交互，并在单关键词模式下增加温和放宽层
                staged_thresholds.append({
                    "OpenAlex": max(10, openalex_threshold - 10),
                    "PubMed": max(25, pubmed_threshold - 25),
                    "Crossref": max(10, crossref_threshold - 5)
                })
                staged_thresholds.append({
                    "OpenAlex": 5,
                    "PubMed": 10,
                    "Crossref": 5
                })
                if single_keyword_mode:
                    staged_thresholds.append({
                        "OpenAlex": max(3, openalex_threshold - 18),
                        "PubMed": max(5, pubmed_threshold - 40),
                        "Crossref": max(3, crossref_threshold - 15)
                    })

                filtered_results = []
                used_stage = 0
                if strict_pool:
                    for stage_index, stage_threshold in enumerate(staged_thresholds):
                        staged_results = filter_by_citations(strict_pool, stage_threshold)
                        if len(staged_results) > len(filtered_results):
                            filtered_results = staged_results
                            used_stage = stage_index
                        if len(filtered_results) >= target_count:
                            break

                if used_stage > 0:
                    st.warning("当前阈值结果较少，系统已自动放宽被引次数阈值以提升召回。")
                
                # 使用最终结果
                candidate_results = filtered_results if filtered_results else strict_pool
                final_results = rerank_with_minimum_results(candidate_results, search_query, min_results=target_count)

                if sort_mode == "被引次数（高到低）":
                    final_results = sorted(
                        final_results,
                        key=lambda item: (
                            item.get("citations", 0),
                            item.get("sort_score", 0),
                            int(item.get("year", 0)) if str(item.get("year", "")).isdigit() else 0,
                        ),
                        reverse=True,
                    )
                elif sort_mode == "发表年份（新到旧）":
                    final_results = sorted(
                        final_results,
                        key=lambda item: (
                            int(item.get("year", 0)) if str(item.get("year", "")).isdigit() else 0,
                            item.get("citations", 0),
                            item.get("sort_score", 0),
                        ),
                        reverse=True
                    )

                total_results = len(final_results)
                total_pages = max(1, (total_results + page_size - 1) // page_size)
                page_state_key = f"page_{search_query.strip().lower()}"
                current_page = st.session_state.get(page_state_key, 1)
                if current_page > total_pages:
                    current_page = total_pages
                if current_page < 1:
                    current_page = 1

                start_idx = (current_page - 1) * page_size
                end_idx = start_idx + page_size
                paged_results = final_results[start_idx:end_idx]

                # 侧边栏统计小面板（OpenAlex风格分析感）
                source_counter = {}
                year_counter = {}
                for item in final_results:
                    source_name = str(item.get("api_source", "未知来源") or "未知来源")
                    source_counter[source_name] = source_counter.get(source_name, 0) + 1

                    year_text = str(item.get("year", "未知年份") or "未知年份")
                    year_counter[year_text] = year_counter.get(year_text, 0) + 1

                top_sources = sorted(source_counter.items(), key=lambda x: x[1], reverse=True)[:3]
                top_years = sorted(
                    year_counter.items(),
                    key=lambda x: (int(x[0]) if x[0].isdigit() else 0),
                    reverse=True
                )[:5]

                with st.sidebar:
                    st.markdown("---")
                    st.markdown("### 结果统计")
                    st.metric("检索结果数", total_results)
                    st.metric("当前页", f"{current_page}/{total_pages}")

                    if top_sources:
                        st.caption("来源分布（Top 3）")
                        for src_name, src_count in top_sources:
                            st.markdown(f"- {src_name}: {src_count}")

                    if top_years:
                        st.caption("年份分布（最近）")
                        for year_name, year_count in top_years:
                            st.markdown(f"- {year_name}: {year_count}")
                
                end_time = time.time()
                
                # 显示搜索结果 - 居中显示
                result_container = st.container()
                with result_container:
                    # 创建居中列，与搜索区域对齐
                    col_result = st.columns([1, 3, 1])[1]
                    with col_result:
                        st.subheader(f"搜索结果 (共 {total_results} 条，耗时 {end_time - start_time:.2f} 秒)")
                        st.caption("排序依据：关键词相关度(BM25+多字段匹配) + 被引次数 + 发表年份")

                        st.markdown(
                            f"<div style='display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 6px 0;'>"
                            f"<span style='background:#eef2ff;color:#243b6b;padding:4px 10px;border-radius:999px;font-size:0.85rem;'>结果数 {total_results}</span>"
                            f"<span style='background:#fff7ed;color:#9a3412;padding:4px 10px;border-radius:999px;font-size:0.85rem;'>第 {current_page}/{total_pages} 页</span>"
                            f"<span style='background:#eff6ff;color:#1f3d63;padding:4px 10px;border-radius:999px;font-size:0.85rem;'>排序 {sort_mode}</span>"
                            f"<span style='background:#ecfdf3;color:#14643a;padding:4px 10px;border-radius:999px;font-size:0.85rem;'>OpenAlex≥{openalex_threshold} / PubMed≥{pubmed_threshold} / CrossRef≥{crossref_threshold}</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                        strict_status = "启用" if strict_pool else "未触发"
                        st.markdown(
                            f"<div style='display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 12px 0;'>"
                            f"<span style='background:#f1f5f9;color:#334155;padding:3px 10px;border-radius:999px;font-size:0.82rem;'>关键词 {search_query}</span>"
                            f"<span style='background:#f1f5f9;color:#334155;padding:3px 10px;border-radius:999px;font-size:0.82rem;'>严格过滤 {strict_status}</span>"
                            f"<span style='background:#f1f5f9;color:#334155;padding:3px 10px;border-radius:999px;font-size:0.82rem;'>每页 {page_size}</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                        nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
                        with nav_col1:
                            if st.button("上一页", disabled=current_page <= 1, key=f"prev_{page_state_key}"):
                                st.session_state[page_state_key] = max(1, current_page - 1)
                                st.rerun()
                        with nav_col2:
                            st.markdown(
                                f"<div style='text-align:center;color:#64748b;font-size:0.92rem;padding-top:0.4rem;'>"
                                f"当前显示 {start_idx + 1 if total_results else 0}-{min(end_idx, total_results)} / {total_results}"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                        with nav_col3:
                            if st.button("下一页", disabled=current_page >= total_pages, key=f"next_{page_state_key}"):
                                st.session_state[page_state_key] = min(total_pages, current_page + 1)
                                st.rerun()

                        jump_col1, jump_col2, jump_col3 = st.columns([1.4, 1.2, 1.4])
                        with jump_col2:
                            jump_page = st.number_input(
                                "页码跳转",
                                min_value=1,
                                max_value=total_pages,
                                value=current_page,
                                step=1,
                                key=f"jump_input_{page_state_key}",
                            )
                            if st.button("跳转", key=f"jump_btn_{page_state_key}"):
                                st.session_state[page_state_key] = int(jump_page)
                                st.rerun()

                        if sort_mode == "综合相关度":
                            st.caption("排序说明：先按综合相关度；同分时优先被引次数和较新年份")
                        elif sort_mode == "被引次数（高到低）":
                            st.caption("排序说明：先按被引次数；同分时优先综合相关度和较新年份")
                        else:
                            st.caption("排序说明：先按发表年份；同分时优先被引次数和综合相关度")
                        
                        if paged_results:
                            # OpenAlex风格紧凑列表展示
                            for offset, paper in enumerate(paged_results):
                                try:
                                    i = start_idx + offset
                                    translation_id = paper_translate_id(paper, i)
                                    can_translate = should_show_translate_button(paper)
                                    translated_mode = st.session_state["paper_translation_toggle"].get(translation_id, False)
                                    abstract_expanded = st.session_state["paper_abstract_expand"].get(translation_id, False)

                                    display_paper = paper
                                    if can_translate and translated_mode:
                                        if translation_id not in st.session_state["paper_translation_cache"]:
                                            st.session_state["paper_translation_cache"][translation_id] = translate_paper_to_chinese(paper)
                                        display_paper = st.session_state["paper_translation_cache"][translation_id]

                                    st.markdown("---")

                                    title_text = str(display_paper.get("title", "暂无数据"))
                                    doi_text = str(display_paper.get("doi", "暂无数据"))
                                    if doi_text and doi_text != "暂无数据":
                                        st.markdown(f"### {i+1}. [{title_text}](https://doi.org/{doi_text})")
                                    else:
                                        st.markdown(f"### {i+1}. {title_text}")

                                    left_col, right_col = st.columns([5, 2])

                                    with left_col:
                                        st.markdown(
                                            f"<div style='font-size:0.98rem;color:#334155;line-height:1.65;'>"
                                            f"<b>{display_paper.get('year', '暂无数据')}</b> · {display_paper.get('authors', '暂无数据')} · <i>{display_paper.get('source', '暂无数据')}</i>"
                                            f"</div>",
                                            unsafe_allow_html=True
                                        )

                                        abstract_text = str(display_paper.get("abstract", "暂无数据") or "暂无数据")
                                        short_abstract = abstract_text
                                        if not abstract_expanded and abstract_text != "暂无数据" and len(abstract_text) > 280:
                                            short_abstract = abstract_text[:280].rstrip() + " ..."

                                        st.caption("摘要")
                                        st.markdown(
                                            f"<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px 14px;color:#1f2937;font-size:0.94rem;line-height:1.55;'>"
                                            f"{short_abstract}"
                                            f"</div>",
                                            unsafe_allow_html=True
                                        )

                                        if abstract_text != "暂无数据" and len(abstract_text) > 280:
                                            toggle_text = "收起摘要" if abstract_expanded else "展开摘要"
                                            if st.button(toggle_text, key=f"abstract_{translation_id}"):
                                                st.session_state["paper_abstract_expand"][translation_id] = not abstract_expanded
                                                st.rerun()

                                    with right_col:
                                        st.markdown(
                                            f"<div style='display:flex;flex-direction:column;gap:8px;'>"
                                            f"<span style='background:#eff6ff;color:#1d4f91;border-radius:999px;padding:4px 10px;font-size:0.84rem;width:fit-content;'>来源 {display_paper.get('api_source', '暂无数据')}</span>"
                                            f"<span style='background:#f5f3ff;color:#5b2d8c;border-radius:999px;padding:4px 10px;font-size:0.84rem;width:fit-content;'>被引 {display_paper.get('citations', 0)}</span>"
                                            f"</div>",
                                            unsafe_allow_html=True
                                        )

                                        if can_translate:
                                            button_text = "查看原文" if translated_mode else "翻译为中文"
                                            if st.button(button_text, key=f"translate_{translation_id}"):
                                                st.session_state["paper_translation_toggle"][translation_id] = not translated_mode
                                                st.rerun()
                                            if translated_mode:
                                                st.caption("当前显示中文译文")
                                except Exception as e:
                                    print(f"显示文献卡片异常: {e}")
                                    st.error(f"显示第 {i+1} 条文献时出现错误")
                        else:
                            render_no_result_guidance(search_query, single_keyword_mode, thresholds)
            except Exception as e:
                print(f"搜索过程异常: {e}")
                st.error("搜索过程中出现错误，请稍后重试")
                st.markdown("#### 可尝试的处理方式")
                st.markdown("1. 先点击搜索按钮重试一次")
                st.markdown("2. 更换关键词，避免过长或特殊符号")
                st.markdown("3. 临时调低被引阈值再搜索")
                with st.expander("错误详情（调试用）", expanded=False):
                    st.code(str(e))
    else:
        st.warning("请输入搜索关键词")

# 页脚信息
st.markdown("""
    <div style="text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #e0e0e0;">
        <p style="color: #7f8c8d;">© 2026 智慧农业文献检索工具 | 阶段2稳定版</p>
    </div>
""", unsafe_allow_html=True)