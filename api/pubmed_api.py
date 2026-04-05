import requests
from Bio import Entrez

# 设置Entrez邮箱（用于API调用标识）
Entrez.email = "your.email@example.com"

def search_pubmed(query, max_results=10):
    """
    使用PubMed API按关键词搜索文献
    
    参数:
        query: 搜索关键词
        max_results: 返回的最大结果数
    
    返回:
        包含文献信息的列表，每个元素是一个字典
    """
    try:
        # 设置Entrez的超时时间
        import socket
        socket.setdefaulttimeout(3)
        
        # 使用Entrez.esearch搜索文献
        handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results)
        record = Entrez.read(handle)
        handle.close()
        
        # 获取PubMed ID列表
        id_list = record.get("IdList", [])
        
        if not id_list:
            return []
        
        # 使用Entrez.efetch获取详细信息
        handle = Entrez.efetch(db="pubmed", id=",".join(id_list), rettype="medline", retmode="text")
        records = Entrez.parse(handle)
        
        results = []
        for record in records:
            # 提取文献信息
            title = record.get("TI", None)
            authors = ", ".join(record.get("AU", [])) if record.get("AU") else None
            year = record.get("DP", "").split()[0] if record.get("DP") else None
            source = record.get("TA", None)
            abstract = record.get("AB", None)
            lid = record.get("LID", "")
            doi = lid.replace("[doi]", "").strip() if "[doi]" in lid else None
            
            # 获取被引次数（通过DOI查询CrossRef）
            citations = 0
            if doi:
                try:
                    crossref_url = f"https://api.crossref.org/works/{doi}"
                    crossref_response = requests.get(crossref_url, timeout=2)
                    if crossref_response.status_code == 200:
                        crossref_data = crossref_response.json()
                        citations = crossref_data.get("message", {}).get("is-referenced-by-count", 0)
                except:
                    pass
            
            # 构建统一格式的结果
            paper = {
                "title": title,
                "authors": authors,
                "year": year,
                "source": source,
                "abstract": abstract,
                "doi": doi,
                "citations": citations,
                "api_source": "PubMed"
            }
            results.append(paper)
        
        handle.close()
        return results
    
    except Exception as e:
        print(f"PubMed API调用错误: {e}")
        return []