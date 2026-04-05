import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.pubmed_api import search_pubmed
from api.crossref_api import search_crossref
from api.openalex_api import search_openalex
from utils.data_process import merge_and_deduplicate, filter_by_citations

def test_api_calls():
    """测试API调用功能"""
    print("=== 测试API调用 ===")
    query = "smart agriculture"
    
    # 测试PubMed API
    print("\n1. 测试PubMed API:")
    try:
        pubmed_results = search_pubmed(query, max_results=5)
        print(f"   结果数量: {len(pubmed_results)}")
        if pubmed_results:
            print(f"   第一条文献: {pubmed_results[0]['title'][:50]}...")
            print(f"   被引次数: {pubmed_results[0].get('citations', 'N/A')}")
    except Exception as e:
        print(f"   错误: {e}")
    
    # 测试OpenAlex API
    print("\n2. 测试OpenAlex API:")
    try:
        openalex_results = search_openalex(query, max_results=5)
        print(f"   结果数量: {len(openalex_results)}")
        if openalex_results:
            print(f"   第一条文献: {openalex_results[0]['title'][:50]}...")
            print(f"   被引次数: {openalex_results[0].get('citations', 'N/A')}")
    except Exception as e:
        print(f"   错误: {e}")
    
    # 测试CrossRef API
    print("\n3. 测试CrossRef API:")
    try:
        crossref_results = search_crossref(query, max_results=5)
        print(f"   结果数量: {len(crossref_results)}")
        if crossref_results:
            print(f"   第一条文献: {crossref_results[0]['title'][:50]}...")
            print(f"   被引次数: {crossref_results[0].get('citations', 'N/A')}")
    except Exception as e:
        print(f"   错误: {e}")

def test_data_processing():
    """测试数据处理功能"""
    print("\n=== 测试数据处理 ===")
    query = "smart agriculture"
    
    try:
        # 获取API结果
        pubmed_results = search_pubmed(query, max_results=3)
        openalex_results = search_openalex(query, max_results=3)
        crossref_results = search_crossref(query, max_results=3)
        
        # 合并结果
        merged = merge_and_deduplicate(pubmed_results + openalex_results + crossref_results)
        print(f"合并后结果数量: {len(merged)}")
        
        # 测试筛选功能
        thresholds = {
            "OpenAlex": 20,
            "PubMed": 50,
            "Crossref": 15
        }
        filtered = filter_by_citations(merged, thresholds)
        print(f"筛选后结果数量: {len(filtered)}")
        
        if filtered:
            print("\n筛选后文献:")
            for i, paper in enumerate(filtered[:3]):
                print(f"{i+1}. {paper['title'][:50]}...")
                print(f"   来源: {paper['api_source']}")
                print(f"   被引次数: {paper['citations']}")
                print(f"   年份: {paper['year']}")
    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    test_api_calls()
    test_data_processing()
    print("\n=== 测试完成 ===")
