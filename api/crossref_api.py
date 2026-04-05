import requests
import time

def search_crossref(query, max_results=10, max_retries=3):
    """
    使用Crossref API按关键词搜索文献
    
    参数:
        query: 搜索关键词
        max_results: 返回的最大结果数
        max_retries: 最大重试次数
    
    返回:
        包含文献信息的列表，每个元素是一个字典
    """
    retry_count = 0
    while retry_count < max_retries:
        try:
            # Crossref API endpoint
            url = "https://api.crossref.org/works"
            
            # 构建请求参数
            params = {
                "query": query,
                "rows": max_results,
                "mailto": "your.email@example.com"  # 用于API调用标识
            }
            
            # 发送请求，设置超时时间
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()  # 检查响应状态
            
            # 解析响应数据
            data = response.json()
            if not isinstance(data, dict):
                print(f"Crossref API响应格式错误: {data}")
                return []
            
            message = data.get("message", {})
            if not isinstance(message, dict):
                print(f"Crossref API message格式错误: {message}")
                return []
            
            items = message.get("items", [])
            
            results = []
            for item in items:
                if not item or not isinstance(item, dict):
                    continue
                    
                try:
                    # 提取文献信息
                    title = None
                    titles = item.get("title", [])
                    if titles and isinstance(titles, list) and len(titles) > 0:
                        title = titles[0]
                    
                    # 处理作者信息
                    authors = []
                    authors_list = item.get("author", [])
                    if authors_list and isinstance(authors_list, list):
                        for author in authors_list:
                            if author and isinstance(author, dict):
                                given = author.get("given", "")
                                family = author.get("family", "")
                                if given or family:
                                    authors.append(f"{given} {family}".strip())
                    authors_str = ", ".join(authors) if authors else None
                    
                    # 处理年份信息
                    year = None
                    # 尝试多种日期字段
                    date_sources = [
                        "published-print",
                        "published-online",
                        "published"
                    ]
                    for source in date_sources:
                        date_data = item.get(source)
                        if date_data and isinstance(date_data, dict):
                            date_parts = date_data.get("date-parts")
                            if date_parts and isinstance(date_parts, list) and len(date_parts) > 0:
                                part = date_parts[0]
                                if part and isinstance(part, list) and len(part) > 0:
                                    year_candidate = part[0]
                                    if year_candidate is not None:
                                        try:
                                            year = str(year_candidate)
                                            break
                                        except:
                                            pass
                    
                    # 处理来源
                    source = None
                    container_titles = item.get("container-title", [])
                    if container_titles and isinstance(container_titles, list) and len(container_titles) > 0:
                        source = container_titles[0]
                    
                    abstract = item.get("abstract")
                    doi = item.get("DOI")
                    
                    # 获取被引次数
                    citations = item.get("is-referenced-by-count", 0)
                    if not isinstance(citations, int):
                        citations = 0
                    
                    # 构建统一格式的结果
                    paper = {
                        "title": title,
                        "authors": authors_str,
                        "year": year,
                        "source": source,
                        "abstract": abstract,
                        "doi": doi,
                        "citations": citations,
                        "api_source": "Crossref"
                    }
                    results.append(paper)
                except Exception as item_error:
                    print(f"Crossref处理单个文献时出错: {item_error}")
                    continue
            
            return results
        
        except requests.exceptions.Timeout:
            retry_count += 1
            if retry_count < max_retries:
                print(f"Crossref API超时，正在重试 ({retry_count}/{max_retries})...")
                time.sleep(1)
            else:
                print(f"Crossref API多次超时，放弃重试")
                return []
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                print(f"Crossref API错误: {e}，正在重试 ({retry_count}/{max_retries})...")
                time.sleep(1)
            else:
                print(f"Crossref API多次错误，放弃重试: {e}")
                return []
    
    return []