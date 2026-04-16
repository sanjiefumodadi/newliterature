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


if "paper_translation_toggle" not in st.session_state:
    st.session_state["paper_translation_toggle"] = {}
if "paper_translation_cache" not in st.session_state:
    st.session_state["paper_translation_cache"] = {}

# 设置页面标题和布局
st.set_page_config(
    page_title="智慧农业文献检索工具",
    page_icon=None,
    layout="wide"
)

# 页面标题 - 居中显示，字体放大
st.markdown("""
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="font-size: 2.5em; color: #2c3e50;">智慧农业文献检索工具</h1>
        <p style="font-size: 1.1em; color: #7f8c8d;">专业、高效的学术文献检索平台</p>
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
with col_center:
    with st.expander("高级筛选", expanded=False):
        st.markdown("### 被引次数阈值设置")
        col1, col2, col3 = st.columns(3)
        with col1:
            openalex_threshold = st.number_input(
                "OpenAlex (≥)", 
                min_value=0, 
                value=20, 
                step=5, 
                help="综合学术库被引次数阈值"
            )
        with col2:
            pubmed_threshold = st.number_input(
                "PubMed (≥)", 
                min_value=0, 
                value=50, 
                step=10, 
                help="生物医学核心库被引次数阈值"
            )
        with col3:
            crossref_threshold = st.number_input(
                "CrossRef (≥)", 
                min_value=0, 
                value=15, 
                step=5, 
                help="官方引文索引被引次数阈值"
            )

# 自定义CSS - 增加按钮hover效果和输入框样式
st.markdown("""
    <style>
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
    </style>
""", unsafe_allow_html=True)

# 搜索按钮
if search_button:
    if search_query:
        # 显示加载状态
        with st.spinner("正在搜索文献..."):
            try:
                start_time = time.time()
                single_keyword_mode = is_single_keyword_query(search_query)
                api_fetch_size = 30 if single_keyword_mode else 10
                target_count = DEFAULT_MIN_RESULTS if single_keyword_mode else 1
                
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
                    except Exception as e:
                        print(f"PubMed API调用异常: {e}")
                        pubmed_results = []
                    
                    try:
                        crossref_results = future_crossref.result(timeout=3)
                    except concurrent.futures.TimeoutError:
                        crossref_results = []
                    except Exception as e:
                        print(f"Crossref API调用异常: {e}")
                        crossref_results = []
                    
                    try:
                        openalex_results = future_openalex.result(timeout=3)
                    except concurrent.futures.TimeoutError:
                        openalex_results = []
                    except Exception as e:
                        print(f"OpenAlex API调用异常: {e}")
                        openalex_results = []
                
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
                
                end_time = time.time()
                
                # 显示搜索结果 - 居中显示
                result_container = st.container()
                with result_container:
                    # 创建居中列，与搜索区域对齐
                    col_result = st.columns([1, 3, 1])[1]
                    with col_result:
                        st.subheader(f"搜索结果 (共 {len(final_results)} 条，耗时 {end_time - start_time:.2f} 秒)")
                        st.caption("排序依据：关键词相关度(BM25+多字段匹配) + 被引次数 + 发表年份")
                        
                        if final_results:
                            # 文献卡片展示
                            for i, paper in enumerate(final_results):
                                try:
                                    translation_id = paper_translate_id(paper, i)
                                    can_translate = should_show_translate_button(paper)
                                    translated_mode = st.session_state["paper_translation_toggle"].get(translation_id, False)

                                    display_paper = paper
                                    if can_translate and translated_mode:
                                        if translation_id not in st.session_state["paper_translation_cache"]:
                                            st.session_state["paper_translation_cache"][translation_id] = translate_paper_to_chinese(paper)
                                        display_paper = st.session_state["paper_translation_cache"][translation_id]

                                    with st.expander(f"{i+1}. {display_paper['title']}"):
                                        # 使用更合理的列宽比例
                                        col1, col2 = st.columns([4, 1])
                                        
                                        with col1:
                                            # 优化排版，确保字段对齐
                                            st.markdown(f"**作者:** {display_paper['authors']}")
                                            st.markdown(f"**发表年份:** {display_paper['year']}")
                                            st.markdown(f"**来源:** {display_paper['source']}")
                                            # 确保DOI链接正确显示
                                            if display_paper['doi'] and display_paper['doi'] != "暂无数据":
                                                st.markdown(f"**DOI:** [{display_paper['doi']}](https://doi.org/{display_paper['doi']})")
                                            else:
                                                st.markdown(f"**DOI:** {display_paper['doi']}")
                                            # 摘要显示优化
                                            st.markdown("**摘要:**")
                                            st.info(display_paper['abstract'])
                                        
                                        with col2:
                                            st.markdown(f"**来源API:** {display_paper['api_source']}")
                                            st.markdown(f"**被引次数:** {display_paper['citations']}")
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
                            st.info("未找到符合条件的文献，请尝试其他关键词")
            except Exception as e:
                print(f"搜索过程异常: {e}")
                st.error("搜索过程中出现错误，请稍后重试")
    else:
        st.warning("请输入搜索关键词")

# 页脚信息
st.markdown("""
    <div style="text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #e0e0e0;">
        <p style="color: #7f8c8d;">© 2026 智慧农业文献检索工具 | 阶段2稳定版</p>
    </div>
""", unsafe_allow_html=True)