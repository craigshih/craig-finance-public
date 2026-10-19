"""
供應鏈地圖：海外龍頭 ↔ 台股公司。

原則：每一條「供應商／客戶／合作」關係都必須有真實新聞或公司公告當出處（SOURCES），
而且出處原文要點名雙方；找不到出處的關係一律不放，避免 AI 憑印象補上錯的供應鏈。
2026-10-07 逐條開原文核對（WebFetch），原本約 110 條關係只留下有出處的部分。

「同業」不是供應關係，是同一條產品線的景氣連動（例如 DRAM 報價），依產業分類，不需新聞出處。

要新增關係：先在 SOURCES 加一筆出處（原文必須同時提到台廠和龍頭），再在 LINKS 加一行引用它。

關係類型（台股公司對龍頭來說是什麼）：
  供應商：台廠賣產品或代工給龍頭（龍頭需求好 → 台廠訂單可能跟著好）
  客戶：台廠向龍頭買設備（台廠擴產 → 龍頭受惠，方向相反）
  合作：合資、代理、共同開發
  同業：同產品線、景氣連動
"""

# 代號: (名稱, 市場, yfinance 代號, 產業, 新聞裡常見的稱呼)
LEADERS = {
    "NVDA": ("NVIDIA", "美股", "NVDA", "AI 晶片", ["輝達", "NVIDIA", "Nvidia"]),
    "AAPL": ("Apple", "美股", "AAPL", "消費電子", ["蘋果", "Apple", "iPhone"]),
    "MSFT": ("Microsoft", "美股", "MSFT", "雲端", ["微軟", "Microsoft"]),
    "GOOGL": ("Alphabet", "美股", "GOOGL", "雲端／AI", ["Google", "谷歌", "Alphabet"]),
    "AMZN": ("Amazon", "美股", "AMZN", "雲端／電商", ["亞馬遜", "Amazon", "AWS"]),
    "META": ("Meta", "美股", "META", "社群／AI", ["Meta"]),
    "AVGO": ("Broadcom", "美股", "AVGO", "網通晶片／ASIC", ["博通", "Broadcom"]),
    "AMD": ("AMD", "美股", "AMD", "CPU／GPU", ["超微", "AMD"]),
    "TSLA": ("Tesla", "美股", "TSLA", "電動車", ["特斯拉", "Tesla"]),
    "MU": ("Micron", "美股", "MU", "記憶體", ["美光", "Micron"]),
    "6758": ("Sony", "日股", "6758.T", "影像感測器／消費電子", ["索尼", "Sony", "SONY"]),
    "8035": ("東京威力科創", "日股", "8035.T", "半導體設備", ["東京威力", "Tokyo Electron"]),
    "6857": ("愛德萬測試", "日股", "6857.T", "半導體測試設備", ["愛德萬", "Advantest"]),
    "6981": ("村田製作所", "日股", "6981.T", "被動元件", ["村田", "Murata"]),
    "7203": ("豐田汽車", "日股", "7203.T", "汽車", ["豐田", "TOYOTA", "Toyota"]),
    "005930": ("三星電子", "韓股", "005930.KS", "記憶體／晶圓代工", ["三星", "Samsung"]),
    "000660": ("SK 海力士", "韓股", "000660.KS", "記憶體／HBM", ["海力士", "SK hynix"]),
    "034220": ("LG Display", "韓股", "034220.KS", "面板", ["LG Display", "樂金顯示"]),
}

