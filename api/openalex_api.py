import requests

def search_openalex(query, max_results=10):
    """
    使用OpenAlex API按关键词搜索文献
    
    参数:
        query: 搜索关键词
        max_results: 返回的最大结果数
    
    返回:
        包含文献信息的列表，每个元素是一个字典
    """
    try:
        # OpenAlex API endpoint
        url = "https://api.openalex.org/works"
        
        # 构建请求参数
        params = {
            "search": query,
            "per-page": max_results
        }
        
        # 发送请求，设置超时时间为3秒
        response = requests.get(url, params=params, timeout=3)
        response.raise_for_status()  # 检查响应状态
        
        # 解析响应数据
        data = response.json()
        if not isinstance(data, dict):
            print(f"OpenAlex API响应格式错误: {data}")
            return []
        items = data.get("results", [])
        
        results = []
        for item in items:
            # 提取文献信息
            title = item.get("title", None)
            
            # 处理作者信息
            authors = []
            for author in item.get("authorships", []):
                if author:
                    author_name = author.get("author", {}).get("display_name", "")
                    if author_name:
                        authors.append(author_name)
            authors_str = ", ".join(authors) if authors else None
            
            year = str(item.get("publication_year")) if item.get("publication_year") else None
            # 安全获取来源信息
            primary_location = item.get("primary_location", {})
            source_info = primary_location.get("source", {})
            source = source_info.get("display_name", None)
            abstract = item.get("abstract", None)
            doi = item.get("doi", "").replace("https://doi.org/", "") if item.get("doi") else None
            
            # 获取被引次数
            citations = item.get("cited_by_count", 0)
            
            # 构建统一格式的结果
            paper = {
                "title": title,
                "authors": authors_str,
                "year": year,
                "source": source,
                "abstract": abstract,
                "doi": doi,
                "citations": citations,
                "api_source": "OpenAlex"
            }
            results.append(paper)
        
        return results
    
    except Exception as e:
        print(f"OpenAlex API调用错误: {e}")
        return []