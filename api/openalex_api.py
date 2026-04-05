import requests
import time

def search_openalex(query, max_results=10, max_retries=3):
    """
    使用OpenAlex API按关键词搜索文献
    
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
            # OpenAlex API endpoint
            url = "https://api.openalex.org/works"
            
            # 构建请求参数
            params = {
                "search": query,
                "per-page": max_results
            }
            
            # 发送请求，设置超时时间
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()  # 检查响应状态
            
            # 解析响应数据
            data = response.json()
            if not isinstance(data, dict):
                print(f"OpenAlex API响应格式错误: {data}")
                return []
            items = data.get("results", [])
            
            results = []
            for item in items:
                if not item or not isinstance(item, dict):
                    continue
                    
                try:
                    # 提取文献信息
                    title = item.get("title")
                    
                    # 处理作者信息
                    authors = []
                    authorships = item.get("authorships", [])
                    if authorships:
                        for author_entry in authorships:
                            if author_entry and isinstance(author_entry, dict):
                                author_obj = author_entry.get("author")
                                if author_obj and isinstance(author_obj, dict):
                                    author_name = author_obj.get("display_name", "")
                                    if author_name:
                                        authors.append(author_name)
                    authors_str = ", ".join(authors) if authors else None
                    
                    # 处理年份
                    year = None
                    pub_year = item.get("publication_year")
                    if pub_year is not None:
                        try:
                            year = str(pub_year)
                        except:
                            year = None
                    
                    # 安全获取来源信息
                    source = None
                    primary_location = item.get("primary_location")
                    if primary_location and isinstance(primary_location, dict):
                        source_info = primary_location.get("source")
                        if source_info and isinstance(source_info, dict):
                            source = source_info.get("display_name")
                    
                    abstract = item.get("abstract")
                    
                    # 处理DOI
                    doi = None
                    doi_raw = item.get("doi")
                    if doi_raw:
                        doi = doi_raw.replace("https://doi.org/", "")
                    
                    # 获取被引次数
                    citations = item.get("cited_by_count", 0)
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
                        "api_source": "OpenAlex"
                    }
                    results.append(paper)
                except Exception as item_error:
                    print(f"OpenAlex处理单个文献时出错: {item_error}")
                    continue
            
            return results
        
        except requests.exceptions.Timeout:
            retry_count += 1
            if retry_count < max_retries:
                print(f"OpenAlex API超时，正在重试 ({retry_count}/{max_retries})...")
                time.sleep(1)
            else:
                print(f"OpenAlex API多次超时，放弃重试")
                return []
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                print(f"OpenAlex API错误: {e}，正在重试 ({retry_count}/{max_retries})...")
                time.sleep(1)
            else:
                print(f"OpenAlex API多次错误，放弃重试: {e}")
                return []
    
    return []