import streamlit as st
import time
import concurrent.futures
from api.pubmed_api import search_pubmed
from api.crossref_api import search_crossref
from api.openalex_api import search_openalex
from utils.data_process import merge_and_deduplicate, filter_by_citations

# 设置页面标题和布局
st.set_page_config(
    page_title="智慧农业文献检索工具",
    page_icon="🌱",
    layout="wide"
)

# 页面标题 - 居中显示，字体放大
st.markdown("""
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="font-size: 2.5em; color: #2c3e50;">智慧农业文献检索工具</h1>
        <p style="font-size: 1.1em; color: #7f8c8d;">🔍 专业、高效的学术文献检索平台</p>
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
        # 文献数量设置
        st.markdown("### 文献数量设置")
        max_results = st.number_input(
            "每页结果数量", 
            min_value=1, 
            max_value=50, 
            value=10, 
            step=1, 
            help="设置每页显示的文献数量（1-50条）"
        )
        
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
                
                # 并发调用三大API，设置超时时间
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                    # 确保max_results是有效的整数
                    try:
                        api_max_results = int(max_results)
                        if api_max_results < 1 or api_max_results > 50:
                            api_max_results = 10
                    except:
                        api_max_results = 10
                    
                    # 设置API调用的超时时间为3秒
                    future_pubmed = executor.submit(search_pubmed, search_query, api_max_results)
                    future_crossref = executor.submit(search_crossref, search_query, api_max_results)
                    future_openalex = executor.submit(search_openalex, search_query, api_max_results)
                    
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
                
                # 被引次数筛选
                thresholds = {
                    "OpenAlex": openalex_threshold,
                    "PubMed": pubmed_threshold,
                    "Crossref": crossref_threshold
                }
                
                filtered_results = filter_by_citations(merged_results, thresholds)
                
                # 容错机制：如果筛选后结果为空，自动降低阈值
                if not filtered_results and merged_results:
                    st.warning("当前阈值下无结果，正在自动降低阈值...")
                    
                    # 第一级降低
                    reduced_thresholds = {
                        "OpenAlex": max(10, openalex_threshold - 10),
                        "PubMed": max(25, pubmed_threshold - 25),
                        "Crossref": max(10, crossref_threshold - 5)
                    }
                    filtered_results = filter_by_citations(merged_results, reduced_thresholds)
                    
                    # 第二级降低
                    if not filtered_results:
                        reduced_thresholds = {
                            "OpenAlex": 5,
                            "PubMed": 10,
                            "Crossref": 5
                        }
                        filtered_results = filter_by_citations(merged_results, reduced_thresholds)
                
                # 使用最终结果
                final_results = filtered_results if filtered_results else merged_results
                
                end_time = time.time()
                
                # 显示搜索结果 - 居中显示
                result_container = st.container()
                with result_container:
                    # 创建居中列，与搜索区域对齐
                    col_result = st.columns([1, 3, 1])[1]
                    with col_result:
                        st.subheader(f"搜索结果 (共 {len(final_results)} 条，耗时 {end_time - start_time:.2f} 秒)")
                        st.info(f"本次搜索设置: 每页显示 {api_max_results} 条文献")
                        
                        if final_results:
                            # 文献卡片展示
                            for i, paper in enumerate(final_results):
                                try:
                                    with st.expander(f"{i+1}. {paper['title']}"):
                                        # 使用更合理的列宽比例
                                        col1, col2 = st.columns([4, 1])
                                        
                                        with col1:
                                            # 优化排版，确保字段对齐
                                            st.markdown(f"**作者:** {paper['authors']}")
                                            st.markdown(f"**发表年份:** {paper['year']}")
                                            st.markdown(f"**来源:** {paper['source']}")
                                            # 确保DOI链接正确显示
                                            if paper['doi'] and paper['doi'] != "暂无数据":
                                                st.markdown(f"**DOI:** [{paper['doi']}](https://doi.org/{paper['doi']})")
                                            else:
                                                st.markdown(f"**DOI:** {paper['doi']}")
                                            # 摘要显示优化
                                            st.markdown("**摘要:**")
                                            abstract = paper.get('abstract')
                                            if not abstract or abstract in ["None", "暂无数据"]:
                                                st.info("暂无数据")
                                            else:
                                                # 长摘要折叠显示
                                                if len(abstract) > 300:
                                                    st.expander("查看完整摘要").info(abstract)
                                                else:
                                                    st.info(abstract)
                                        
                                        with col2:
                                            st.markdown(f"**来源API:** {paper['api_source']}")
                                            st.markdown(f"**被引次数:** {paper['citations']}")
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