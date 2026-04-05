import re
import requests
from datetime import datetime

def clean_abstract(abstract):
    """
    清理摘要中的HTML/XML标签
    
    参数:
        abstract: 包含HTML/XML标签的摘要
    
    返回:
        清理后的纯文本摘要
    """
    if not abstract:
        return "暂无数据"
    
    # 移除HTML/XML标签
    clean_text = re.sub(r'<[^>]+>', '', abstract)
    # 移除多余的空白字符
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    return clean_text if clean_text else "暂无数据"

def get_paper_info_by_doi(doi):
    """
    通过DOI获取文献的完整信息
    
    参数:
        doi: 文献的DOI
    
    返回:
        包含文献信息的字典
    """
    if not doi or doi == "暂无数据":
        return {}
    
    try:
        # 使用Crossref API通过DOI获取文献信息
        url = f"https://api.crossref.org/works/{doi}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        message = data.get("message", {})
        
        # 提取信息
        info = {}
        
        # 作者
        authors = []
        for author in message.get("author", []):
            given = author.get("given", "")
            family = author.get("family", "")
            if given or family:
                authors.append(f"{given} {family}".strip())
        if authors:
            info["authors"] = ", ".join(authors)
        
        # 年份
        if message.get("published-print"):
            year = message.get("published-print", {}).get("date-parts", [[None]])[0][0]
        elif message.get("published-online"):
            year = message.get("published-online", {}).get("date-parts", [[None]])[0][0]
        else:
            year = None
        if year:
            info["year"] = str(year)
        
        # 来源
        source = message.get("container-title", [None])[0] if message.get("container-title") else None
        if source:
            info["source"] = source
        
        # 摘要
        abstract = message.get("abstract", None)
        if abstract:
            info["abstract"] = clean_abstract(abstract)
        
        return info
    except Exception as e:
        print(f"通过DOI获取文献信息失败: {e}")
        return {}

def is_recent_paper(year):
    """
    检查文献是否是近十年的
    
    参数:
        year: 文献发表年份
    
    返回:
        bool: 是否是近十年的文献
    """
    if not year or year == "暂无数据":
        return False
    
    try:
        current_year = datetime.now().year
        paper_year = int(year)
        return current_year - paper_year <= 10
    except:
        return False

def normalize_doi(doi):
    """
    标准化DOI格式
    
    参数:
        doi: 原始DOI字符串
    
    返回:
        标准化后的DOI
    """
    if not doi:
        return ""
    
    # 移除DOI前缀
    doi = doi.strip()
    if doi.startswith("https://doi.org/"):
        doi = doi[16:]
    elif doi.startswith("doi:"):
        doi = doi[4:]
    
    return doi

def merge_and_deduplicate(papers):
    """
    合并来自多个API的文献结果，去除重复项，并统一数据格式
    
    参数:
        papers: 包含文献信息的列表，每个元素是一个字典
    
    返回:
        去重后的文献列表
    """
    # 用于存储去重后的文献
    unique_papers = []
    # 用于跟踪已处理的DOI，以去除重复项
    seen_dois = set()
    # 用于跟踪已处理的标题，作为无DOI文献的唯一标识
    seen_titles = set()
    
    for paper in papers:
        # 获取并标准化DOI
        doi = normalize_doi(paper.get("doi", ""))
        
        # 获取标题
        title = paper.get("title", "").strip()
        
        # 严格按DOI去重
        if doi:
            if doi not in seen_dois:
                seen_dois.add(doi)
            else:
                continue
        else:
            # 没有DOI的文献，使用标题作为唯一标识
            if title:
                # 标准化标题（去除多余空格，转换为小写）
                normalized_title = " ".join(title.lower().split())
                if normalized_title not in seen_titles:
                    seen_titles.add(normalized_title)
                else:
                    continue
            else:
                # 既没有DOI也没有标题的文献，跳过
                continue
        
        # 清理摘要
        abstract = paper.get("abstract")
        clean_abs = clean_abstract(abstract)
        
        # 构建基础信息
        paper_info = {
            "title": paper.get("title") or "暂无数据",
            "authors": paper.get("authors") or "暂无数据",
            "year": paper.get("year") or "暂无数据",
            "source": paper.get("source") or "暂无数据",
            "abstract": clean_abs,
            "doi": doi or "暂无数据",
            "citations": paper.get("citations", 0),
            "api_source": paper.get("api_source") or "暂无数据"
        }
        
        # 如果有DOI且缺少关键信息，尝试获取更完整的信息
        if doi and doi != "暂无数据":
            # 只有在缺少信息时才进行DOI查询，减少API调用
            need_update = False
            if paper_info["authors"] == "暂无数据":
                need_update = True
            if paper_info["year"] == "暂无数据":
                need_update = True
            if paper_info["source"] == "暂无数据":
                need_update = True
            if paper_info["abstract"] == "暂无数据":
                need_update = True
            
            if need_update:
                doi_info = get_paper_info_by_doi(doi)
                # 更新信息
                if doi_info.get("authors"):
                    paper_info["authors"] = doi_info["authors"]
                if doi_info.get("year"):
                    paper_info["year"] = doi_info["year"]
                if doi_info.get("source"):
                    paper_info["source"] = doi_info["source"]
                if doi_info.get("abstract"):
                    paper_info["abstract"] = doi_info["abstract"]
        
        # 检查是否是近十年的文献
        if is_recent_paper(paper_info["year"]):
            # 添加到结果列表
            unique_papers.append(paper_info)
    
    return unique_papers

def filter_by_citations(papers, thresholds):
    """
    根据被引次数筛选文献
    
    参数:
        papers: 文献列表
        thresholds: 各API的被引次数阈值字典
    
    返回:
        筛选后的文献列表
    """
    filtered_papers = []
    
    for paper in papers:
        api_source = paper.get("api_source", "")
        citations = paper.get("citations", 0)
        threshold = thresholds.get(api_source, 0)
        
        if citations >= threshold:
            filtered_papers.append(paper)
    
    return filtered_papers