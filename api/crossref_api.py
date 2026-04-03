import requests

def search_crossref(query, max_results=10):
    """
    使用Crossref API按关键词搜索文献
    
    参数:
        query: 搜索关键词
        max_results: 返回的最大结果数
    
    返回:
        包含文献信息的列表，每个元素是一个字典
    """
    try:
        # Crossref API endpoint
        url = "https://api.crossref.org/works"
        
        # 构建请求参数
        params = {
            "query": query,
            "rows": max_results,
            "mailto": "your.email@example.com"  # 用于API调用标识
        }
        
        # 发送请求，设置超时时间为3秒
        response = requests.get(url, params=params, timeout=3)
        response.raise_for_status()  # 检查响应状态
        
        # 解析响应数据
        data = response.json()
        items = data.get("message", {}).get("items", [])
        
        results = []
        for item in items:
            # 提取文献信息
            title = item.get("title", [""])[0] if item.get("title") else None
            
            # 处理作者信息
            authors = []
            for author in item.get("author", []):
                given = author.get("given", "")
                family = author.get("family", "")
                if given or family:
                    authors.append(f"{given} {family}".strip())
            authors_str = ", ".join(authors) if authors else None
            
            # 处理年份信息
            year = None
            if item.get("published-print"):
                year = item.get("published-print", {}).get("date-parts", [[None]])[0][0]
            elif item.get("published-online"):
                year = item.get("published-online", {}).get("date-parts", [[None]])[0][0]
            year = str(year) if year else None
            
            source = item.get("container-title", [None])[0] if item.get("container-title") else None
            abstract = item.get("abstract", None)
            doi = item.get("DOI", None)
            
            # 构建统一格式的结果
            paper = {
                "title": title,
                "authors": authors_str,
                "year": year,
                "source": source,
                "abstract": abstract,
                "doi": doi,
                "api_source": "Crossref"
            }
            results.append(paper)
        
        return results
    
    except Exception as e:
        print(f"Crossref API调用错误: {e}")
        return []