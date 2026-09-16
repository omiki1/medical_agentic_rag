"""Small, attributed Chinese paraphrases; source-checked, NOT clinician-reviewed.

Each source has fewer than 200 words of paraphrased content. Do not infer a
GRADE evidence rating from the publisher or from the fact-sheet format.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    (
        "hypertension",
        "高血压",
        "2025-09-25",
        ["hypertension", "血压高"],
        [
            (
                "overview",
                "认识高血压",
                "高血压是血管内压力持续升高的状况。是否患病需要规范测量和专业评估，不能只凭感觉判断。",
                [],
            ),
            (
                "symptom",
                "症状与识别",
                "多数高血压患者没有明显症状。血压很高时可能出现头痛、视力模糊等表现；定期测量血压比依赖症状更可靠。",
                [("DISEASE_SYMPTOM", "头痛"), ("DISEASE_SYMPTOM", "视力模糊")],
            ),
            (
                "prevention",
                "生活方式管理",
                "减少盐摄入、保持适宜体重、规律活动和戒烟有助于控制血压。生活方式改善后，部分患者仍需要遵医嘱服药。",
                [],
            ),
            (
                "test",
                "怎样发现高血压",
                "血压测量是发现高血压的关键。WHO 资料强调在不同日期进行测量，并由医务人员评估心血管风险及相关疾病。",
                [("DISEASE_CHECK", "血压测量")],
            ),
            (
                "medication",
                "药物类别",
                "高血压的常见药物类别包括 ACE 抑制剂、血管紧张素受体阻滞剂、钙通道阻滞剂和利尿剂。具体选择需结合患者情况。",
                [("DISEASE_DRUG", "ACE抑制剂"), ("DISEASE_DRUG", "血管紧张素受体阻滞剂")],
            ),
        ],
    ),
    (
        "diabetes",
        "糖尿病",
        "2024-11-14",
        ["diabetes", "二型糖尿病", "2型糖尿病", "Ⅱ型糖尿病"],
        [
            (
                "overview",
                "认识糖尿病",
                "糖尿病与胰岛素分泌不足或利用障碍有关，可造成血糖升高。2 型糖尿病的症状可能较轻，长期不被察觉。",
                [],
            ),
            (
                "symptom",
                "常见症状",
                "糖尿病可能出现明显口渴、排尿增多、视力模糊、疲乏和非意愿性体重下降。这些表现不能单独用于确诊。",
                [("DISEASE_SYMPTOM", "口渴"), ("DISEASE_SYMPTOM", "多尿"), ("DISEASE_SYMPTOM", "体重下降")],
            ),
            (
                "prevention",
                "预防与管理",
                "健康饮食、规律活动、维持适宜体重和避免烟草有助于预防或延缓 2 型糖尿病。已患病者还需要按计划随访。",
                [],
            ),
            (
                "test",
                "检查与随访",
                "血糖检测有助于早期发现糖尿病。随访还应关注眼底、肾脏及足部问题，以发现相关并发症。",
                [("DISEASE_CHECK", "血糖检测"), ("DISEASE_CHECK", "眼底检查")],
            ),
            (
                "medication",
                "治疗知识",
                "部分 2 型糖尿病患者需要降糖药物，例如二甲双胍或胰岛素。1 型糖尿病患者需要胰岛素治疗；不能仅凭症状选药。",
                [("DISEASE_DRUG", "二甲双胍"), ("DISEASE_DRUG", "胰岛素")],
            ),
        ],
    ),
    (
        "asthma",
        "哮喘",
        "2026-04-28",
        ["asthma", "支气管哮喘"],
        [
            (
                "overview",
                "认识哮喘",
                "哮喘与气道炎症及气道周围肌肉收缩有关，可影响儿童和成人。恰当治疗有助于控制症状和维持日常活动。",
                [],
            ),
            (
                "symptom",
                "常见表现",
                "哮喘常见咳嗽、喘鸣、气短和胸部紧缩感，表现可反复变化，在夜间或运动时加重。类似症状也可能来自其他疾病。",
                [("DISEASE_SYMPTOM", "咳嗽"), ("DISEASE_SYMPTOM", "喘鸣")],
            ),
            (
                "prevention",
                "减少诱因",
                "尘埃、烟雾、花粉及动物毛屑可能诱发哮喘症状。识别并减少个体诱因的暴露，有助于症状管理。",
                [],
            ),
            (
                "treatment",
                "治疗原则",
                "吸入药物能够帮助控制哮喘。出现症状应由医务人员评估，严重发作可能需要紧急医疗处理。",
                [],
            ),
        ],
    ),
    (
        "chronic-obstructive-pulmonary-disease-(copd)",
        "慢性阻塞性肺疾病",
        "2026-06-10",
        ["COPD", "慢阻肺"],
        [
            (
                "overview",
                "认识慢阻肺",
                "慢性阻塞性肺疾病会导致气流受限。吸烟和空气污染是常见危险因素，患者还可能合并其他健康问题。",
                [],
            ),
            (
                "symptom",
                "常见表现",
                "慢阻肺常见长期咳嗽、咳痰、呼吸费力和疲乏。症状可能在数日内明显加重，这类情况称为急性加重。",
                [("DISEASE_SYMPTOM", "慢性咳嗽"), ("DISEASE_SYMPTOM", "咳痰")],
            ),
            (
                "prevention",
                "减少危险因素",
                "戒烟、减少空气污染暴露以及通过疫苗预防感染，是慢阻肺管理的重要组成部分。",
                [],
            ),
            (
                "treatment",
                "治疗原则",
                "慢阻肺目前不能根治，但药物、适用时的氧疗及肺康复可改善症状。具体方案需要医务人员评估。",
                [],
            ),
        ],
    ),
    (
        "influenza-(seasonal)",
        "流感",
        "2025-02-28",
        ["influenza", "季节性流感"],
        [
            (
                "overview",
                "认识流感",
                "季节性流感是流感病毒引起的急性呼吸道感染，可在人与人之间传播。多数患者可以恢复，但部分人群可能出现重症。",
                [],
            ),
            (
                "symptom",
                "常见表现",
                "流感可突然出现发热、咳嗽、咽痛、肌肉和关节疼痛以及明显疲乏。咳嗽有时可持续两周或更久。",
                [("DISEASE_SYMPTOM", "发热"), ("DISEASE_SYMPTOM", "咳嗽")],
            ),
            (
                "prevention",
                "预防原则",
                "接种流感疫苗是预防流感的重要方法。咳嗽或打喷嚏时注意防护，有助于减少传播。",
                [],
            ),
            (
                "treatment",
                "恢复与就医",
                "休息和补充液体有助于流感患者恢复。严重症状或存在重症危险因素时，需要医疗评估。",
                [],
            ),
        ],
    ),
    (
        "tuberculosis",
        "肺结核",
        "2026-03-24",
        ["TB", "结核病"],
        [
            (
                "overview",
                "认识结核病",
                "结核病由细菌引起，最常影响肺部。患病者咳嗽、打喷嚏等可使病原体经空气传播。",
                [],
            ),
            (
                "cause",
                "感染与发病",
                "结核感染不等于已发生结核病。感染者通常没有不适，只有部分人会进展为活动性疾病；免疫功能低下等因素增加风险。",
                [],
            ),
            (
                "prevention",
                "预防知识",
                "结核病可以预防和治疗。部分国家对婴幼儿接种卡介苗，以降低严重结核病及死亡风险。",
                [],
            ),
            (
                "treatment",
                "治疗原则",
                "结核病通常需要抗生素治疗。治疗必须由专业医疗机构管理，未经治疗的结核病可能危及生命。",
                [],
            ),
        ],
    ),
    (
        "hepatitis-b",
        "乙型肝炎",
        "2026-07-28",
        ["乙肝", "hepatitis b", "HBV"],
        [
            (
                "overview",
                "认识乙型肝炎",
                "乙型肝炎由乙肝病毒感染引起，可表现为急性或慢性肝脏疾病。慢性感染增加肝硬化和肝癌风险。",
                [],
            ),
            (
                "cause",
                "传播途径",
                "乙肝可通过母婴传播、血液及某些体液接触传播。医疗操作中的不安全注射和锐器暴露也可能带来风险。",
                [],
            ),
            (
                "prevention",
                "预防原则",
                "乙肝疫苗能够有效预防乙肝感染。新生儿出生后及时接种，并按当地免疫程序完成后续剂次很重要。",
                [],
            ),
        ],
    ),
]


def main():
    rows = []
    for slug, entity, published, aliases, sections in SOURCES:
        for facet, heading, text, edges in sections:
            rows.append(
                dict(
                    id=f"who:{slug}:{facet}",
                    source_id=f"who:{slug}",
                    title=f"{entity} · {heading}",
                    text=text,
                    entity=entity,
                    facet=facet,
                    source_title=f"WHO · {entity}事实清单",
                    source_url=f"https://www.who.int/news-room/fact-sheets/detail/{slug}",
                    source_type="public_health",
                    review_status="source_checked",
                    published_at=published,
                    checked_at="2026-09-07",
                    version="2026-09-07",
                    aliases=aliases,
                    edges=edges,
                )
            )
    (ROOT / "data/curated.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(rows)} attributed evidence excerpts from {len(SOURCES)} sources")


if __name__ == "__main__":
    main()
