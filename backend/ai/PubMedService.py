import asyncio
import re
from xml.etree import ElementTree

import httpx
from rag.entity.Evidence import Document, Evidence


class PubMedService:
    """Opt-in public literature lookup. It does NOT turn abstracts into clinical guidance."""

    ENDPOINT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    # Chinese user terms -> clean English PubMed query terms. Keys are the normalized
    # entities people actually say (from QueryTopics/EXPANSIONS), values are precise
    # disease terms. Extended from WHO bilingual corpus + common patient vocabulary.
    TRANSLATIONS = {
        # --- 心血管 / 代谢 ---
        "高血压": "hypertension",
        "低血压": "hypotension",
        "血压": "blood pressure",
        "糖尿病": "diabetes",
        "高血糖": "hyperglycemia",
        "低血糖": "hypoglycemia",
        "高血脂": "hyperlipidemia",
        "高胆固醇": "hypercholesterolemia",
        "肥胖": "obesity",
        "超重": "overweight",
        "冠心病": "coronary heart disease",
        "心绞痛": "angina",
        "心力衰竭": "heart failure",
        "心律失常": "arrhythmia",
        "心房颤动": "atrial fibrillation",
        "心肌梗死": "myocardial infarction",
        "卒中": "stroke",
        "中风": "stroke",
        # --- 甲状腺 / 内分泌 ---
        "甲亢": "hyperthyroidism",
        "甲减": "hypothyroidism",
        "甲状腺功能亢进": "hyperthyroidism",
        "甲状腺功能减退": "hypothyroidism",
        # --- 呼吸 ---
        "哮喘": "asthma",
        "慢性阻塞性肺疾病": "COPD",
        "肺炎": "pneumonia",
        "肺结核": "tuberculosis",
        "流感": "influenza",
        "支气管炎": "bronchitis",
        "咳嗽": "cough",
        "过敏性鼻炎": "allergic rhinitis",
        # --- 消化 ---
        "胃食管反流": "gastroesophageal reflux",
        "胃炎": "gastritis",
        "胃溃疡": "peptic ulcer",
        "胃癌": "stomach cancer",
        "肝炎": "hepatitis",
        "乙型肝炎": "hepatitis B",
        "丙型肝炎": "hepatitis C",
        "肝硬化": "liver cirrhosis",
        "脂肪肝": "fatty liver",
        "胰腺炎": "pancreatitis",
        "腹泻": "diarrhea",
        "便秘": "constipation",
        "肠易激综合征": "irritable bowel syndrome",
        "炎症性肠病": "inflammatory bowel disease",
        "阑尾炎": "appendicitis",
        "结直肠癌": "colorectal cancer",
        # --- 神经 / 精神 ---
        "偏头痛": "migraine",
        "头痛": "headache",
        "癫痫": "epilepsy",
        "帕金森病": "Parkinson disease",
        "阿尔茨海默病": "Alzheimer disease",
        "痴呆": "dementia",
        "多发性硬化": "multiple sclerosis",
        "失眠": "insomnia",
        "焦虑": "anxiety",
        "抑郁": "depression",
        "抑郁症": "depression",
        "精神分裂症": "schizophrenia",
        "自闭症": "autism",
        # --- 感染 ---
        "疟疾": "malaria",
        "登革热": "dengue",
        "寨卡": "Zika virus",
        "狂犬病": "rabies",
        "脑膜炎": "meningitis",
        "梅毒": "syphilis",
        "艾滋病": "HIV",
        "带状疱疹": "herpes zoster",
        "水痘": "chickenpox",
        "麻疹": "measles",
        "腮腺炎": "mumps",
        "百日咳": "whooping cough",
        "破伤风": "tetanus",
        "伤寒": "typhoid",
        "霍乱": "cholera",
        "结核": "tuberculosis",
        # --- 骨科 / 风湿 ---
        "骨质疏松": "osteoporosis",
        "关节炎": "arthritis",
        "类风湿性关节炎": "rheumatoid arthritis",
        "痛风": "gout",
        "腰痛": "low back pain",
        "颈椎病": "cervical spondylosis",
        # --- 肾病 / 泌尿 ---
        "肾结石": "kidney stones",
        "慢性肾病": "chronic kidney disease",
        "肾衰竭": "kidney failure",
        "尿路感染": "urinary tract infection",
        "前列腺增生": "benign prostatic hyperplasia",
        # --- 皮肤 / 过敏 ---
        "湿疹": "eczema",
        "荨麻疹": "urticaria",
        "银屑病": "psoriasis",
        "痤疮": "acne",
        "过敏": "allergy",
        # --- 妇科 / 儿科 ---
        "多囊卵巢综合征": "polycystic ovary syndrome",
        "子宫内膜异位症": "endometriosis",
        "宫颈癌": "cervical cancer",
        "乳腺癌": "breast cancer",
        "儿童肺炎": "pneumonia in children",
        "肺炎链球菌": "pneumococcal disease",
        # --- 眼科 / 耳鼻喉 ---
        "青光眼": "glaucoma",
        "白内障": "cataract",
        "中耳炎": "otitis media",
        "甲状腺眼病": "thyroid eye disease",
        # --- 其他高频 ---
        "癌症": "cancer",
        "肺癌": "lung cancer",
        "肾脏疾病": "kidney disease",
        "焦虑症": "anxiety disorders",
        "多囊肾": "polycystic kidney disease",
        "甲状腺结节": "thyroid nodule",
        "贫血": "anemia",
        "缺铁性贫血": "iron deficiency anemia",
        "维生素D缺乏": "vitamin D deficiency",
        "脱水": "dehydration",
        "晕厥": "syncope",
        "头晕": "dizziness",
        "眩晕": "vertigo",
        "耳鸣": "tinnitus",
    }

    def __init__(self, settings):
        self.settings = settings
        self.lock = asyncio.Lock()

    async def search(self, entities):
        # Send recognized public terms only; never send the patient's raw question/history.
        terms = [self.TRANSLATIONS[e] for e in entities if e in self.TRANSLATIONS]
        if not self.settings.pubmed_enabled or not terms:
            return []
        # The first matched entity becomes the Document.entity so topic matching and
        # citation grading recognize the literature as being about the asked disease.
        entity_label = next(e for e in entities if e in self.TRANSLATIONS)
        async with self.lock, httpx.AsyncClient(timeout=8, trust_env=False) as client:
            params = {
                "db": "pubmed",
                "term": " AND ".join(terms),
                "retmax": 3,
                "retmode": "json",
                "sort": "pub date",
                "tool": "MediAtlas",
            }
            if self.settings.pubmed_email:
                params["email"] = self.settings.pubmed_email
            response = await client.get(self.ENDPOINT + "esearch.fcgi", params=params)
            response.raise_for_status()
            ids = response.json()["esearchresult"]["idlist"]
            if not ids:
                return []
            await asyncio.sleep(0.4)  # NCBI unauthenticated rate limit.
            response = await client.get(
                self.ENDPOINT + "efetch.fcgi", params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}
            )
            response.raise_for_status()
            if len(response.content) > 2_000_000 or b"<!ENTITY" in response.content:
                raise ValueError("Unexpected PubMed response")
            root = ElementTree.fromstring(response.content)
            results = []
            for article in root.findall(".//PubmedArticle"):
                pmid = article.findtext(".//PMID") or ""
                if not re.fullmatch(r"\d+", pmid):
                    continue
                title = "".join(article.find(".//ArticleTitle").itertext())
                abstract = " ".join("".join(x.itertext()) for x in article.findall(".//AbstractText"))
                if abstract:
                    doc = Document(
                        id="pubmed:" + pmid,
                        source_id="pubmed:" + pmid,
                        entity=entity_label,
                        title=title,
                        text=abstract[:1800],
                        source_title="PubMed · 待专业解读的文献摘要",
                        source_url="https://pubmed.ncbi.nlm.nih.gov/" + pmid + "/",
                        source_type="research",
                        language="en",
                        date_provenance="publication_not_extracted",
                    )
                    results.append(Evidence(document=doc, methods=["pubmed"]))
            return results