# 出處：key → (媒體, 日期, 標題, 網址, 原文摘錄)
# 標題只放真實標題（不知道就留空）；摘錄只放開原文核對過的句子（沒有就留空，網頁只顯示標題）
SOURCES = {
    "tsmc-customers": ("工商時報", "2026-02-27", "台積大客戶換人！輝達超車蘋果 最燒錢「美國廠」大賺161億原因找到了",
                       "https://www.ctee.com.tw/news/20260227700496-430501", "蘋果、輝達、超微、高通與博通等皆為重要客戶"),
    "ase-nvda": ("經濟日報", "2026-03-31", "封測廠 AI 戰略地位激增 大摩調升這二檔個股目標價",
                 "https://money.udn.com/money/amp/story/5607/9414552", "日月光投控目前仍為輝達（NVIDIA）GPU主要的oS封裝供應商之一"),
    "ase-aapl": ("科技新報", "2020-09-16", "蘋果推新 Apple Watch，封測和載板台廠吃補",
                 "https://technews.tw/2020/09/16/apple-apple-watch-s6-benefit-tw-packaging-and-testing-pcb-plant/",
                 "法人指出包括封測大廠日月光投控、IC 載板廠南電和景碩切入相關供應鏈吃補"),
    "kyec-nvda": ("理財周刊", "2025-08-07", "輝達包下！京元電7月營收29.18億元 年月雙增",
                  "https://www.moneyweekly.com.tw/_Article?AID=196613", ""),
    "asic-ctee": ("工商時報", "2025-06-01", "客製化ASIC需求旺 台廠樂", "https://www.ctee.com.tw/news/20250601700036-430501",
                  "創意取得微軟、谷歌專案；亞馬遜AWS持續打造推論Inferentia晶片，由世芯-KY助拳；聯發科也加入戰局，為谷歌TPU張量處理器提供設計服務"),
    "mtk-nvda": ("科技新報", "", "輝達 GB10 晶片高度合作，引發市場臆測可能收購聯發科", "https://technews.tw/?p=1435456",
                 ""),
    "foxconn": ("科技新報", "2025-03-19", "劉揚偉現身 GTC：兩年內鴻海伺服器營收超越 iPhone", "https://technews.tw/2025/03/19/2025-gtc-honhai/",
                "與輝達共同開發的次世代GB300 NVL72伺服器機櫃"),
    "quanta": ("中央社", "2024-04-02", "AI需求強 廣達股價衝今年新高領漲伺服器族群", "https://www.cna.com.tw/news/afe/202404020047.aspx",
               "廣達拿下Google、AWS（亞馬遜雲端運算服務）、Meta等3大雲端服務供應商的GB200伺服器訂單"),
    "wiwynn": ("自由時報", "2023-08-08", "緯穎3大AI客戶佔有率提升 馬國新廠強化出貨中東", "https://ec.ltn.com.tw/article/breakingnews/4390146",
               "緯穎持續向美系雲端服務供應商（CSP）Meta、微軟（Microsoft）、亞馬遜（Amazon）出貨AI伺服器"),
    "wistron": ("數位時代", "2023-10-03", "緯創入手Nvidia新訂單，明年首季顯著出貨！一窺拿下輝達AI伺服器大單的秘密",
                "https://www.bnext.com.tw/article/76027/wistron-ai-server", "緯創是Nvidia DGX與HGX伺服器主力供應商；受惠於微軟等美國大型雲端服務供應商訂單增加"),
    "inventec": ("科技新報", "2024-06-11", "英業達傳首度打入 Meta，明年出貨 GB200 伺服器", "https://technews.tw/?p=1239953",
                 "取得微軟、Google、亞馬遜等供應鏈訂單"),
    "gigabyte": ("自由時報", "", "技嘉葉培城：GB300出貨展望正向 H2顯卡動能優於預期", "https://ec.ltn.com.tw/article/breakingnews/5182650",
                 ""),
    "asus": ("科技新報", "2025-08-15", "華碩預告 GB300 伺服器、桌上型 AI 超級電腦第三季出貨", "https://finance.technews.tw/2025/08/15/asus-2025-q2-earnings/",
             ""),
    "accton": ("經濟日報", "", "亞馬遜財報超乎預期 帶旺智邦業績 股價亮燈漲停", "https://money.udn.com/money/amp/story/5607/9667042",
               ""),
    "delta": ("鉅亨網", "2025-03-21", "", "https://news.cnyes.com/news/id/5908550",
              "已取得輝達推薦供應商(Recommended Vender List, RVL) 與合格供應商 (Approved Vendor List, AVL) 資格"),
    "kingslide": ("DIGITIMES", "2026-02-03", "川湖、南俊國際在列NVIDIA滑軌鏈　富世達2026卡位可期",
                  "https://www.digitimes.com.tw/tech/dt/n/shwnws.asp?id=745441", ""),
    "lotes": ("風傳媒", "2026-05-19", "瑤池金母首建倉！00981A納入「傳統連接器廠切入液冷」營收兩位數成長，為何輝達伺服器都少不了它！", "https://www.storm.mg/article/11133298",
              ""),
    "winway": ("鏡週刊", "2026-07-19", "", "https://www.mirrormedia.mg/story/20260714fin001",
               "包括輝達（NVIDIA）、超微（AMD）等北美大客戶就貢獻8成以上營收"),
    "gce": ("優分析", "2025-02-18", "【PCB】金像電(2368)-這三大成長動能支撐未來營運!", "https://uanalyze.com.tw/articles/2010710638",
            "AWS Trainium 2 就是一個關鍵案例"),
    "unimicron": ("Smart 智富", "2026-07-27", "ABF載板需求爆發，「載板三雄」欣興、景碩、南電，誰能成為最大贏家？",
                  "https://smart.businessweekly.com.tw/Reading/IndepArticle.aspx?id=6022472",
                  "欣興已成為輝達（Nvidia）的GPU載板第二大供應商…還深度參與了英特爾（Intel）、超微（AMD）等一線大廠的設計"),
    "yageo": ("鉅亨網", "2024-09-26", "國巨陳泰銘：AI營收比重約5% 產品已供應最新一代AI伺服器", "https://anuenews.cnyes.com/news/id/5725076",
              "輝達或是AI伺服器代工廠都是國巨客戶"),
    "iphone-parts": ("聯合報", "2026-03-24", "iPhone零組件完整曝光 這三家台廠最受矚目", "https://udn.com/news/story/7251/9400072",
                     "手機鏡頭大廠大立光，今年來自iPhone的營收貢獻占比最高、達40%-45%；砷化鎵大廠穩懋，向來是是蘋果iPhone PA及3D感測（VCSEL）的核心供應商；臻鼎同樣以iPhone用PCB為主力大宗產品"),
    "pegatron": ("科技新報", "2021-07-25", "iPhone 13 供應鏈爭霸，鴻海能擠下「它」繼續當老大？", "https://technews.tw/?p=773774",
                 "6.1吋則由鴻海、和碩七三對分，最低階5.4吋又是和碩全拿"),
    "hota": ("科技新報", "2019-11-26", "特斯拉上海廠估 2020 年第三季滿載，台廠供應鏈可受惠",
             "https://technews.tw/2019/11/26/tesla-shanghai-plant-estimates-full-load-in-third-quarter-of-2020/",
             "和大透過供應電動車減速齒輪箱關鍵零配件，切入特斯拉供應鏈"),
    "jasm": ("科技新報", "2024-02-26", "魏哲家開口一句話，索尼從採購談判轉為生產合作", "https://technews.tw/2024/02/26/jasm-sony-cooperation/",
             "會議主題隨即從採購談判，轉變為生產合作"),
    "tel": ("鉅亨網", "", "", "https://news.cnyes.com/news/id/6097211",
            "東京威力科創…是台積電、三星與英特爾等晶片巨擘的重要設備供應商"),
    "advantest-tsmc": ("科技新報", "2020-10-22", "",
                       "https://technews.tw/2020/10/22/increased-demand-for-system-on-chip-testing/",
                       "半導體測試設備大廠愛德萬表示，台積電布局 3 奈米及以下晶圓先進製程，長期帶動測試設備需求"),
    "advantest-ase": ("愛德萬測試公告", "2023-10-03", "",
                      "https://www.advantest.com/tw/news/2023/20231003.html", "愛德萬測試榮獲日月光投控頒發『2022最佳供應商獎』"),
    "hbm4": ("科技新報", "", "HBM4 勝出關鍵在 Base Die 和客製化，SK 海力士、三星紛與台積結盟", "https://technews.tw/?p=1279012",
             ""),
    "hotai": ("優分析", "2026-01-02", "〈車市〉和泰車旗下二大品牌拿下37%市占創16年來新高 連24年稱霸",
              "https://uanalyze.com.tw/articles/3220744051", "和泰車代理的 TOYOTA 和 LEXUS 品牌"),
    # ---- 台股同業族群的出處（標題或原文把同組公司放在一起比較）----
    "peer-foundry": ("優分析", "2026-03-12", "研調：前十大晶圓代工廠去年Q4產值季增2.6% 台積電市占率7成",
                     "https://uanalyze.com.tw/articles/2939548893", "台積電市占率達 70.4%；聯電…營收季增 0.9%；世界先進…營收季減 1.6%；力積電…"),
    "peer-osat": ("財報狗", "", "AI 晶片競賽推升先進封裝需求 日月光投控、力成、京元電資本支出衝 3700 億元",
                  "https://statementdog.com/news/16363", ""),
    "peer-asic": ("Smart 智富", "2025-12-18", "世芯、創意本益比不低，現在還能入手？分析師：「ASIC超級週期」才剛要啟動",
                  "https://smart.businessweekly.com.tw/Reading/IndepArticle.aspx?ID=6021190", ""),
    "peer-ems-1": ("經濟日報", "", "電子五哥4月營收比拚 鴻海穩居龍頭寶座", "https://money.udn.com/money/amp/story/5607/9494360", ""),
    "peer-ems-2": ("優分析", "", "AI伺服器帶旺廣達、緯創、英業達同創最佳9月 電子五哥Q4展望一次看",
                   "https://uanalyze.com.tw/articles/3251134873", ""),
    "peer-probe": ("優分析", "", "AI測試大升級 測試介面三雄營運爆發", "https://uanalyze.com.tw/articles/4964334510",
                   ""),
    "peer-power": ("理財周刊", "", "", "https://www.moneyweekly.com.tw/_Article?AID=200598",
                   "AI時代推升電源供應器地位…光寶科、台達電同受惠"),
    "peer-memory": ("今周刊", "2026-04-07", "記憶體股要滿血復活？南亞科、旺宏、華邦電…我該買誰才會漲得快？",
                    "https://www.businesstoday.com.tw/article/category/183008/post/202604070027/", ""),
    "peer-passive": ("聯合報", "", "國巨股價漲破千元 華新科、禾伸堂近3個月翻倍噴…被動元件漲價潮 誰真正抓住成長商機?",
                     "https://udn.com/news/story/6839/9599753", ""),
    "peer-lens": ("科技新報", "2022-08-30", "", "https://technews.tw/2022/08/30/optical-lens-q3/",
                  "光學鏡頭大廠大立光、玉晶光今年 7 月營收同步加溫"),
    "peer-pa": ("鉅亨網", "", "PA三雄 穩懋 宏捷科 全新營收止穩 砷化鎵族群AI時代應用大", "https://news.cnyes.com/news/id/5365801", ""),
    "peer-panel": ("優分析", "", "面板雙虎8月營收走勢不同調 友達月增17% 群創繳年增", "https://uanalyze.com.tw/articles/3224433108", ""),
    "peer-board": ("Yahoo股市", "", "板卡三雄6月業績 華碩月增逾3成最強 技嘉AI伺服器潛力足股價再創高",
                   "https://tw.stock.yahoo.com/news/%E6%9D%BF%E5%8D%A1%E4%B8%89%E9%9B%846%E6%9C%88%E6%A5%AD%E7%B8%BE-%E8%8F%AF%E7%A2%A9%E6%9C%88%E5%A2%9E%E9%80%BE3%E6%88%90%E6%9C%80%E5%BC%B7-%E6%8A%80%E5%98%89ai%E4%BC%BA%E6%9C%8D%E5%99%A8%E6%BD%9B%E5%8A%9B%E8%B6%B3%E8%82%A1%E5%83%B9%E5%86%8D%E5%89%B5%E9%AB%98-040939241.html", ""),
    "peer-switch": ("優分析", "", "資料中心交換器迎800G技術換代 智邦、明泰、啓碁搶攻2026年升級商機",
                    "https://uanalyze.com.tw/articles/5857443265", ""),
    "peer-pcb": ("經濟日報", "2026-07-22", "GPU、ASIC 雙火點燃 PCB！欣興、南電亮燈 臻鼎、景碩大漲逾8%",
                 "https://money.udn.com/money/amp/story/5607/9643480", ""),
    "peer-serverpcb": ("經濟日報", "", "伺服板龍頭金像電重返600元以上 健鼎高技再掀比價", "https://money.udn.com/money/amp/story/5607/9213240", ""),
}

