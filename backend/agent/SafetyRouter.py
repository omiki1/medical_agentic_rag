"""Risk router: layered, explainable urgency triage for symptom descriptions.

This is an engineering safety net, not a clinical triage model. It classifies the
USER'S CURRENT UTTERANCE into risk bands using explicit composite-signal rules and
their colloquial rewrites. Composite signals (chest pressure + sweating + arm
discomfort; facial droop + one-sided weakness + slurred speech; child diarrhoea +
no urine + lethargy) are required so a single word ("胸痛", "胳膊麻") never fires
the highest band on its own, while textbook phrasing still works.

Design rules (per the release checklist):
- Runs before any model or retrieval step; output is limited to risk band, matched
  signals and requested clarifications - never a diagnosis, medication or tool call.
- Handles negation ("没有胸痛"), history ("去年发作过"), hypothesis ("如果胸痛会怎样")
  and academic/科普 ("科普：胸痛的鉴别") so they are not treated as current events.
- The urgent/emergency band must not depend on Dense, Neo4j, generation or review
  models succeeding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

NONE = "none"
URGENT = "urgent"  # 尽快就医 / 需要及时医疗评估
EMERGENCY = "emergency"  # 立即呼叫急救

_NEGATION = re.compile(
    r"(?:没有|并无|否认|不伴|未出现|无|不再|从未|不是|不像是|没得|没感觉有)"
    r".{0,6}$|(?:no|without|not having|never had)\s*$",
    re.I,
)
_HISTORY = re.compile(r"去年|以前|曾经|之前有过|小时候|之前查过|上个月|三年前|既往|有.{0,4}史", re.I)
_ACADEMIC = re.compile(
    r"科普|教材|论文|什么是|定义|鉴别|机制|有哪些原因|的原因|知识|学习|写作业|考试|想问一下.{0,6}(?:区别|分类)",
    re.I,
)
_HYPOTHETICAL = re.compile(r"如果.{0,8}(?:会|该)|假如|假设|要是", re.I)


def _active_clauses(text: str) -> list[str]:
    """Split into clauses and keep only those describing current, positive facts."""
    lowered = text.lower()
    clauses = re.split(r"[，。；！？,;.!?]|但是|不过|但|然而", lowered)
    kept = []
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        if _NEGATION.search(clause) and not re.search(r"没有发烧|没有.{0,4}(?:发烧|呕吐)", clause):
            # A clause that negates a signal is not evidence FOR that signal, but it
            # may still carry other positive signals (e.g. "没有胸痛，但左臂麻").
            pass
        kept.append(clause)
    return kept


@dataclass
class RiskDecision:
    level: str = NONE
    code: str = ""  # stable reason code: heart_attack_like / stroke_like / ...
    signals: list[str] = field(default_factory=list)
    band_message: str = ""

    @property
    def active(self):
        return self.level in {URGENT, EMERGENCY}


# Each rule: (code, band, required signal groups; at least one term per group must
# appear in the utterance as a whole - colloquial speech separates the composite
# signals with commas ("胸口像压了石头，冒冷汗，左胳膊酸"). Single-clause negation
# and history filtering still apply before the whole-utterance match.
_COMBINED_RULES = [
    # --- MI-like: chest pressure/ache + sweating + arm/shoulder/jaw radiation ---
    (
        "heart_attack_like",
        EMERGENCY,
        [
            [r"胸口|胸痛|胸闷|心口|胸前|胸部|心脏"],
            [r"石头|压|闷|紧|痛|疼|窒息|绞"],
            [r"冷汗|冒汗|出汗|大汗|冷汗淋漓"],
        ],
        "描述像心肌缺血的危险组合（胸部压迫不适并出汗）。请立即拨打当地急救电话或前往急诊，不要自己开车；等待时可解开衣领保持安静。",
    ),
    (
        "heart_attack_radiation",
        URGENT,
        [
            [r"胸口|胸痛|胸闷|心口|胸前|胸部"],
            [r"左臂|左胳膊|左手|肩膀|肩部|后背|下颌|牙|上肢"],
            [r"麻|酸|痛|疼|放射|牵扯|无力"],
        ],
        "胸部不适伴上肢/肩背放射感需要尽快就医评估，不要只当作普通疲劳。",
    ),
    # --- Stroke-like (FAST): face + arm + speech ---
    (
        "stroke_like",
        EMERGENCY,
        [
            [r"嘴(?:角|巴)?|脸|面部|半边脸|口角"],
            [r"歪|斜|耷拉|不对称|麻|僵|下垂"],
            [r"手|胳膊|手臂|肢体|脚|腿|上肢"],
            [r"抬不起|无力|没力气|麻木|不听使唤|软|动不了"],
        ],
        "描述像卒中的危险组合（面部异常、单侧肢体无力）。请立即拨打急救电话（中国大陆 120），记录发病时间，不要进食或服药。",
    ),
    (
        "stroke_fast_speech",
        EMERGENCY,
        [
            [r"话|言语|说话|舌头|吐字|讲|表达"],
            [r"不清|含糊|不利索|说不清|大舌头|说不出|混乱|语无伦次"],
        ],
        "突发言语不清需要立即按卒中急救处理，请马上拨打急救电话。",
    ),
    # --- Child dehydration ---
    (
        "child_dehydration",
        URGENT,
        [
            [r"孩子|娃|宝宝|儿童|小孩|幼儿|婴儿|儿子|女儿|我家"],
            [r"拉|泻|吐|呕吐|水样|腹泻"],
            [r"没尿|不尿|尿少|尿得少|没哭没眼泪|眼窝凹|没精神|蔫|嗜睡|叫不醒|喝水也吐|不愿喝"],
        ],
        "孩子腹泻/呕吐伴尿少或无尿、精神差，提示脱水风险，应尽快到儿科或急诊评估补液，不要继续在家观察。",
    ),
    # --- Appendicitis-like: umbilical pain migrating to right lower quadrant ---
    (
        "appendicitis_like",
        URGENT,
        [
            [r"肚脐|脐周|肚脐眼|肚子"],
            [r"疼|痛"],
            [r"右下|右边下|右下腹|右下方"],
            [r"更|加重|厉害|走|震|颠|跳|转移"],
        ],
        "疼痛从肚脐周围转移到右下腹且活动时加重，符合阑尾炎常见表现，请尽快就医外科评估，确诊前避免进食。",
    ),
    # --- Single severe signals (kept for completeness, urgent not emergency) ---
    (
        "severe_headache_sudden",
        URGENT,
        [
            [r"突然|突发|一下子|刚刚|瞬间"],
            [r"头痛|头疼|头要炸|爆炸"],
            [r"剧烈|最疼|从未.{0,4}疼|炸开|雷击"],
        ],
        "突发剧烈头痛需要尽快就医，以排除需要紧急处理的原因。",
    ),
    (
        "syncope_now",
        EMERGENCY,
        [
            [r"晕倒|昏倒|失去意识|不省人事|叫不醒|昏迷|晕厥"],
        ],
        "意识丧失或叫不醒属于紧急情况，请立即拨打急救电话。",
    ),
]

EMERGENCY_ACTION = "你描述的情况可能需要立即医疗处理：请马上拨打当地急救电话（中国大陆 120）或前往急诊，不要等待在线问答。"
URGENT_ACTION = "你描述的情况建议尽快就医或联系医生评估，不要仅依赖在线信息拖延处理。"


def _clause_level(clause: str) -> str | None:
    """Return band if a single-clause rule (syncope etc.) matches this clause."""
    for code, band, groups, message in _COMBINED_RULES:
        if len(groups) == 1 and all(any(re.search(p, clause) for p in group) for group in groups):
            return code
    return None


def classify(text: str, previous_risk: str = NONE) -> RiskDecision:
    """Classify current utterance; combine with previous risk when relevant.

    previous_risk is the stored band from earlier turns (e.g. URGENT appendicitis
    watch); a current clause that keeps describing the same evolving story keeps or
    raises the band instead of being treated as a brand-new topic.
    """
    lowered = text.lower()
    if _ACADEMIC.search(lowered) and not re.search(r"我|孩子|娃|家人|父亲|母亲|现在|此刻|正在", lowered):
        return RiskDecision(level=NONE, code="academic_context")
    if _HYPOTHETICAL.search(lowered):
        return RiskDecision(level=NONE, code="hypothetical_context")
    # History-only statements ("去年胸口疼过") are not current events. But if the
    # utterance mixes past with present ("以前不这样，现在突然…"), the current part
    # still counts, so only fully-past sentences are excluded.
    if _HISTORY.search(lowered) and not re.search(r"现在|今天|刚才|此刻|突然|刚刚|这(?:次|两)天", lowered):
        return RiskDecision(level=NONE, code="historical_context")

    # Whole-utterance composite match (multi-group rules). Negated groups must not
    # count: split into clauses and drop any clause that negates its symptoms
    # ("没有嘴歪", "也不喘", "没说不清话"), then match on the positive remainder.
    clauses = [c.strip() for c in re.split(r"[，。；！？,;.!?]|但是|不过|但|然而", lowered) if c.strip()]
    positive_clauses = []
    for clause in clauses:
        if re.search(r"^(?:没有|没|无|并无|否认|不伴|不是|不再|也不|也没|不(?:是|会)?)", clause):
            continue  # clause negates its own symptoms
        if re.search(r"也没有|也没有|没再说|没有再说", clause):
            continue
        positive_clauses.append(clause)
    signal_text = "，".join(positive_clauses)

    best = RiskDecision(level=NONE)
    for code, band, groups, message in _COMBINED_RULES:
        if len(groups) == 1:
            continue  # single-clause rules handled below
        if all(any(re.search(p, signal_text) for p in group) for group in groups):
            if band == EMERGENCY or (band == URGENT and best.level != EMERGENCY):
                best = RiskDecision(level=band, code=code, signals=[code], band_message=message)
                if band == EMERGENCY:
                    break
    if best.level == NONE:
        for clause in _active_clauses(text):
            code = _clause_level(clause)
            if code is None:
                continue
            band = next(r[1] for r in _COMBINED_RULES if r[0] == code)
            message = next(r[3] for r in _COMBINED_RULES if r[0] == code)
            if band == EMERGENCY or (band == URGENT and best.level != EMERGENCY):
                best = RiskDecision(level=band, code=code, signals=[code], band_message=message)
                if band == EMERGENCY:
                    break
    if best.level == NONE and previous_risk in {URGENT, EMERGENCY}:
        # Earlier turns already established an urgent story and this turn continues
        # describing the same evolving complaint; do not silently downgrade.
        best = RiskDecision(
            level=previous_risk,
            code="continuing_risk_story",
            signals=["continuing_prior_risk"],
            band_message="延续上一轮已提示的风险，仍应尽快就医评估。",
        )
    return best


def action_for(decision: RiskDecision) -> str:
    if decision.level == EMERGENCY:
        return EMERGENCY_ACTION + "\n\n" + decision.band_message
    if decision.level == URGENT:
        return URGENT_ACTION + "\n\n" + decision.band_message
    return ""
