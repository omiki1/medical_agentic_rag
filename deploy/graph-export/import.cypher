// MediAtlas 疾病图谱导入（由 deploy/prepare_graph_import.py 生成）
// 幂等前提：目标图谱为空；关系使用 CREATE，重复执行会产生重复边。

// ---- 唯一性约束：端点按 (标签, 名称) 匹配的前提 ----
CREATE CONSTRAINT med_category_name IF NOT EXISTS FOR (n:`Category`) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT med_check_name IF NOT EXISTS FOR (n:`Check`) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT med_cureway_name IF NOT EXISTS FOR (n:`Cureway`) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT med_department_name IF NOT EXISTS FOR (n:`Department`) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT med_disease_name IF NOT EXISTS FOR (n:`Disease`) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT med_dishes_name IF NOT EXISTS FOR (n:`Dishes`) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT med_drug_name IF NOT EXISTS FOR (n:`Drug`) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT med_food_name IF NOT EXISTS FOR (n:`Food`) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT med_symptom_name IF NOT EXISTS FOR (n:`Symptom`) REQUIRE n.name IS UNIQUE;

// ---- 节点 ----
LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE row.label = 'Category'
MERGE (n:`Category` {name: row.name});

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE row.label = 'Check'
MERGE (n:`Check` {name: row.name});

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE row.label = 'Cureway'
MERGE (n:`Cureway` {name: row.name});

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE row.label = 'Department'
MERGE (n:`Department` {name: row.name});

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE row.label = 'Disease'
MERGE (n:`Disease` {name: row.name});

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE row.label = 'Dishes'
MERGE (n:`Dishes` {name: row.name});

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE row.label = 'Drug'
MERGE (n:`Drug` {name: row.name});

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE row.label = 'Food'
MERGE (n:`Food` {name: row.name});

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
WITH row WHERE row.label = 'Symptom'
MERGE (n:`Symptom` {name: row.name});

// ---- 疾病属性 ----
LOAD CSV WITH HEADERS FROM 'file:///disease.csv' AS row
MATCH (d:Disease {name: row.name})
SET d.`cause` = CASE WHEN row.`cause` = '' THEN null ELSE row.`cause` END, d.`cost_money` = CASE WHEN row.`cost_money` = '' THEN null ELSE row.`cost_money` END, d.`cure_lasttime` = CASE WHEN row.`cure_lasttime` = '' THEN null ELSE row.`cure_lasttime` END, d.`cured_prob` = CASE WHEN row.`cured_prob` = '' THEN null ELSE row.`cured_prob` END, d.`desc` = CASE WHEN row.`desc` = '' THEN null ELSE row.`desc` END, d.`get_prob` = CASE WHEN row.`get_prob` = '' THEN null ELSE row.`get_prob` END, d.`get_way` = CASE WHEN row.`get_way` = '' THEN null ELSE row.`get_way` END, d.`prevent` = CASE WHEN row.`prevent` = '' THEN null ELSE row.`prevent` END, d.`yibao_status` = CASE WHEN row.`yibao_status` = '' THEN null ELSE row.`yibao_status` END;

// ---- 关系（每个三元组一条语句，端点按标签+名称匹配）----
// 12 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_ACOMPANY__Disease.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 3 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_ACOMPANY__Symptom.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Symptom` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 5 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_CATEGORY__Category.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Category` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 3 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_CATEGORY__Department.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Department` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_CATEGORY__Disease.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 20 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_CHECK__Check.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Check` {name: row.bname})
CREATE (a)-[:`DISEASE_CHECK`]->(b);

// 6 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_CUREWAY__Cureway.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Cureway` {name: row.bname})
CREATE (a)-[:`DISEASE_CUREWAY`]->(b);

// 3 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_DEPARTMENT__Category.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Category` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 3 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_DEPARTMENT__Department.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Department` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_DEPARTMENT__Disease.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 16 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_DISHES__Dishes.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Dishes` {name: row.bname})
CREATE (a)-[:`DISEASE_DISHES`]->(b);

