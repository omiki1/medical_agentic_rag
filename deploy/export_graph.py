"""从本地 Neo4j 导出疾病图谱为 CSV，供 ECS 上的 Neo4j 导入。

背景：README 与验收清单都把 Neo4j 的 383,229 条关系当作"继承自原系统、只读、
不清空不重建"的既有资产，但仓库里没有它的装载脚本（MergeWHO 明确 neo4j_writes=0）。
ECS 上是全新的 neo4j:5.26 容器，因此该图谱缺失，图谱校验层退化为 0 行。
本脚本把本地图谱导出成与版本无关的 CSV，再用 LOAD CSV 重建。

输出到 deploy/graph-export/：
    nodes.csv          label,name
    disease.csv        name + 9 个疾病属性
    rels.csv           alabel,aname,rtype,blabel,bname
    manifest.json      计数与校验信息
"""

import csv
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

LABELS = [
    "Category", "Check", "Cureway", "Department",
    "Disease", "Dishes", "Drug", "Food", "Symptom",
]
DISEASE_PROPS = [
    "cause", "cost_money", "cure_lasttime", "cured_prob", "desc",
    "get_prob", "get_way", "prevent", "yibao_status",
]
OUT = Path(__file__).resolve().parents[1] / "deploy" / "graph-export"


def main() -> int:
    from common.Settings import Settings
    from neo4j import GraphDatabase

    settings = Settings()
    OUT.mkdir(parents=True, exist_ok=True)
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
        connection_timeout=15,
    )
    driver.verify_connectivity()
    counts = {}

    with driver.session(database=settings.neo4j_database) as session:
        # ---- 节点 ----
        with (OUT / "nodes.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["label", "name"])
            total = 0
            for label in LABELS:
                rows = session.run(
                    f"MATCH (n:`{label}`) WHERE n.name IS NOT NULL RETURN n.name AS name"
                )
                n = 0
                for row in rows:
                    writer.writerow([label, row["name"]])
                    n += 1
                counts[label] = n
                total += n
                print(f"  nodes {label:12s} {n}")
            counts["_nodes_total"] = total

        # ---- 疾病属性 ----
        with (OUT / "disease.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["name", *DISEASE_PROPS])
            rows = session.run(
                "MATCH (d:Disease) WHERE d.name IS NOT NULL "
                "RETURN d.name AS name, " + ", ".join(f"d.`{p}` AS `{p}`" for p in DISEASE_PROPS)
            )
            n = 0
            for row in rows:
                values = []
                for prop in DISEASE_PROPS:
                    value = row[prop]
                    values.append("" if value is None else str(value))
                writer.writerow([row["name"], *values])
                n += 1
            counts["_disease_props"] = n
            print(f"  disease props {n}")

        # ---- 关系 ----
        with (OUT / "rels.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["alabel", "aname", "rtype", "blabel", "bname"])
            rows = session.run(
                "MATCH (a)-[r]->(b) "
                "WHERE a.name IS NOT NULL AND b.name IS NOT NULL "
                "RETURN labels(a)[0] AS alabel, a.name AS aname, "
                "type(r) AS rtype, labels(b)[0] AS blabel, b.name AS bname"
            )
            rel_counts = {}
            n = 0
            for row in rows:
                writer.writerow([row["alabel"], row["aname"], row["rtype"], row["blabel"], row["bname"]])
                rel_counts[row["rtype"]] = rel_counts.get(row["rtype"], 0) + 1
                n += 1
            counts["_rels_total"] = n
            counts["_rel_types"] = rel_counts
            print(f"  relationships {n}")

    driver.close()

    manifest = {
        "source_uri": settings.neo4j_uri,
        "source_database": settings.neo4j_database,
        "labels": LABELS,
        "disease_props": DISEASE_PROPS,
        "counts": counts,
        "files": {
            name: {"bytes": (OUT / name).stat().st_size}
            for name in ("nodes.csv", "disease.csv", "rels.csv")
        },
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest["files"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