# (台股代號, 名稱, 龍頭, 關係, 角色, 出處 key；同業為 None)
LINKS = [
    ("2330", "台積電", "NVDA", "供應商", "晶圓代工、先進封裝", "tsmc-customers"),
    ("2330", "台積電", "AAPL", "供應商", "晶圓代工", "tsmc-customers"),
    ("2330", "台積電", "AMD", "供應商", "晶圓代工、先進封裝", "tsmc-customers"),
    ("2330", "台積電", "AVGO", "供應商", "晶圓代工、先進封裝", "tsmc-customers"),
    ("2330", "台積電", "6758", "合作", "與 Sony 合資熊本 JASM 晶圓廠", "jasm"),
    ("2330", "台積電", "8035", "客戶", "採購東京威力的半導體設備", "tel"),
    ("2330", "台積電", "6857", "客戶", "先進製程帶動愛德萬測試設備需求", "advantest-tsmc"),
    ("2330", "台積電", "000660", "合作", "HBM4 base die 合作", "hbm4"),
    ("2330", "台積電", "005930", "同業", "晶圓代工的主要競爭對手", None),
    ("3711", "日月光投控", "NVDA", "供應商", "GPU 封裝（oS）", "ase-nvda"),
    ("3711", "日月光投控", "AAPL", "供應商", "Apple Watch 系統級封裝", "ase-aapl"),
    ("3711", "日月光投控", "6857", "客戶", "採購愛德萬測試設備（最佳供應商獎）", "advantest-ase"),
    ("2449", "京元電子", "NVDA", "供應商", "AI GPU 測試", "kyec-nvda"),
    ("3443", "創意", "MSFT", "供應商", "ASIC 設計服務", "asic-ctee"),
    ("3443", "創意", "GOOGL", "供應商", "ASIC 設計服務", "asic-ctee"),
    ("3661", "世芯-KY", "AMZN", "供應商", "AWS Inferentia ASIC 設計服務", "asic-ctee"),
    ("2454", "聯發科", "GOOGL", "供應商", "Google TPU 設計服務", "asic-ctee"),
    ("2454", "聯發科", "NVDA", "合作", "共同設計 GB10 晶片", "mtk-nvda"),
    ("2317", "鴻海", "NVDA", "供應商", "AI 伺服器機櫃（GB300 NVL72）", "foxconn"),
    ("2317", "鴻海", "AAPL", "供應商", "iPhone 組裝", "foxconn"),
    ("2382", "廣達", "GOOGL", "供應商", "GB200 AI 伺服器", "quanta"),
    ("2382", "廣達", "AMZN", "供應商", "GB200 AI 伺服器", "quanta"),
    ("2382", "廣達", "META", "供應商", "GB200 AI 伺服器", "quanta"),
    ("6669", "緯穎", "META", "供應商", "AI 伺服器", "wiwynn"),
    ("6669", "緯穎", "MSFT", "供應商", "AI 伺服器", "wiwynn"),
    ("6669", "緯穎", "AMZN", "供應商", "AI 伺服器", "wiwynn"),
    ("3231", "緯創", "NVDA", "供應商", "DGX/HGX 伺服器、GPU 基板", "wistron"),
    ("3231", "緯創", "MSFT", "供應商", "雲端伺服器", "wistron"),
    ("2356", "英業達", "MSFT", "供應商", "伺服器主機板", "inventec"),
    ("2356", "英業達", "GOOGL", "供應商", "伺服器主機板", "inventec"),
    ("2356", "英業達", "AMZN", "供應商", "伺服器主機板", "inventec"),
    ("2356", "英業達", "META", "供應商", "GB200 伺服器（透過 ZT）", "inventec"),
    ("2376", "技嘉", "NVDA", "合作", "採用 NVIDIA GB300 平台的伺服器", "gigabyte"),
    ("2357", "華碩", "NVDA", "合作", "採用 NVIDIA GB300 平台的伺服器", "asus"),
    ("2345", "智邦", "AMZN", "供應商", "資料中心網路交換器", "accton"),
    ("2308", "台達電", "NVDA", "供應商", "電源、液冷（輝達 RVL/AVL 供應商）", "delta"),
    ("2059", "川湖", "NVDA", "供應商", "伺服器滑軌", "kingslide"),
    ("3533", "嘉澤", "NVDA", "供應商", "CPU 插槽、連接器", "lotes"),
    ("6515", "穎崴", "NVDA", "供應商", "AI 晶片測試座", "winway"),
    ("6515", "穎崴", "AMD", "供應商", "AI 晶片測試座", "winway"),
    ("2368", "金像電", "AMZN", "供應商", "AWS Trainium 伺服器 PCB", "gce"),
    ("3037", "欣興", "NVDA", "供應商", "GPU ABF 載板", "unimicron"),
    ("3037", "欣興", "AMD", "供應商", "ABF 載板", "unimicron"),
    ("2327", "國巨", "NVDA", "供應商", "被動元件", "yageo"),
    ("3008", "大立光", "AAPL", "供應商", "iPhone 鏡頭", "iphone-parts"),
    ("3105", "穩懋", "AAPL", "供應商", "iPhone PA、3D 感測", "iphone-parts"),
    ("4958", "臻鼎-KY", "AAPL", "供應商", "iPhone PCB", "iphone-parts"),
    ("4938", "和碩", "AAPL", "供應商", "iPhone 組裝", "pegatron"),
    ("1536", "和大", "TSLA", "供應商", "電動車減速齒輪箱", "hota"),
    ("2207", "和泰車", "7203", "合作", "TOYOTA、LEXUS 台灣代理", "hotai"),
    # 同業：同產品線，依產業分類
    ("2408", "南亞科", "005930", "同業", "DRAM", None),
    ("2408", "南亞科", "000660", "同業", "DRAM", None),
    ("2408", "南亞科", "MU", "同業", "DRAM", None),
    ("2344", "華邦電", "005930", "同業", "DRAM、Flash", None),
    ("2344", "華邦電", "000660", "同業", "DRAM", None),
    ("2344", "華邦電", "MU", "同業", "DRAM、Flash", None),
    ("2492", "華新科", "6981", "同業", "MLCC 被動元件", None),
    ("2327", "國巨", "6981", "同業", "MLCC 被動元件", None),
    ("3481", "群創", "034220", "同業", "面板", None),
]


