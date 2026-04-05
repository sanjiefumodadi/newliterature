import requests
import time
import xml.etree.ElementTree as ET

def search_pubmed(query, max_results=10, max_retries=3):
    """
    使用PubMed API按关键词搜索文献
    
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
            # 使用NCBI E-utilities API直接调用，避免Biopython的XML问题
            # 1. 搜索文献获取ID
            esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            esearch_params = {
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json"
            }
            
            response = requests.get(esearch_url, params=esearch_params, timeout=5)
            response.raise_for_status()
            
            search_data = response.json()
            id_list = search_data.get("esearchresult", {}).get("idlist", [])
            
            if not id_list:
                return []
            
            # 2. 获取详细信息
            efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            efetch_params = {
                "db": "pubmed",
                "id": ",".join(id_list),
                "retmode": "xml",
                "rettype": "abstract"
            }
            
            response = requests.get(efetch_url, params=efetch_params, timeout=5)
            response.raise_for_status()
            
            # 解析XML
            root = ET.fromstring(response.content)
            
            results = []
            for article in root.findall(".//PubmedArticle"):
                try:
                    # 提取标题
                    title_elem = article.find(".//ArticleTitle")
                    title = title_elem.text if title_elem is not None else None
                    
                    # 提取作者
                    authors = []
                    for author_elem in article.findall(".//Author"):
                        last_name = author_elem.find("LastName")
                        fore_name = author_elem.find("ForeName")
                        if last_name is not None:
                            author_name = last_name.text
                            if fore_name is not None:
                                author_name = f"{fore_name.text} {last_name.text}"
                            authors.append(author_name)
                    authors_str = ", ".join(authors) if authors else None
                    
                    # 提取年份
                    year = None
                    pub_date_elem = article.find(".//PubDate/Year")
                    if pub_date_elem is not None:
                        year = pub_date_elem.text
                    else:
                        # 尝试从MedlineDate获取
                        medline_date = article.find(".//PubDate/MedlineDate")
                        if medline_date is not None and medline_date.text:
                            year = medline_date.text[:4]
                    
                    # 提取期刊名
                    source = None
                    journal_elem = article.find(".//Journal/Title")
                    if journal_elem is not None:
                        source = journal_elem.text
                    
                    # 提取摘要
                    abstract = None
                    abstract_elems = article.findall(".//AbstractText")
                    if abstract_elems:
                        abstract_parts = []
                        for abst in abstract_elems:
                            if abst.text:
                                abstract_parts.append(abst.text)
                        abstract = " ".join(abstract_parts) if abstract_parts else None
                    
                    # 提取DOI
                    doi = None
                    article_id_elems = article.findall(".//ArticleId")
                    for id_elem in article_id_elems:
                        if id_elem.get("IdType") == "doi" and id_elem.text:
                            doi = id_elem.text
                            break
                    
                    # 获取被引次数（通过DOI查询CrossRef）
                    citations = 0
                    if doi:
                        try:
                            crossref_url = f"https://api.crossref.org/works/{doi}"
                            crossref_response = requests.get(crossref_url, timeout=3)
                            if crossref_response.status_code == 200:
                                crossref_data = crossref_response.json()
                                citations = crossref_data.get("message", {}).get("is-referenced-by-count", 0)
                                if not isinstance(citations, int):
                                    citations = 0
                        except Exception as citation_error:
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
                        "api_source": "PubMed"
                    }
                    results.append(paper)
                except Exception as item_error:
                    print(f"PubMed处理单个文献时出错: {item_error}")
                    continue
            
            return results
        
        except requests.exceptions.Timeout:
            retry_count += 1
            if retry_count < max_retries:
                print(f"PubMed API超时，正在重试 ({retry_count}/{max_retries})...")
                time.sleep(1)
            else:
                print(f"PubMed API多次超时，放弃重试")
                return []
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                print(f"PubMed API错误: {e}，正在重试 ({retry_count}/{max_retries})...")
                time.sleep(1)
            else:
                print(f"PubMed API多次错误，放弃重试: {e}")
                return []
    
    return []