// 8 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_DO_EAT__Food.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Food` {name: row.bname})
CREATE (a)-[:`DISEASE_DO_EAT`]->(b);

// 19 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_DRUG__Drug.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Drug` {name: row.bname})
CREATE (a)-[:`DISEASE_DRUG`]->(b);

// 8 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_NOT_EAT__Food.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Food` {name: row.bname})
CREATE (a)-[:`DISEASE_NOT_EAT`]->(b);

// 4 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_SYMPTOM__Disease.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_SYMPTOM`]->(b);

// 17 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Category__DISEASE_SYMPTOM__Symptom.csv' AS row
MATCH (a:`Category` {name: row.aname}), (b:`Symptom` {name: row.bname})
CREATE (a)-[:`DISEASE_SYMPTOM`]->(b);

// 1 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Check__DISEASE_ACOMPANY__Disease.csv' AS row
MATCH (a:`Check` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 1 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Check__DISEASE_ACOMPANY__Symptom.csv' AS row
MATCH (a:`Check` {name: row.aname}), (b:`Symptom` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 3 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Check__DISEASE_CATEGORY__Category.csv' AS row
MATCH (a:`Check` {name: row.aname}), (b:`Category` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Check__DISEASE_CATEGORY__Department.csv' AS row
MATCH (a:`Check` {name: row.aname}), (b:`Department` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 6 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Check__DISEASE_CHECK__Check.csv' AS row
MATCH (a:`Check` {name: row.aname}), (b:`Check` {name: row.bname})
CREATE (a)-[:`DISEASE_CHECK`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Check__DISEASE_CUREWAY__Cureway.csv' AS row
MATCH (a:`Check` {name: row.aname}), (b:`Cureway` {name: row.bname})
CREATE (a)-[:`DISEASE_CUREWAY`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Check__DISEASE_DEPARTMENT__Category.csv' AS row
MATCH (a:`Check` {name: row.aname}), (b:`Category` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Check__DISEASE_DEPARTMENT__Department.csv' AS row
MATCH (a:`Check` {name: row.aname}), (b:`Department` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 5 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Check__DISEASE_DRUG__Drug.csv' AS row
MATCH (a:`Check` {name: row.aname}), (b:`Drug` {name: row.bname})
CREATE (a)-[:`DISEASE_DRUG`]->(b);

// 3 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Check__DISEASE_SYMPTOM__Symptom.csv' AS row
MATCH (a:`Check` {name: row.aname}), (b:`Symptom` {name: row.bname})
CREATE (a)-[:`DISEASE_SYMPTOM`]->(b);

// 1 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Cureway__DISEASE_ACOMPANY__Disease.csv' AS row
MATCH (a:`Cureway` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 3 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Cureway__DISEASE_CATEGORY__Category.csv' AS row
MATCH (a:`Cureway` {name: row.aname}), (b:`Category` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Cureway__DISEASE_CATEGORY__Department.csv' AS row
MATCH (a:`Cureway` {name: row.aname}), (b:`Department` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 6 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Cureway__DISEASE_CHECK__Check.csv' AS row
MATCH (a:`Cureway` {name: row.aname}), (b:`Check` {name: row.bname})
CREATE (a)-[:`DISEASE_CHECK`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Cureway__DISEASE_CUREWAY__Cureway.csv' AS row
MATCH (a:`Cureway` {name: row.aname}), (b:`Cureway` {name: row.bname})
CREATE (a)-[:`DISEASE_CUREWAY`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Cureway__DISEASE_DEPARTMENT__Category.csv' AS row
MATCH (a:`Cureway` {name: row.aname}), (b:`Category` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Cureway__DISEASE_DEPARTMENT__Department.csv' AS row
MATCH (a:`Cureway` {name: row.aname}), (b:`Department` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 8 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Cureway__DISEASE_DISHES__Dishes.csv' AS row
MATCH (a:`Cureway` {name: row.aname}), (b:`Dishes` {name: row.bname})
CREATE (a)-[:`DISEASE_DISHES`]->(b);

// 4 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Cureway__DISEASE_DO_EAT__Food.csv' AS row
MATCH (a:`Cureway` {name: row.aname}), (b:`Food` {name: row.bname})
CREATE (a)-[:`DISEASE_DO_EAT`]->(b);

// 5 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Cureway__DISEASE_DRUG__Drug.csv' AS row
MATCH (a:`Cureway` {name: row.aname}), (b:`Drug` {name: row.bname})
CREATE (a)-[:`DISEASE_DRUG`]->(b);

// 4 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Cureway__DISEASE_NOT_EAT__Food.csv' AS row
MATCH (a:`Cureway` {name: row.aname}), (b:`Food` {name: row.bname})
CREATE (a)-[:`DISEASE_NOT_EAT`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Cureway__DISEASE_SYMPTOM__Disease.csv' AS row
MATCH (a:`Cureway` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_SYMPTOM`]->(b);

// 7 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Cureway__DISEASE_SYMPTOM__Symptom.csv' AS row
MATCH (a:`Cureway` {name: row.aname}), (b:`Symptom` {name: row.bname})
CREATE (a)-[:`DISEASE_SYMPTOM`]->(b);

// 12 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_ACOMPANY__Disease.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 3 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_ACOMPANY__Symptom.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Symptom` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 5 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_CATEGORY__Category.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Category` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 3 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_CATEGORY__Department.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Department` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_CATEGORY__Disease.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 20 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_CHECK__Check.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Check` {name: row.bname})
CREATE (a)-[:`DISEASE_CHECK`]->(b);

// 6 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_CUREWAY__Cureway.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Cureway` {name: row.bname})
CREATE (a)-[:`DISEASE_CUREWAY`]->(b);

// 3 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_DEPARTMENT__Category.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Category` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 3 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_DEPARTMENT__Department.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Department` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_DEPARTMENT__Disease.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 16 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_DISHES__Dishes.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Dishes` {name: row.bname})
CREATE (a)-[:`DISEASE_DISHES`]->(b);

// 8 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_DO_EAT__Food.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Food` {name: row.bname})
CREATE (a)-[:`DISEASE_DO_EAT`]->(b);

// 19 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_DRUG__Drug.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Drug` {name: row.bname})
CREATE (a)-[:`DISEASE_DRUG`]->(b);

// 8 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_NOT_EAT__Food.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Food` {name: row.bname})
CREATE (a)-[:`DISEASE_NOT_EAT`]->(b);

// 4 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_SYMPTOM__Disease.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_SYMPTOM`]->(b);

// 17 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Department__DISEASE_SYMPTOM__Symptom.csv' AS row
MATCH (a:`Department` {name: row.aname}), (b:`Symptom` {name: row.bname})
CREATE (a)-[:`DISEASE_SYMPTOM`]->(b);

// 34 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_ACOMPANY__Category.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Category` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_ACOMPANY__Check.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Check` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 34 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_ACOMPANY__Department.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Department` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 12024 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_ACOMPANY__Disease.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 4408 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_ACOMPANY__Symptom.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Symptom` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 25587 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_CATEGORY__Category.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Category` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 16781 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_CATEGORY__Department.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Department` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 80 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_CATEGORY__Disease.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 39418 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_CHECK__Check.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Check` {name: row.bname})
CREATE (a)-[:`DISEASE_CHECK`]->(b);

// 1 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_CHECK__Disease.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_CHECK`]->(b);

// 57 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_CHECK__Symptom.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Symptom` {name: row.bname})
CREATE (a)-[:`DISEASE_CHECK`]->(b);

// 21047 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_CUREWAY__Cureway.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Cureway` {name: row.bname})
CREATE (a)-[:`DISEASE_CUREWAY`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_CUREWAY__Disease.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_CUREWAY`]->(b);

// 16781 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_DEPARTMENT__Category.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Category` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 16781 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_DEPARTMENT__Department.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Department` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 80 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_DEPARTMENT__Disease.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 40221 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_DISHES__Dishes.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Dishes` {name: row.bname})
CREATE (a)-[:`DISEASE_DISHES`]->(b);

// 20 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_DISHES__Food.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Food` {name: row.bname})
CREATE (a)-[:`DISEASE_DISHES`]->(b);

// 28 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_DO_EAT__Dishes.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Dishes` {name: row.bname})
CREATE (a)-[:`DISEASE_DO_EAT`]->(b);

// 22230 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_DO_EAT__Food.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Food` {name: row.bname})
CREATE (a)-[:`DISEASE_DO_EAT`]->(b);

// 59736 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_DRUG__Drug.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Drug` {name: row.bname})
CREATE (a)-[:`DISEASE_DRUG`]->(b);

// 22239 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_NOT_EAT__Food.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Food` {name: row.bname})
CREATE (a)-[:`DISEASE_NOT_EAT`]->(b);

// 101 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_SYMPTOM__Check.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Check` {name: row.bname})
CREATE (a)-[:`DISEASE_SYMPTOM`]->(b);

// 11519 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_SYMPTOM__Disease.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_SYMPTOM`]->(b);

// 54710 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Disease__DISEASE_SYMPTOM__Symptom.csv' AS row
MATCH (a:`Disease` {name: row.aname}), (b:`Symptom` {name: row.bname})
CREATE (a)-[:`DISEASE_SYMPTOM`]->(b);

// 3 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_ACOMPANY__Category.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Category` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 3 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_ACOMPANY__Department.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Department` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 616 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_ACOMPANY__Disease.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 218 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_ACOMPANY__Symptom.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Symptom` {name: row.bname})
CREATE (a)-[:`DISEASE_ACOMPANY`]->(b);

// 1204 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_CATEGORY__Category.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Category` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 786 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_CATEGORY__Department.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Department` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 4 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_CATEGORY__Disease.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_CATEGORY`]->(b);

// 2016 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_CHECK__Check.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Check` {name: row.bname})
CREATE (a)-[:`DISEASE_CHECK`]->(b);

// 3 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_CHECK__Symptom.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Symptom` {name: row.bname})
CREATE (a)-[:`DISEASE_CHECK`]->(b);

// 956 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_CUREWAY__Cureway.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Cureway` {name: row.bname})
CREATE (a)-[:`DISEASE_CUREWAY`]->(b);

// 786 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_DEPARTMENT__Category.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Category` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 786 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_DEPARTMENT__Department.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Department` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 4 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_DEPARTMENT__Disease.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_DEPARTMENT`]->(b);

// 2542 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_DISHES__Dishes.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Dishes` {name: row.bname})
CREATE (a)-[:`DISEASE_DISHES`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_DISHES__Food.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Food` {name: row.bname})
CREATE (a)-[:`DISEASE_DISHES`]->(b);

// 1343 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_DO_EAT__Food.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Food` {name: row.bname})
CREATE (a)-[:`DISEASE_DO_EAT`]->(b);

// 3097 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_DRUG__Drug.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Drug` {name: row.bname})
CREATE (a)-[:`DISEASE_DRUG`]->(b);

// 1344 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_NOT_EAT__Food.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Food` {name: row.bname})
CREATE (a)-[:`DISEASE_NOT_EAT`]->(b);

// 2 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_SYMPTOM__Check.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Check` {name: row.bname})
CREATE (a)-[:`DISEASE_SYMPTOM`]->(b);

// 557 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_SYMPTOM__Disease.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Disease` {name: row.bname})
CREATE (a)-[:`DISEASE_SYMPTOM`]->(b);

// 2699 条
LOAD CSV WITH HEADERS FROM 'file:///rels/Symptom__DISEASE_SYMPTOM__Symptom.csv' AS row
MATCH (a:`Symptom` {name: row.aname}), (b:`Symptom` {name: row.bname})
CREATE (a)-[:`DISEASE_SYMPTOM`]->(b);