def build_map() -> dict:
    """{台股代號: {code, name, links: {龍頭: (關係, 角色, 出處key)}}}"""
    out: dict[str, dict] = {}
    for code, name, ld, rel, role, src in LINKS:
        assert ld in LEADERS, ld
        assert src is None or src in SOURCES, src
        assert rel == "同業" or src, f"{name}→{ld} 不是同業就必須有出處"
        s = out.setdefault(code, {"code": code, "name": name, "links": {}})
        s["links"][ld] = (rel, role, src)
    return out


TW_MAP = build_map()

# 台股同業／競爭者：(族群名稱, [(代號, 名稱)], [出處 key])。
# 每一組都要有一篇新聞的標題或原文把這些公司放在一起比較，才算同業。
PEER_GROUPS = [
    ("晶圓代工", [("2330", "台積電"), ("2303", "聯電"), ("5347", "世界先進"), ("6770", "力積電")], ["peer-foundry"]),
    ("封裝測試", [("3711", "日月光投控"), ("6239", "力成"), ("2449", "京元電子")], ["peer-osat"]),
    ("ASIC 設計服務", [("3661", "世芯-KY"), ("3443", "創意")], ["peer-asic"]),
    ("伺服器組裝代工（電子五哥）", [("2317", "鴻海"), ("2382", "廣達"), ("3231", "緯創"), ("2356", "英業達")], ["peer-ems-1", "peer-ems-2"]),
    ("iPhone 組裝", [("2317", "鴻海"), ("4938", "和碩")], ["pegatron"]),
    ("測試介面三雄", [("6515", "穎崴"), ("6223", "旺矽"), ("6510", "精測")], ["peer-probe"]),
    ("電源雙雄", [("2308", "台達電"), ("2301", "光寶科")], ["peer-power"]),
    ("記憶體", [("2408", "南亞科"), ("2344", "華邦電"), ("2337", "旺宏")], ["peer-memory"]),
    ("被動元件", [("2327", "國巨"), ("2492", "華新科"), ("3026", "禾伸堂")], ["peer-passive"]),
    ("光學鏡頭", [("3008", "大立光"), ("3406", "玉晶光")], ["peer-lens"]),
    ("PA 三雄（砷化鎵）", [("3105", "穩懋"), ("8086", "宏捷科"), ("2455", "全新")], ["peer-pa"]),
    ("面板雙虎", [("2409", "友達"), ("3481", "群創")], ["peer-panel"]),
    ("板卡三雄", [("2357", "華碩"), ("2376", "技嘉"), ("2377", "微星")], ["peer-board"]),
    ("資料中心交換器", [("2345", "智邦"), ("3380", "明泰"), ("6285", "啟碁")], ["peer-switch"]),
    ("ABF 載板三雄", [("3037", "欣興"), ("3189", "景碩"), ("8046", "南電")], ["unimicron"]),
    ("PCB／載板", [("4958", "臻鼎-KY"), ("3037", "欣興"), ("8046", "南電"), ("3189", "景碩")], ["peer-pcb"]),
    ("伺服器 PCB", [("2368", "金像電"), ("3044", "健鼎"), ("5439", "高技")], ["peer-serverpcb"]),
    ("伺服器滑軌", [("2059", "川湖"), ("6584", "南俊國際"), ("6805", "富世達")], ["kingslide"]),
]


def build_peers() -> dict:
    """{台股代號: [{"code", "name", "group", "sources"}]}（不含自己）"""
    out: dict[str, list] = {}
    for group, members, srcs in PEER_GROUPS:
        assert srcs and all(k in SOURCES for k in srcs), group
        for code, _ in members:
            for other, oname in members:
                if other != code:
                    out.setdefault(code, []).append({"code": other, "name": oname, "group": group, "sources": srcs})
    return out


TW_PEERS = build_peers()
# 所有會出現在網站上的台股代號與名稱（供應鏈＋同業），給 supply.py 抓股價
ALL_TW = {**{c: n for _, members, _ in PEER_GROUPS for c, n in members}, **{c: t["name"] for c, t in TW_MAP.items()}}
