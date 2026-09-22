# Lit2Zotero

按论文大纲组织文献检索、记录agent的纳入与阅读判断、建立本地Zotero分类，并向Word动态引文工作流交接真实条目身份。

**文献是否纳入由宿主agent判断。** 搜索排名、下载成功和自动生成的摘要都不能替代证据判断。该skill提供可检查的流程与工具，不保证文献能够支持任意写作主张。

## 能做什么

- **必须同时调用宿主agent原生联网检索与学术API检索**：原生搜索及打开原文用于发现、追溯和核查；Europe PMC、Crossref用于结构化元数据，OpenAlex辅助定位OA全文。
- 分开记录纳入理由、具体命题、摘要阅读和全文阅读状态。
- 在本地Zotero中建立项目分类、复用已有条目、更新管理笔记和导入PDF。
- 重复运行避免重复导入；无法确认的身份与未完成阅读保持阻断。
- 导出引文交接表，并将Word技能的定位结果绑定到agent已确认的Zotero key，避免同DOI重复条目导致引用指向另一条记录。

本仓库不包含个人文献库、文献PDF、API密钥、测试DOCX或配置后的XPI。

## 按引用用途决定是否需要全文

**纳入文献不等于必须下载PDF。** agent依据实际要写的句子逐条判断，而不是按论文主题、期刊或文献类型统一决定。

以算法开发论文为例：一般背景、生物学现象或既有方法的概括性介绍，如果原始摘要足以支持该表述，可以只读摘要，归入“不需要PDF”。当引用涉及核心公式、算法步骤、实现参数、比较方法细节，或摘要未交代的实验时点、分子角色、样本设计和具体数值时，才要求核对相应全文，归入“需要PDF”。生物学因果细节和实验阳性纳入标准也可能必须读全文。

最终阅读深度由agent自主判断，并在每条证据的reason中写明“支持什么论点、摘要为何足够／需要核对什么细节”。同一文献有多种用途时分别判断；其中任一用途确需全文，整篇文献仍归入“需要PDF”。有PDF不代表必须精读，无PDF也不能成为降低阅读要求的理由。

已有项目若需重新分类，应先复核引用用途、记录变更理由，再更新合同并同步；本规则更新不会自动批量移动旧文献，也不会删除已下载PDF。详见[skill阅读策略](SKILL.md#claim-based-reading-policy)。

## 环境与安装

实际小批验收环境为Windows、Python 3.12、Zotero 9.0.6及Microsoft Word Desktop。其他系统与Zotero版本未完成完整链验收。

```powershell
git clone https://github.com/mingruiy270-debug/lit2zotero.git
cd lit2zotero
python -m venv .venv
New-Item -ItemType Directory -Force tmp | Out-Null
$env:TEMP = (Resolve-Path tmp).Path
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $env:TEMP 'pip'
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe scripts/build_bridge.py
```

在Zotero“工具→插件→从文件安装”中选择生成的 `dist/lit2zotero-local.xpi`。开启Zotero允许本机其他应用通信的选项。此XPI包含随机本机凭证和目录范围，**只能本机使用，不能上传或转发**。不要删除已有private配置后继续使用旧XPI；两端凭证需要一致。

桥接版本为0.1.2，CLI为0.1.1。原生桥只提供限定分类和目录的操作，不提供任意JavaScript、数据库SQL、合并或删除接口。更新地址使用保留的.invalid域名以满足Zotero清单要求，插件关闭自己的后台更新；新版本通过本地重新构建和安装，不提供远程自动更新服务。

## 开始一个项目

让宿主agent读取本仓库[SKILL.md](SKILL.md)，根据实际大纲填写claims。复制[示例结构](examples/claims.example.json)后改成真实命题。

```powershell
& .\.venv\Scripts\python.exe scripts/lit2zotero.py doctor
& .\.venv\Scripts\python.exe scripts/lit2zotero.py init --project projects/my_paper --claims examples/claims.example.json --collection 'Lit2Zotero · My paper' --backend native
& .\.venv\Scripts\python.exe scripts/lit2zotero.py discover --project projects/my_paper --provider epmc --query 'gene prioritization benchmark' --pages 1
```

agent读取候选材料后，按[工作流说明](references/workflow.md)生成决策文件，再执行decide、必要的全文获取、sync和handoff。sync默认预览，明确加 `--apply` 才写入Zotero。完整项目与参考表在本仓库目录内保存；项目文件默认不被Git跟踪。

无需独立LLM API key：科学判断由运行skill的agent完成。远程服务凭证通过环境变量提供，程序不会自动读取.env。保留服务原有使用限制；网络错误不标作检索完成。

## Word交接

Word自动化依赖另行安装并连接的 `word_mcp_live` 和兼容的 `zotero-word-citations-skill`；本仓库不捆绑第三方Word实现。参见[Word交接合同](references/word-handoff.md)。

必须在副本上先运行Word技能的题名匹配，然后使用本仓库 `scripts/prepare_word_mapping.py` 生成配套的mapping-bound文件。所有插入输入都使用新绑定文件。最后以实际ZoteroRefresh、引用URI、书目及非引文内容比较验收，不能以“存在字段代码”代替成功。

## 测试与已知范围

```powershell
& .\.venv\Scripts\python.exe scripts/build_bridge.py
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
node tests/test_bridge.cjs
```

当前通用回归为36项Python测试和17项Node模拟检查。实际本地试点另外完成8篇书目、1份真实PDF附件、两次同步，以及4篇文献／4个Word引用字段／5次引用／4条书目的Refresh和格式对照。个人库结果和测试文档不随仓库发布，使用者仍需在自己的环境中实测。

测试机存在Word首次启动VBA 424的环境警告，责任加载项尚未定位，用户选择暂缓处理。结束该错误后功能测试通过；本项目不声称已经解决该错误，也不保证所有Word加载项组合均可无人值守运行。

首版支持journalArticle；未内置OCR、组库、云端写入或通用全文语义审查。两项需全文支持的试点命题保持未ready，没有因软件通过而升级为证据充分。非空超链接保真和大规模稿件尚未作为本轮验收覆盖项。

## 许可

本仓库代码采用[MIT](LICENSE)。运行依赖、Zotero、Word及其加载项遵循各自许可；MIT不覆盖下载的文献或第三方数据库内容。特别是PyMuPDF有自己的AGPL／商业许可条件，分发集成产品前需另行判断。

原生联网由运行skill的agent实际调用（例如Codex的web.run），并通过record_web_search.py记录；Python脚本本身不会获得或模拟宿主联网工具权限。工具不可用时必须记录原因，不得把API查询冒称为完成原生联网检索。

## 两个PDF子分类

每个项目分类下自动建立“需要PDF”和“不需要PDF”。分类依据是agent声明的阅读需求，而不是现在有没有PDF：任一命题要求全文即归入“需要PDF”，已补齐或已精读也不移出；所有用途只需摘要才归入“不需要PDF”。只在本项目的两个管理子分类之间调整成员关系，不删除文献、不改变其他分类。

每次sync另输出reading_queue.tsv，列出题名、DOI、需求类别、附件记录、阅读状态和下一步操作。用户可以把PDF手动拖到Zotero对应父条目下；下次sync会看到附件元数据，但不会把它当作已核实原文或已精读。agent仍需取得实际文件、调用attach校验身份并完成原文阅读，之后才能生成可靠精读记录。

旧插件0.1.1需重新构建并安装本机XPI。程序会在不支持reading-collections时明确停止，而不是继续同步后冒称分类完成。metadata-only existing后端不支持此合同。
