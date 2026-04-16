import re
import math
import requests
from datetime import datetime
from collections import Counter

# 结果排序与相关性控制参数
DEFAULT_MIN_RESULTS = 10
SORT_WEIGHTS = {
    "citations": 0.30,
    "year": 0.20,
    "relevance": 0.50
}
FIELD_WEIGHTS = {
    "title": 3.0,
    "abstract": 2.2,
    "source": 1.2,
    "authors": 0.7
}
BM25_WEIGHTS = {
    "title": 1.25,
    "abstract": 1.00,
    "source": 0.80,
    "authors": 0.55
}
BM25_K1 = 1.5
BM25_B = 0.75
LOW_RELEVANCE_TOKEN_CAP = 0.18
MIN_RELEVANCE_STAGES = [0.90, 0.82, 0.74, 0.66, 0.58]

# 智慧农业领域常见同义词与近义表达
DOMAIN_SYNONYMS = {
    "agriculture": ["farming", "agricultural", "crop", "field"],
    "smart": ["intelligent", "digital", "precision", "automated"],
    "precision": ["site-specific", "variable-rate", "digital"],
    "genomics": ["genomic", "genome", "genetic", "genetics"],
    "breeding": ["selection", "cultivar", "phenotyping"],
    "phenotyping": ["trait", "traits", "phenotype", "high-throughput"],
    "crop": ["plant", "crops", "yield"],
    "soil": ["edaphic", "nutrient", "fertility"],
    "irrigation": ["water", "watering", "moisture"],
    "remote": ["satellite", "uav", "drone", "sensing"],
    "sensing": ["sensor", "detection", "monitoring"],
    "yield": ["productivity", "output"],
    "machine": ["ml", "learning", "algorithm"],
    "learning": ["ml", "model", "prediction"],
    "climate": ["weather", "temperature", "environment"],
    "stress": ["drought", "heat", "salinity"],
    "disease": ["pathogen", "infection", "resistance"],
    "wheat": ["triticum"],
    "maize": ["corn", "zea"],
    "rice": ["oryza"]
}

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

def is_recent_paper(year, recent_years=10):
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
        if recent_years is None:
            return True
        current_year = datetime.now().year
        paper_year = int(year)
        return current_year - paper_year <= recent_years
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

def merge_and_deduplicate(papers, recent_years=10, enrich_by_doi=True):
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
            "url": paper.get("url") or "",
            "citations": paper.get("citations", 0),
            "api_source": paper.get("api_source") or "暂无数据"
        }
        
        # 如果有DOI且缺少关键信息，尝试获取更完整的信息
        if enrich_by_doi and doi and doi != "暂无数据":
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
        if is_recent_paper(paper_info["year"], recent_years=recent_years):
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


