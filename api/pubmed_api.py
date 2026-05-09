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
        socket.setdefaulttimeout(8)
        
        # 使用Entrez.esearch搜索文献
        handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results)
        record = Entrez.read(handle)
        handle.close()
        
        # 获取PubMed ID列表
        id_list = record.get("IdList", [])
        
        if not id_list:
            return []
        
        # 使用XML模式获取详细信息，避免文本模式解析兼容问题
        handle = Entrez.efetch(db="pubmed", id=",".join(id_list), retmode="xml")
        records = Entrez.read(handle)
        
        results = []
        pubmed_articles = records.get("PubmedArticle", []) if isinstance(records, dict) else []
        for article in pubmed_articles:
            medline = article.get("MedlineCitation", {})
            article_info = medline.get("Article", {})
            pmid = str(medline.get("PMID", "")).strip()

            # 提取文献信息
            title = article_info.get("ArticleTitle", None)

            authors = []
            author_list = article_info.get("AuthorList", [])
            for author in author_list:
                if not isinstance(author, dict):
                    continue
                fore_name = author.get("ForeName", "")
                last_name = author.get("LastName", "")
                full_name = f"{fore_name} {last_name}".strip()
                if full_name:
                    authors.append(full_name)
            authors = ", ".join(authors) if authors else None

            year = None
            journal = article_info.get("Journal", {})
            journal_issue = journal.get("JournalIssue", {}) if isinstance(journal, dict) else {}
            pub_date = journal_issue.get("PubDate", {}) if isinstance(journal_issue, dict) else {}
            if isinstance(pub_date, dict):
                year_value = pub_date.get("Year")
                if year_value:
                    year = str(year_value)

            source = journal.get("ISOAbbreviation") if isinstance(journal, dict) else None

            abstract = None
            abstract_obj = article_info.get("Abstract", {})
            if isinstance(abstract_obj, dict):
                abstract_text = abstract_obj.get("AbstractText", [])
                if isinstance(abstract_text, list):
                    abstract = " ".join(str(part) for part in abstract_text if part)
                elif abstract_text:
                    abstract = str(abstract_text)

            doi = None
            pubmed_data = article.get("PubmedData", {})
            article_id_list = pubmed_data.get("ArticleIdList", []) if isinstance(pubmed_data, dict) else []
            for article_id in article_id_list:
                if hasattr(article_id, "attributes") and article_id.attributes.get("IdType") == "doi":
                    doi = str(article_id)
                    break

            link_url = None
            if pmid:
                link_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            
            # 获取被引次数（通过DOI查询CrossRef）
            citations = 0
            if doi:
                try:
                    crossref_url = f"https://api.crossref.org/works/{doi}"
                    crossref_response = requests.get(crossref_url, timeout=(2.0, 5.0))
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
                "url": link_url,
                "citations": citations,
                "api_source": "PubMed"
            }
            results.append(paper)
        
        handle.close()
        return results
    
    except Exception as e:
        print(f"PubMed API调用错误: {e}")
        return []