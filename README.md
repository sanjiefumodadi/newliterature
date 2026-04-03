# 智慧农业文献检索工具

面向智慧农业专业师生的轻量开源文献检索工具，解决不会搜、找不到权威文献、外文检索困难的痛点。

## 项目结构

```
literature_search/
├── main.py                 # Streamlit主入口，前端页面
├── requirements.txt         # 依赖清单，适配Streamlit Cloud
├── .gitignore               # Git忽略文件（venv/__pycache__等）
├── README.md                # 项目说明+Windows运行+部署教程
├── api/
│   ├── __init__.py
│   ├── pubmed_api.py        # PubMed API封装
│   ├── crossref_api.py      # Crossref API封装
│   └── openalex_api.py      # OpenAlex API封装
└── utils/
    ├── __init__.py
    └── data_process.py      # 数据合并、去重、清洗工具
```

## 功能特点

- **关键词检索**：支持输入关键词搜索文献
- **多API集成**：同时调用PubMed、Crossref、OpenAlex三大权威学术API
- **结果合并**：自动合并三个API的结果，去重并统一格式
- **卡片式展示**：清晰展示文献标题、作者、年份、DOI、摘要等信息
- **稳定运行**：完整的异常处理，确保搜索过程稳定不崩溃

## 开发阶段

- **阶段1**（当前）：实现关键词检索，调用三大API获取文献，前端简单展示文献列表，稳定运行、无额外功能
- **阶段2**：检索流程无Bug，数据规整、去重、排版清晰，页面简洁加载快，达到可用版本
- **阶段3**：添加文献筛选（年份/学科/引用数）、智能排序、导出Excel/CSV、关键词联想推荐
- **阶段4**：添加页面右下角AI小方块智能助手，生成专业检索关键词、给出搜索建议
- **阶段5**：文献引用关系可视化图谱、语义检索、个性化推荐、公网长期部署

## Windows本地运行

### 前置条件
- Python 3.7+
- 已创建虚拟环境

### 安装依赖

```bash
# 激活虚拟环境
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 启动应用

```bash
# 在项目根目录运行
streamlit run main.py
```

应用将在浏览器中打开，默认地址为 `http://localhost:8501`

## GitHub上传步骤（Windows版）

1. **初始化Git仓库**
   ```bash
   cd literature_search
   git init
   ```

2. **添加文件**
   ```bash
   git add .
   ```

3. **提交更改**
   ```bash
   git commit -m "初始化项目 - 阶段1基础版"
   ```

4. **创建GitHub仓库**
   - 登录GitHub，创建一个新的空仓库

5. **关联远程仓库**
   ```bash
   git remote add origin https://github.com/your-username/literature-search.git
   ```

6. **推送到GitHub**
   ```bash
   git push -u origin main
   ```

## Streamlit Cloud部署步骤

1. **登录Streamlit Cloud**
   - 访问 https://share.streamlit.io/
   - 使用GitHub账号登录

2. **创建新应用**
   - 点击 "New app"
   - 选择你的GitHub仓库
   - 选择分支（默认main）
   - 输入主文件路径：`main.py`
   - 点击 "Deploy"

3. **等待部署完成**
   - Streamlit Cloud会自动安装依赖并部署应用
   - 部署完成后，你将获得一个公网访问链接

## 后续阶段迭代的标准话术模板

> 我要做面向智慧农业专业的轻量开源文献检索Web工具，严格按分阶段蓝图开发，现在做阶段X。
> 
> 核心目标：[阶段X的核心目标]
> 
> 核心铁律（必须100%遵守）
> 1. 所有路径必须用相对路径，绝对禁止任何本地绝对路径
> 2. 项目结构模块化、清晰有序，符合GitHub管理规范
> 3. 只做阶段X功能，不添加任何额外功能，代码极简、稳定、无Bug
> 4. 自动在当前工作目录生成所有文件，无需手动粘贴
> 5. 自动在当前虚拟环境安装所有依赖，最后只给我一句运行命令
> 
> 请按照标准项目结构生成代码，并在最后告诉我测试结果＋启动命令＋后续迭代的标准话术