def normalize_text(text):
    """
    统一文本格式，便于做关键词匹配和BM25评分
    """
    if not text or text == "暂无数据":
        return ""

    lowered = str(text).lower()
    lowered = re.sub(r"[\n\r\t]", " ", lowered)
    lowered = re.sub(r"[^a-z0-9\-\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def tokenize_text(text):
    """
    将文本切分为词元，长度过短的无意义词会被移除
    """
    normalized = normalize_text(text)
    if not normalized:
        return []
    return [token for token in normalized.split(" ") if len(token) > 1]


def expand_query_terms(query):
    """
    对用户查询词做轻量同义词扩展，提升召回
    """
    base_terms = tokenize_text(query)
    expanded = set(base_terms)

    for term in list(base_terms):
        for synonym in DOMAIN_SYNONYMS.get(term, []):
            expanded.add(synonym)
        for headword, synonyms in DOMAIN_SYNONYMS.items():
            if term in synonyms:
                expanded.add(headword)
                expanded.update(synonyms)

    return base_terms, sorted(expanded)


def build_expanded_queries(query, max_queries=4):
    """
    为单关键词检索生成扩展查询词，用于召回补充
    """
    base_terms, _ = expand_query_terms(query)
    if not base_terms:
        return [query]

    normalized_query = normalize_text(query)
    queries = [normalized_query]
    candidates = []

    if len(base_terms) == 1:
        key = base_terms[0]
        candidates.extend(DOMAIN_SYNONYMS.get(key, []))
        for headword, synonyms in DOMAIN_SYNONYMS.items():
            if key in synonyms:
                candidates.append(headword)
    else:
        # 多关键词时仅保留原查询，避免过度发散
        return [normalized_query]

    seen = {normalized_query}
    for term in candidates:
        normalized_term = normalize_text(term)
        if not normalized_term or normalized_term in seen:
            continue
        seen.add(normalized_term)
        queries.append(normalized_term)
        if len(queries) >= max_queries:
            break

    return queries


def filter_by_title_abstract_relevance(papers, query):
    """
    严格过滤：仅保留标题或摘要命中关键词/同义词的文献
    """
    if not papers:
        return []

    base_terms, expanded_terms = expand_query_terms(query)
    match_terms = set(expanded_terms)
    normalized_query = normalize_text(query)
    strict_filtered = []

    for paper in papers:
        title_text = normalize_text(paper.get("title", ""))
        abstract_text = normalize_text(paper.get("abstract", ""))

        title_tokens = set(tokenize_text(title_text))
        abstract_tokens = set(tokenize_text(abstract_text))
        title_or_abstract_tokens = title_tokens.union(abstract_tokens)

        token_hit = bool(match_terms.intersection(title_or_abstract_tokens))
        phrase_hit = bool(normalized_query and (normalized_query in title_text or normalized_query in abstract_text))
        base_hit = bool(set(base_terms).intersection(title_or_abstract_tokens))

        if token_hit or phrase_hit or base_hit:
            strict_filtered.append(paper)

    return strict_filtered


def extract_field_texts(paper):
    """
    提取用于排序和相关性判断的核心字段
    """
    return {
        "title": paper.get("title", ""),
        "abstract": paper.get("abstract", ""),
        "source": paper.get("source", ""),
        "authors": paper.get("authors", "")
    }


def build_bm25_corpus(papers):
    """
    为每个字段构建BM25所需语料统计
    """
    corpus = {field: [] for field in FIELD_WEIGHTS}

    for paper in papers:
        field_texts = extract_field_texts(paper)
        for field in corpus:
            corpus[field].append(tokenize_text(field_texts.get(field, "")))

    stats = {}
    for field, documents in corpus.items():
        doc_count = len(documents)
        if doc_count == 0:
            stats[field] = {
                "documents": [],
                "avgdl": 0.0,
                "doc_freq": {},
                "doc_count": 0
            }
            continue

        lengths = [len(doc) for doc in documents]
        avgdl = sum(lengths) / doc_count if doc_count else 0.0
        doc_freq = {}
        for doc in documents:
            for token in set(doc):
                doc_freq[token] = doc_freq.get(token, 0) + 1

        stats[field] = {
            "documents": documents,
            "avgdl": avgdl,
            "doc_freq": doc_freq,
            "doc_count": doc_count
        }

    return stats


def bm25_score(query_terms, doc_tokens, doc_freq, doc_count, avgdl):
    """
    计算单文档BM25分数
    """
    if not query_terms or not doc_tokens or doc_count == 0 or avgdl == 0:
        return 0.0

    tf_counter = Counter(doc_tokens)
    score = 0.0

    for term in query_terms:
        if term not in tf_counter:
            continue
        term_df = doc_freq.get(term, 0)
        idf = math.log(1 + (doc_count - term_df + 0.5) / (term_df + 0.5))
        tf = tf_counter[term]
        denom = tf + BM25_K1 * (1 - BM25_B + BM25_B * (len(doc_tokens) / avgdl))
        score += idf * ((tf * (BM25_K1 + 1)) / (denom + 1e-12))

    return float(score)


def calc_field_match_score(field_texts, base_terms, expanded_terms):
    """
    多字段加权匹配分数。标题和摘要权重更高，扩展词命中权重略低。
    """
    if not expanded_terms:
        return 0.0

    score = 0.0
    phrase = " ".join(base_terms)

    for field, weight in FIELD_WEIGHTS.items():
        text = normalize_text(field_texts.get(field, ""))
        if not text:
            continue

        tokens = text.split(" ")
        token_set = set(tokens)

        base_hits = sum(1 for term in base_terms if term in token_set)
        expanded_hits = sum(1 for term in expanded_terms if term in token_set)

        coverage = base_hits / max(len(base_terms), 1)
        soft_coverage = expanded_hits / max(len(expanded_terms), 1)

        field_score = (coverage * 0.75 + soft_coverage * 0.25) * weight

        if phrase and len(base_terms) > 1 and phrase in text:
            field_score += 0.25 * weight

        score += field_score

    return float(score)


def calc_bm25_score(papers, index, expanded_terms):
    """
    计算目标文献在各字段的BM25加权总分
    """
    score = 0.0

    for field, bm25_weight in BM25_WEIGHTS.items():
        field_stats = papers.get(field, {})
        docs = field_stats.get("documents", [])
        if index >= len(docs):
            continue

        doc_tokens = docs[index]
        part_score = bm25_score(
            query_terms=expanded_terms,
            doc_tokens=doc_tokens,
            doc_freq=field_stats.get("doc_freq", {}),
            doc_count=field_stats.get("doc_count", 0),
            avgdl=field_stats.get("avgdl", 0.0)
        )
        score += part_score * bm25_weight

    return float(score)


def normalize_year(year):
    """
    将年份归一化到[0, 1]，最近年份分数更高
    """
    try:
        year_value = int(year)
        current = datetime.now().year
        floor = current - 12
        clipped = max(min(year_value, current), floor)
        return (clipped - floor) / max(current - floor, 1)
    except Exception:
        return 0.0


def normalize_citations(citations):
    """
    使用对数缩放被引次数，避免极大值支配排序
    """
    try:
        value = max(int(citations), 0)
    except Exception:
        return 0.0
    return math.log1p(value) / math.log1p(2000)


def score_and_rank_papers(papers, query):
    """
    计算并写回每篇文献的相关性与综合排序分
    """
    if not papers:
        return []

    base_terms, expanded_terms = expand_query_terms(query)
    bm25_corpus = build_bm25_corpus(papers)

    # 用于归一化字段匹配与BM25分数
    raw_scores = []
    for index, paper in enumerate(papers):
        field_texts = extract_field_texts(paper)
        field_match = calc_field_match_score(field_texts, base_terms, expanded_terms)
        bm25_val = calc_bm25_score(bm25_corpus, index, expanded_terms)
        raw_scores.append((field_match, bm25_val))

    max_field = max((item[0] for item in raw_scores), default=1.0) or 1.0
    max_bm25 = max((item[1] for item in raw_scores), default=1.0) or 1.0

    ranked = []
    for index, paper in enumerate(papers):
        field_match_raw, bm25_raw = raw_scores[index]
        field_match_score = field_match_raw / max_field
        bm25_score_norm = bm25_raw / max_bm25

        relevance_score = field_match_score * 0.55 + bm25_score_norm * 0.45

        # 仅标题字面命中、摘要/来源上下文缺失时做明显降权
        title_tokens = set(tokenize_text(paper.get("title", "")))
        abstract_tokens = set(tokenize_text(paper.get("abstract", "")))
        source_tokens = set(tokenize_text(paper.get("source", "")))
        base_set = set(base_terms)

        title_overlap = len(base_set.intersection(title_tokens)) / max(len(base_terms), 1)
        abstract_overlap = len(base_set.intersection(abstract_tokens)) / max(len(base_terms), 1)
        source_overlap = len(base_set.intersection(source_tokens)) / max(len(base_terms), 1)

        if title_overlap > 0 and abstract_overlap == 0 and source_overlap == 0:
            relevance_score *= 0.78
        elif title_overlap > 0 and relevance_score < 0.55 and title_overlap <= LOW_RELEVANCE_TOKEN_CAP:
            relevance_score *= 0.86

        citation_score = normalize_citations(paper.get("citations", 0))
        year_score = normalize_year(paper.get("year"))

        sort_score = (
            SORT_WEIGHTS["citations"] * citation_score
            + SORT_WEIGHTS["year"] * year_score
            + SORT_WEIGHTS["relevance"] * relevance_score
        )

        enriched = dict(paper)
        enriched["field_match_score"] = round(field_match_score, 4)
        enriched["bm25_score"] = round(bm25_score_norm, 4)
        enriched["relevance_score"] = round(relevance_score, 4)
        enriched["sort_score"] = round(sort_score, 4)
        ranked.append(enriched)

    ranked.sort(key=lambda item: item.get("sort_score", 0), reverse=True)
    return ranked


def rerank_with_minimum_results(papers, query, min_results=DEFAULT_MIN_RESULTS):
    """
    在保证相关性的前提下做分阶段放宽，尽量满足最低返回数量
    """
    ranked = score_and_rank_papers(papers, query)
    if not ranked:
        return []

    for min_relevance in MIN_RELEVANCE_STAGES:
        filtered = [paper for paper in ranked if paper.get("relevance_score", 0.0) >= min_relevance]
        if len(filtered) >= min_results:
            return filtered

    # 如果仍不足，返回最高分结果，保证尽量满足展示数量
    return ranked[:max(min_results, len(ranked))]


def is_single_keyword_query(query):
    """
    判断是否为单关键词检索
    """
    return len(tokenize_text(query)) == 1