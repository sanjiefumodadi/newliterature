import streamlit as st
import time
import concurrent.futures
from api.pubmed_api import search_pubmed
from api.crossref_api import search_crossref
from api.openalex_api import search_openalex
from utils.data_process import merge_and_deduplicate

# 设置页面标题和布局
st.set_page_config(
    page_title="智慧农业文献检索工具",
    page_icon="🌱",
    layout="wide"
)

# 页面标题
st.title("智慧农业文献检索工具")

# 搜索框和按钮
col1, col2 = st.columns([3, 1])
with col1:
    search_query = st.text_input("输入搜索关键词", placeholder="例如: genomic selection breeding")
with col2:
    search_button = st.button("开始搜索", use_container_width=True)

# 搜索按钮
if search_button:
    if search_query:
        # 显示加载状态
        with st.spinner("正在搜索文献..."):
            try:
                start_time = time.time()
                
                # 并发调用三大API，设置超时时间
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                    # 设置API调用的超时时间为3秒
                    future_pubmed = executor.submit(search_pubmed, search_query)
                    future_crossref = executor.submit(search_crossref, search_query)
                    future_openalex = executor.submit(search_openalex, search_query)
                    
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
                
                end_time = time.time()
                
                # 显示搜索结果
                st.subheader(f"搜索结果 (共 {len(merged_results)} 条，耗时 {end_time - start_time:.2f} 秒)")
                
                if merged_results:
                    # 文献卡片展示
                    for i, paper in enumerate(merged_results):
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
                                    st.info(paper['abstract'])
                                
                                with col2:
                                    st.markdown(f"**来源API:** {paper['api_source']}")
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
st.markdown("---")
st.markdown("© 2026 智慧农业文献检索工具 | 阶段2稳定版")