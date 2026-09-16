"""把导出的图谱 CSV 整理成可直接执行的 Neo4j 导入包。

为什么按 (alabel, rtype, blabel) 三元组切分关系文件：
    图谱里有 482 组跨标签同名节点（其中 421 组涉及 Disease），因此端点必须按
    (标签, 名称) 匹配，不能只按名称，否则会连到错误的节点上。
    而逐三元组过滤会让 24.5 MB 的关系 CSV 被反复读取 100 多次；
    先切分成小文件，则每行只被读一次，总量不变。

产出：
    import.cypher          约束 + 节点 + 疾病属性 + 关系
    rels/<a>__<r>__<b>.csv 按三元组切分的关系文件
    import-manifest.json   计数与语句清单
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent / "graph-export"
LABELS = [
    "Category", "Check", "Cureway", "Department",
    "Disease", "Dishes", "Drug", "Food", "Symptom",
]
DISEASE_PROPS = [
    "cause", "cost_money", "cure_lasttime", "cured_prob", "desc",
    "get_prob", "get_way", "prevent", "yibao_status",
]


def main() -> int:
    rels_csv = BASE / "rels.csv"
    rels_dir = BASE / "rels"
    rels_dir.mkdir(exist_ok=True)
    for stale in rels_dir.glob("*.csv"):
        stale.unlink()

    # ---- 按三元组切分关系 ----
    handles: dict[tuple[str, str, str], tuple] = {}
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    total = 0
    with rels_csv.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        for row in reader:
            key = (row["alabel"], row["rtype"], row["blabel"])
            if key not in handles:
                path = rels_dir / f"{key[0]}__{key[1]}__{key[2]}.csv"
                handle = path.open("w", encoding="utf-8", newline="")
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(["aname", "bname"])
                handles[key] = (handle, writer)
            handle, writer = handles[key]
            writer.writerow([row["aname"], row["bname"]])
            counts[key] += 1
            total += 1
    for handle, _ in handles.values():
        handle.close()

    # ---- 生成导入脚本 ----
    lines = [
        "// MediAtlas 疾病图谱导入（由 deploy/prepare_graph_import.py 生成）",
        "// 幂等前提：目标图谱为空；关系使用 CREATE，重复执行会产生重复边。",
        "",
        "// ---- 唯一性约束：端点按 (标签, 名称) 匹配的前提 ----",
    ]
    for label in LABELS:
        lines.append(
            f"CREATE CONSTRAINT med_{label.lower()}_name IF NOT EXISTS "
            f"FOR (n:`{label}`) REQUIRE n.name IS UNIQUE;"
        )

    lines += ["", "// ---- 节点 ----"]
    for label in LABELS:
        lines += [
            f"LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row",
            f"WITH row WHERE row.label = '{label}'",
            f"MERGE (n:`{label}` {{name: row.name}});",
            "",
        ]

    lines += ["// ---- 疾病属性 ----"]
    sets = ", ".join(f"d.`{p}` = CASE WHEN row.`{p}` = '' THEN null ELSE row.`{p}` END" for p in DISEASE_PROPS)
    lines += [
        "LOAD CSV WITH HEADERS FROM 'file:///disease.csv' AS row",
        "MATCH (d:Disease {name: row.name})",
        f"SET {sets};",
        "",
        "// ---- 关系（每个三元组一条语句，端点按标签+名称匹配）----",
    ]
    statement_count = 0
    for (alabel, rtype, blabel), count in sorted(counts.items()):
        lines += [
            f"// {count} 条",
            f"LOAD CSV WITH HEADERS FROM 'file:///rels/{alabel}__{rtype}__{blabel}.csv' AS row",
            f"MATCH (a:`{alabel}` {{name: row.aname}}), (b:`{blabel}` {{name: row.bname}})",
            f"CREATE (a)-[:`{rtype}`]->(b);",
            "",
        ]
        statement_count += 1

    (BASE / "import.cypher").write_text("\n".join(lines), encoding="utf-8")

    manifest = {
        "nodes_csv": "nodes.csv",
        "disease_csv": "disease.csv",
        "rels_csv_split": len(counts),
        "rel_statements": statement_count,
        "rels_total": total,
        "triples": [
            {"alabel": k[0], "rtype": k[1], "blabel": k[2], "count": v}
            for k, v in sorted(counts.items())
        ],
    }
    (BASE / "import-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"关系文件 {len(counts)} 个，关系语句 {statement_count} 条，关系总数 {total}")
    print(f"导入脚本: {BASE / 'import.cypher'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
